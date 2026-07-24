import json
import os
import uuid
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session, joinedload, selectinload
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET_KEY,
    authenticate_reviewer,
    csrf_cookie_middleware,
    current_reviewer,
    require_reviewer,
    require_reviewer_form,
    safe_next_path,
    sign_in_reviewer,
    sign_out_reviewer,
    verify_csrf,
)
from app.ai_schema import validate_analysis_result, validation_error_text
from app.case_status import (
    allowed_next_statuses,
    invalid_transition_message,
)
from app.database import apply_sqlite_startup_migrations, engine, get_db, Base
from app.models import (
    AIAnalysisRecord,
    CaseEvent,
    HumanReviewStatus,
    Observation,
    ObservationImage,
    RiskCase,
    Site,
)
from app.provenance import (
    analysis_attempt_history,
    build_case_snapshot,
    build_contributor_original,
    case_snapshot,
    contributor_original,
)
from app.provider_identity import (
    PROVIDER_AZURE,
    PROVIDER_MOCK,
    provider_identity,
)
from app.risk import ALL_TAGS, TAG_LABELS
from app.reports import generate_report
from app.config import settings
from app.services.ai_analysis import (
    AIAnalysisResult,
    AZURE_PROVIDER_DIAGNOSTIC,
    analyze_observation_images,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = Path(os.environ.get("HERITAGERISK_UPLOADS_DIR", REPO_ROOT / "data" / "uploads"))
if not UPLOADS_DIR.is_absolute():
    UPLOADS_DIR = REPO_ROOT / UPLOADS_DIR
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_FORMAT_BY_EXTENSION = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
ALLOWED_IMAGE_EXTENSIONS = set(IMAGE_FORMAT_BY_EXTENSION)
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
MAX_OBSERVATION_IMAGES = 6

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

Base.metadata.create_all(bind=engine)
apply_sqlite_startup_migrations(engine)

app = FastAPI(title="HeritageRisk AI", version="0.1.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie=SESSION_COOKIE_NAME,
    max_age=SESSION_MAX_AGE_SECONDS,
    same_site="lax",
    https_only=False,
)
app.middleware("http")(csrf_cookie_middleware)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["TAG_LABELS"] = TAG_LABELS
templates.env.globals["current_reviewer"] = current_reviewer
templates.env.globals["provider_identity"] = provider_identity

REVIEW_ACTION_STATUSES = (
    HumanReviewStatus.APPROVED_FOR_AI,
    HumanReviewStatus.REJECTED,
    HumanReviewStatus.SENSITIVE,
)


def image_format_from_signature(content: bytes) -> str | None:
    header = content[:12]
    if header.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "WEBP"
    return None


def sanitize_image_content(content: bytes, image_format: str) -> bytes:
    try:
        with Image.open(BytesIO(content)) as candidate:
            if candidate.format != image_format:
                raise HTTPException(
                    status_code=400,
                    detail="Image content does not match its file extension.",
                )
            candidate.verify()

        with Image.open(BytesIO(content)) as source:
            source.load()
            oriented = ImageOps.exif_transpose(source)
            oriented.load()

            has_alpha = "A" in oriented.getbands() or "transparency" in source.info
            if image_format == "JPEG" and oriented.mode in {"L", "RGB", "CMYK"}:
                pixel_mode = oriented.mode
            elif image_format == "PNG" and oriented.mode in {
                "1",
                "L",
                "LA",
                "I",
                "I;16",
                "RGB",
                "RGBA",
            }:
                pixel_mode = oriented.mode
            else:
                pixel_mode = "RGBA" if image_format != "JPEG" and has_alpha else "RGB"

            pixels = (
                oriented
                if oriented.mode == pixel_mode
                else oriented.convert(pixel_mode)
            )
            clean_image = Image.frombytes(
                pixels.mode,
                pixels.size,
                pixels.tobytes(),
            )

            output = BytesIO()
            save_options: dict[str, int | bool] = {}
            if image_format == "JPEG":
                save_options = {"quality": 95, "subsampling": 0, "optimize": True}
            elif image_format == "WEBP":
                save_options = {"quality": 95}
            clean_image.save(output, format=image_format, **save_options)
            return output.getvalue()
    except HTTPException:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid JPG, PNG, or WEBP image.",
        ) from exc


async def save_upload_image(image: UploadFile) -> tuple[str, Path]:
    ext = Path(image.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported image type. Accepted image types are JPG, PNG, "
                "and WEBP."
            ),
        )

    content = await image.read(MAX_IMAGE_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image cannot be empty.")
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be 10 MB or smaller.")

    expected_format = IMAGE_FORMAT_BY_EXTENSION[ext]
    detected_format = image_format_from_signature(content)
    if detected_format is None:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid JPG, PNG, or WEBP image.",
        )
    if detected_format != expected_format:
        raise HTTPException(
            status_code=400,
            detail="Image content does not match its file extension.",
        )

    sanitized_content = sanitize_image_content(content, expected_format)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = UPLOADS_DIR / unique_name
    saved_path.write_bytes(sanitized_content)
    return f"/uploads/{unique_name}", saved_path


def cleanup_saved_uploads(saved_paths: list[Path]) -> None:
    for saved_path in saved_paths:
        saved_path.unlink(missing_ok=True)


def parse_damage_tags(raw_tags: str) -> str:
    tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
    invalid_tags = [tag for tag in tags if tag not in ALL_TAGS]
    if invalid_tags:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported damage tag(s): {', '.join(invalid_tags)}",
        )
    return ",".join(tags)


def parse_review_action_status(raw_status: str) -> HumanReviewStatus:
    try:
        review_status = HumanReviewStatus(raw_status)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid human review status",
        ) from exc

    if review_status not in REVIEW_ACTION_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Invalid human review status",
        )

    return review_status


def ai_raw_data(observation: Observation) -> dict:
    if not observation.ai_raw_response:
        return {}
    try:
        data = json.loads(observation.ai_raw_response)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def ai_schema_v2_data(observation: Observation) -> dict | None:
    data = ai_raw_data(observation)
    if data.get("schema_version") != "2" or data.get("validation_status") == "failed":
        return None
    try:
        return validate_analysis_result(data).model_dump()
    except Exception:
        return None


def ai_v2_indicators(observation: Observation) -> list[dict]:
    result = ai_schema_v2_data(observation)
    return result.get("indicators", []) if result else []


def extract_ai_damage_tags(observation: Observation) -> list[str]:
    indicators = ai_v2_indicators(observation)
    if indicators:
        return [
            indicator["indicator_type"]
            for indicator in indicators
            if indicator.get("indicator_type") in ALL_TAGS
        ]
    raw_tags = ai_raw_data(observation).get("damage_tags", [])
    if not isinstance(raw_tags, list):
        return []
    return [
        tag
        for tag in raw_tags
        if isinstance(tag, str) and tag in ALL_TAGS
    ]


def extract_ai_severity(observation: Observation) -> int | None:
    indicators = ai_v2_indicators(observation)
    if indicators:
        return max(
            int(indicator["severity_contribution"])
            for indicator in indicators
        )
    v2 = ai_schema_v2_data(observation)
    if v2 and v2.get("evidence_sufficiency") == "insufficient":
        return 1
    raw_severity = ai_raw_data(observation).get("severity")
    try:
        return max(1, min(5, int(raw_severity)))
    except (TypeError, ValueError):
        return None


def extract_ai_uncertainty(observation: Observation) -> str:
    v2 = ai_schema_v2_data(observation)
    if v2:
        if v2.get("evidence_sufficiency") == "insufficient":
            return v2.get("insufficient_reason") or "Evidence was insufficient."
        return f"Evidence sufficiency: {v2.get('evidence_sufficiency')}."

    uncertainty = ai_raw_data(observation).get("uncertainty")
    if isinstance(uncertainty, str) and uncertainty.strip():
        return uncertainty.strip()

    confidence = observation.ai_confidence
    if confidence is None:
        return "No uncertainty statement was provided. Human verification is required."
    if confidence < 40:
        return "High uncertainty. The visible evidence is limited or ambiguous."
    if confidence < 70:
        return (
            "Moderate uncertainty. Confirm the suggested indicators against "
            "every image."
        )
    return "Lower uncertainty, but the result still requires human verification."


def extract_ai_review(observation: Observation) -> dict:
    review = observation.ai_review_decision
    if isinstance(review, dict) and review.get("decision"):
        return review

    # Compatibility for records finalized before reviewer decisions were separated.
    review = ai_raw_data(observation).get("human_ai_review", {})
    return review if isinstance(review, dict) else {}


def ai_review_decision_label(
    observation: Observation,
    final_tags: list[str],
    final_severity: int,
    final_summary: str,
    final_recommended_action: str,
) -> str:
    """Describe whether the human-approved final differs from the AI proposal."""
    was_edited = (
        final_summary != (observation.ai_summary or "")
        or final_recommended_action
        != (observation.ai_recommended_action or "")
        or final_tags != extract_ai_damage_tags(observation)
        or final_severity != extract_ai_severity(observation)
    )
    return "Edited and accepted" if was_edited else "Accepted"


def ensure_observation_approved_for_ai(observation: Observation) -> None:
    if observation.human_review_status != HumanReviewStatus.APPROVED_FOR_AI:
        raise HTTPException(
            status_code=403,
            detail=(
                "Observation must be approved by a human reviewer before AI "
                "analysis."
            ),
        )
    if not observation.reviewed_by:
        raise HTTPException(
            status_code=403,
            detail="A recorded human reviewer is required before AI analysis.",
        )


def ensure_observation_ready_for_case(observation: Observation) -> None:
    ensure_observation_approved_for_ai(observation)
    if extract_ai_review(observation).get("decision") == "Rejected":
        raise HTTPException(
            status_code=403,
            detail="The current AI proposal was rejected and must be re-run.",
        )
    if (
        not observation.ai_summary
        or observation.ai_analysis_status not in ("complete", "mock")
    ):
        raise HTTPException(
            status_code=403,
            detail="AI analysis summary is required before creating a Risk Case.",
        )


def create_risk_case_from_observation(
    db: Session,
    observation: Observation,
    final_tags: list[str],
    final_severity: int,
    final_summary: str,
    final_recommended_action: str,
    reviewer_decision: dict,
    finalized_by: str,
    routed_to: str | None = None,
) -> RiskCase:
    observation.damage_tags = ",".join(final_tags)
    observation.severity = final_severity

    snapshot = build_case_snapshot(
        observation=observation,
        final_tags=final_tags,
        final_severity=final_severity,
        final_summary=final_summary,
        final_recommended_action=final_recommended_action,
        reviewer_decision=reviewer_decision,
        finalized_by=finalized_by,
    )
    case = RiskCase(
        observation_id=observation.id,
        risk_score=snapshot["capped_score"],
        risk_band=snapshot["band"],
        routed_to=routed_to,
        final_snapshot=snapshot,
        finalized_by=finalized_by,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    report_path = generate_report(case)
    case.report_path = report_path
    db.commit()
    db.refresh(case)
    return case


def build_ai_intake_notes(
    site: Site,
    observation_notes: str | None = None,
) -> str:
    parts = [
        f"Site name: {site.name}",
        f"Location: {site.location or 'Not provided'}",
        f"Site description: {site.description or 'Not provided'}",
    ]
    if observation_notes:
        parts.append(f"Contributor notes: {observation_notes}")
    return "\n".join(parts)


def apply_ai_analysis_result(
    observation: Observation,
    result: AIAnalysisResult,
) -> None:
    for attempt in result.preceding_attempts:
        attempted_at = attempt.attempted_at
        if attempted_at.tzinfo is not None:
            attempted_at = (
                attempted_at.astimezone(timezone.utc).replace(tzinfo=None)
            )
        observation.analysis_records.append(
            AIAnalysisRecord(
                status=attempt.status,
                provider=attempt.provider,
                diagnostic=attempt.diagnostic,
                created_at=attempted_at,
            )
        )

    allowed_image_ids = {image.id for image in observation.images}
    raw_payload = result.structured_response
    if raw_payload is None and result.raw_response:
        try:
            parsed_payload = json.loads(result.raw_response)
            raw_payload = parsed_payload if isinstance(parsed_payload, dict) else parsed_payload
        except json.JSONDecodeError:
            raw_payload = result.raw_response

    validation_error = result.validation_error
    validated_v2: dict | None = None
    if validation_error is None and isinstance(raw_payload, dict) and raw_payload.get("schema_version") == "2":
        try:
            validated_v2 = validate_analysis_result(
                raw_payload,
                allowed_image_ids=allowed_image_ids,
            ).model_dump()
        except Exception as exc:  # noqa: BLE001
            validation_error = validation_error_text(exc)

    if validation_error is not None:
        observation.ai_analysis_status = "failed"
        observation.ai_summary = "AI response failed schema validation."
        observation.ai_confidence = 0
        observation.ai_provider = result.provider
        observation.ai_recommended_action = (
            "Human review required before any action is taken."
        )
        observation.ai_raw_response = json.dumps(
            {
                "schema_version": "2",
                "validation_status": "failed",
                "provider": result.provider,
                "validation_error": validation_error,
                "raw_payload": raw_payload,
            }
        )
        observation.analysis_records.append(
            AIAnalysisRecord(
                status="failed",
                provider=result.provider,
                diagnostic=validation_error,
            )
        )
        return

    identity = provider_identity(result.provider)
    azure_failed = (
        identity == PROVIDER_AZURE
        and result.structured_response is None
        and result.confidence == 0
        and result.damage_tags == ["other"]
    )

    if azure_failed:
        observation.ai_analysis_status = "failed"
    elif identity == PROVIDER_MOCK:
        observation.ai_analysis_status = "mock"
    else:
        observation.ai_analysis_status = "complete"

    observation.analysis_records.append(
        AIAnalysisRecord(
            status=observation.ai_analysis_status,
            provider=result.provider,
            diagnostic=(
                AZURE_PROVIDER_DIAGNOSTIC if azure_failed else None
            ),
        )
    )

    observation.ai_summary = result.summary
    observation.ai_confidence = result.confidence
    observation.ai_provider = result.provider
    observation.ai_recommended_action = result.recommended_action

    previous_review = extract_ai_review(observation)
    current_review_record = observation.ai_review_decision
    review_history = []
    if isinstance(current_review_record, dict):
        stored_history = current_review_record.get("history", [])
        if isinstance(stored_history, list):
            review_history.extend(stored_history)
    if previous_review.get("decision"):
        review_history.append(
            {
                key: previous_review.get(key)
                for key in (
                    "decision",
                    "reviewer_notes",
                    "reviewed_at",
                    "reviewed_by",
                )
            }
        )
    observation.ai_review_decision = (
        {"history": review_history} if review_history else None
    )

    if validated_v2 is not None:
        validated_v2["provider"] = result.provider
        observation.ai_raw_response = json.dumps(validated_v2)
    else:
        try:
            raw_data = json.loads(result.raw_response) if result.raw_response else {}
        except (json.JSONDecodeError, TypeError):
            raw_data = {}
        if not isinstance(raw_data, dict):
            raw_data = {}
        raw_data.update(
            {
                "damage_tags": result.damage_tags,
                "severity": max(1, min(5, result.severity)),
                "confidence": max(0, min(100, result.confidence)),
                "summary": result.summary,
                "recommended_action": result.recommended_action,
                "uncertainty": result.uncertainty,
            }
        )
        observation.ai_raw_response = json.dumps(raw_data)


def record_ai_review_decision(
    observation: Observation,
    decision: str,
    reviewer_username: str,
    reviewer_notes: str = "",
) -> dict:
    existing_record = observation.ai_review_decision
    history = []
    if isinstance(existing_record, dict):
        existing_history = existing_record.get("history", [])
        if isinstance(existing_history, list):
            history.extend(existing_history)
        if existing_record.get("decision"):
            history.append(
                {
                    key: existing_record.get(key)
                    for key in (
                        "decision",
                        "reviewer_notes",
                        "reviewed_at",
                        "reviewed_by",
                    )
                }
            )

    review = {
        "decision": decision,
        "reviewer_notes": reviewer_notes.strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewer_username,
    }
    if history:
        review["history"] = history
    observation.ai_review_decision = review
    return review


def run_observation_analysis(observation: Observation, db: Session) -> None:
    ensure_observation_approved_for_ai(observation)
    if observation.risk_case:
        raise HTTPException(
            status_code=400,
            detail="AI analysis cannot be changed after a Risk Case is created.",
        )
    image_paths = [
        image_url_to_local_path(image.image_url)
        for image in observation.images
    ]
    result = analyze_observation_images(
        image_paths=image_paths,
        image_ids=[image.id for image in observation.images],
        notes=build_ai_intake_notes(observation.site, observation.notes),
    )
    apply_ai_analysis_result(observation, result)
    db.commit()


def image_url_to_local_path(image_url: str | None) -> str:
    if not image_url:
        return ""
    filename = image_url.rsplit("/", 1)[-1]
    return str(UPLOADS_DIR / filename)


def format_relative_time(created_at: datetime | None) -> str:
    if created_at is None:
        return "Unknown"

    created = created_at
    if created.tzinfo is not None:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seconds = max(0, int((now - created).total_seconds()))
    if seconds < 60:
        return "Just now"

    minutes = seconds // 60
    if minutes < 60:
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit} ago"

    hours = minutes // 60
    if hours < 24:
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit} ago"

    days = hours // 24
    unit = "day" if days == 1 else "days"
    return f"{days} {unit} ago"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/reviewer/login", response_class=HTMLResponse)
def reviewer_login_form(request: Request, next: str = ""):
    next_path = safe_next_path(next)
    if current_reviewer(request):
        return RedirectResponse(url=next_path, status_code=303)
    return templates.TemplateResponse(
        "reviewer_login.html",
        {
            "request": request,
            "next_path": next_path,
            "error": None,
        },
    )


@app.post("/reviewer/login")
async def reviewer_login(
    request: Request,
    _csrf: None = Depends(verify_csrf),
    username: str = Form(...),
    password: str = Form(...),
    next_path: str = Form(""),
):
    reviewer = authenticate_reviewer(username, password)
    if reviewer is None:
        return templates.TemplateResponse(
            "reviewer_login.html",
            {
                "request": request,
                "next_path": safe_next_path(next_path),
                "error": "Invalid reviewer username or password.",
            },
            status_code=401,
        )

    sign_in_reviewer(request, reviewer)
    return RedirectResponse(url=safe_next_path(next_path), status_code=303)


@app.post("/reviewer/logout")
async def reviewer_logout(
    request: Request,
    _reviewer: str = Depends(require_reviewer_form),
):
    sign_out_reviewer(request)
    return RedirectResponse(url="/reviewer/login", status_code=303)


@app.post("/seed")
async def seed_data(
    reviewer: str = Depends(require_reviewer_form),
    db: Session = Depends(get_db),
):
    from app.seed import seed
    seed(db, reviewer_username=reviewer)
    return RedirectResponse(url="/?seeded=1", status_code=303)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.created_at.desc()).all()
    all_cases = (
        db.query(RiskCase)
        .options(joinedload(RiskCase.observation).joinedload(Observation.site))
        .order_by(RiskCase.created_at.desc())
        .all()
    )
    all_obs = (
        db.query(Observation)
        .options(selectinload(Observation.site), selectinload(Observation.images))
        .order_by(Observation.created_at.desc())
        .all()
    )

    high_risk_cases = [c for c in all_cases if c.risk_band == "High"]
    needs_review_cases = [c for c in all_cases if c.status == "Needs Review"]
    approved_observations = [
        obs
        for obs in all_obs
        if obs.human_review_status == HumanReviewStatus.APPROVED_FOR_AI
    ]
    priority_review_cases = [
        c
        for c in all_cases
        if c.risk_band == "High" or c.status in ("Draft", "Needs Review")
    ]
    awaiting_review_observations = [
        obs
        for obs in all_obs
        if obs.human_review_status == HumanReviewStatus.PENDING
    ]
    recent_activity = []
    for observation in all_obs:
        recent_activity.append(
            {
                "kind": "Observation",
                "title": f"Observation #{observation.id}",
                "site_name": (
                    observation.site.name if observation.site else "Unknown site"
                ),
                "href": f"/observations/{observation.id}",
                "status": observation.human_review_status.value,
                "risk_band": None,
                "created_at": observation.created_at,
            }
        )
    for case in all_cases:
        site = case.observation.site if case.observation else None
        recent_activity.append(
            {
                "kind": "Risk Case",
                "title": f"Risk Case #{case.id}",
                "site_name": site.name if site else "Unknown site",
                "href": f"/cases/{case.id}",
                "status": case.status,
                "risk_band": case.risk_band,
                "created_at": case.created_at,
            }
        )
    recent_activity = sorted(
        recent_activity,
        key=lambda activity: activity["created_at"] or datetime.min,
        reverse=True,
    )[:5]
    seeded = request.query_params.get("seeded") == "1"
    upload_observation_site = sites[0] if sites else None
    case_status_counts = {
        status: len([case for case in all_cases if case.status == status])
        for status in RiskCase.STATUSES
    }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "sites": sites,
            "total_sites": len(sites),
            "total_obs": len(all_obs),
            "total_observations_submitted": len(all_obs),
            "total_cases": len(all_cases),
            "total_risk_cases_generated": len(all_cases),
            "high_risk_count": len(high_risk_cases),
            "high_priority_cases_count": len(high_risk_cases),
            "needs_review_count": len(needs_review_cases),
            "approved_observations_count": len(approved_observations),
            "observations_awaiting_review_count": len(awaiting_review_observations),
            "priority_review_count": len(priority_review_cases),
            "case_status_counts": case_status_counts,
            "recent_cases": all_cases[:8],
            "recent_obs": all_obs[:6],
            "recent_activity": recent_activity,
            "upload_observation_site": upload_observation_site,
            "azure_enabled": settings.azure_openai_enabled,
            "mock_fallback_available": True,
            "seeded": seeded,
        },
    )


@app.get("/sites", response_class=HTMLResponse)
def sites_list(request: Request, db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.created_at.desc()).all()
    return templates.TemplateResponse(
        "sites_list.html", {"request": request, "sites": sites}
    )


@app.get("/sites/new", response_class=HTMLResponse)
def site_new_form(
    request: Request,
    _reviewer: str = Depends(require_reviewer),
):
    return templates.TemplateResponse("site_new.html", {"request": request})


@app.post("/sites")
async def site_create(
    request: Request,
    reviewer: str = Depends(require_reviewer_form),
    name: str = Form(...),
    location: str = Form(""),
    description: str = Form(""),
    intake_notes: str = Form(""),
    images: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    uploaded_images = [image for image in images or [] if image and image.filename]
    if len(uploaded_images) > MAX_OBSERVATION_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload no more than {MAX_OBSERVATION_IMAGES} images.",
        )
    saved_paths: list[Path] = []
    image_urls: list[str] = []

    try:
        for image in uploaded_images:
            image_url, saved_path = await save_upload_image(image)
            image_urls.append(image_url)
            saved_paths.append(saved_path)

        site = Site(
            name=name,
            location=location or None,
            description=description or None,
        )
        db.add(site)
        db.flush()

        observation = None
        if image_urls:
            submitted_at = datetime.utcnow()
            original_notes = intake_notes or None
            observation = Observation(
                site_id=site.id,
                notes=original_notes,
                damage_tags="",
                severity=1,
                human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
                reviewed_by=reviewer,
                created_at=submitted_at,
                contributor_original=build_contributor_original(
                    notes=original_notes,
                    tags=[],
                    severity=1,
                    submitted_at=submitted_at,
                ),
            )
            db.add(observation)
            db.flush()

            for image_url in image_urls:
                db.add(
                    ObservationImage(
                        observation_id=observation.id,
                        image_url=image_url,
                    )
                )

        db.commit()
        db.refresh(site)

        if observation:
            db.refresh(observation)
            image_paths = [
                image_url_to_local_path(image_url) for image_url in image_urls
            ]
            result = analyze_observation_images(
                image_paths=image_paths,
                image_ids=[image.id for image in observation.images],
                notes=build_ai_intake_notes(site, intake_notes),
            )
            apply_ai_analysis_result(observation, result)
            db.commit()
            return RedirectResponse(
                url=f"/observations/{observation.id}/ai_review",
                status_code=303,
            )

    except HTTPException:
        db.rollback()
        cleanup_saved_uploads(saved_paths)
        raise
    except Exception:
        db.rollback()
        cleanup_saved_uploads(saved_paths)
        raise

    return RedirectResponse(url=f"/sites/{site.id}", status_code=303)


@app.get("/sites/{site_id}", response_class=HTMLResponse)
def site_detail(site_id: int, request: Request, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    risk_cases = sorted(
        [obs.risk_case for obs in site.observations if obs.risk_case],
        key=lambda case: case.created_at,
        reverse=True,
    )
    latest_case = risk_cases[0] if risk_cases else None
    return templates.TemplateResponse(
        "site_detail.html",
        {
            "request": request,
            "site": site,
            "risk_cases": risk_cases,
            "latest_case": latest_case,
            "ai_reviews": {
                obs.id: extract_ai_review(obs) for obs in site.observations
            },
        },
    )


@app.post("/observations/submit")
async def observation_submit(
    _csrf: None = Depends(verify_csrf),
    site_id: int | None = Form(None),
    site_name: str = Form(""),
    site_location: str = Form(""),
    site_description: str = Form(""),
    contributor_notes: str = Form(""),
    manually_selected_tags: str = Form(""),
    severity: int = Form(...),
    response_mode: str = Form("json"),
    images: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    site = None
    if site_id is not None:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
    elif not site_name.strip():
        raise HTTPException(
            status_code=400,
            detail="Select an existing site or describe a new site.",
        )

    if severity < 1 or severity > 5:
        raise HTTPException(status_code=400, detail="Severity must be between 1 and 5.")

    uploaded_images = [image for image in images or [] if image and image.filename]
    if not uploaded_images:
        raise HTTPException(status_code=400, detail="At least one image is required.")
    if len(uploaded_images) > MAX_OBSERVATION_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload no more than {MAX_OBSERVATION_IMAGES} images.",
        )

    damage_tags = parse_damage_tags(manually_selected_tags or "")
    saved_paths: list[Path] = []
    image_urls: list[str] = []

    try:
        for image in uploaded_images:
            image_url, saved_path = await save_upload_image(image)
            image_urls.append(image_url)
            saved_paths.append(saved_path)

        if site is None:
            site = Site(
                name=site_name.strip(),
                location=site_location.strip() or None,
                description=site_description.strip() or None,
            )
            db.add(site)
            db.flush()

        public_review_status = HumanReviewStatus.PENDING
        submitted_at = datetime.utcnow()
        original_notes = contributor_notes or None
        original_tags = [tag for tag in damage_tags.split(",") if tag]
        obs = Observation(
            site_id=site.id,
            notes=original_notes,
            damage_tags=damage_tags,
            severity=severity,
            human_review_status=public_review_status,
            created_at=submitted_at,
            contributor_original=build_contributor_original(
                notes=original_notes,
                tags=original_tags,
                severity=severity,
                submitted_at=submitted_at,
            ),
        )
        db.add(obs)
        db.flush()

        for image_url in image_urls:
            db.add(ObservationImage(observation_id=obs.id, image_url=image_url))

        db.commit()
        db.refresh(obs)

    except HTTPException:
        db.rollback()
        cleanup_saved_uploads(saved_paths)
        raise
    except Exception as exc:
        db.rollback()
        cleanup_saved_uploads(saved_paths)
        raise HTTPException(
            status_code=500,
            detail="Submission could not be saved.",
        ) from exc

    if response_mode == "html":
        return RedirectResponse(
            url=f"/observations/{obs.id}/submitted",
            status_code=303,
        )

    return {
        "success": True,
        "message": "Submission received.",
        "observation_id": obs.id,
        "site_id": site.id,
        "image_count": len(image_urls),
        "image_urls": image_urls,
        "human_review_status": obs.human_review_status.value,
    }


@app.get("/observations/{obs_id}/submitted", response_class=HTMLResponse)
def observation_submission_received(
    obs_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    obs = (
        db.query(Observation)
        .options(joinedload(Observation.site), selectinload(Observation.images))
        .filter(Observation.id == obs_id)
        .first()
    )
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    return templates.TemplateResponse(
        "submission_received.html",
        {"request": request, "obs": obs, "site": obs.site},
    )


@app.get("/observations/submit", response_class=HTMLResponse)
def observation_submit_form(
    request: Request,
    site_id: int | None = None,
    db: Session = Depends(get_db),
):
    selected_site = None
    if site_id is not None:
        selected_site = db.query(Site).filter(Site.id == site_id).first()
        if not selected_site:
            raise HTTPException(status_code=404, detail="Site not found")

    sites = db.query(Site).order_by(Site.name.asc()).all()
    return templates.TemplateResponse(
        "submit_observation.html",
        {
            "request": request,
            "site": selected_site,
            "sites": sites,
            "all_tags": ALL_TAGS,
        },
    )


@app.get("/observations/review", response_class=HTMLResponse)
def observation_review_queue(
    request: Request,
    _reviewer: str = Depends(require_reviewer),
    status: str = HumanReviewStatus.PENDING.value,
    db: Session = Depends(get_db),
):
    valid_statuses = [review_status.value for review_status in HumanReviewStatus]
    show_all = status == "All"

    if not show_all and status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid human review status")

    query = (
        db.query(Observation)
        .options(
            joinedload(Observation.site),
            selectinload(Observation.images),
        )
        .order_by(Observation.created_at.desc())
    )

    if not show_all:
        query = query.filter(
            Observation.human_review_status == HumanReviewStatus(status)
        )

    observations = query.all()
    status_counts = {
        review_status.value: db.query(Observation)
        .filter(Observation.human_review_status == review_status)
        .count()
        for review_status in HumanReviewStatus
    }
    review_items = [
        {
            "observation": observation,
            "image_count": len(observation.images),
            "submitted_age": format_relative_time(observation.created_at),
        }
        for observation in observations
    ]

    return templates.TemplateResponse(
        "review_queue.html",
        {
            "request": request,
            "review_items": review_items,
            "selected_status": status,
            "review_statuses": valid_statuses,
            "status_counts": status_counts,
            "total_count": sum(status_counts.values()),
        },
    )


@app.get("/observations/{observation_id}/review", response_class=HTMLResponse)
def observation_review_action_form(
    observation_id: int,
    request: Request,
    _reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
):
    obs = (
        db.query(Observation)
        .options(
            joinedload(Observation.site),
            selectinload(Observation.images),
        )
        .filter(Observation.id == observation_id)
        .first()
    )
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")

    return templates.TemplateResponse(
        "review_action.html",
        {
            "request": request,
            "obs": obs,
            "site": obs.site,
            "all_tags": ALL_TAGS,
            "review_action_statuses": REVIEW_ACTION_STATUSES,
            "contributor_original": contributor_original(
                obs.contributor_original
            ),
        },
    )


@app.post("/observations/{observation_id}/review")
def observation_review_action(
    observation_id: int,
    reviewer: str = Depends(require_reviewer_form),
    human_review_status: str = Form(...),
    reviewer_notes: str = Form(""),
    manually_selected_tags: str = Form(""),
    severity: int = Form(...),
    analyze_after_approval: bool = Form(False),
    db: Session = Depends(get_db),
):
    obs = db.query(Observation).filter(Observation.id == observation_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")

    review_status = parse_review_action_status(human_review_status)
    if severity < 1 or severity > 5:
        raise HTTPException(status_code=400, detail="Severity must be between 1 and 5.")
    if analyze_after_approval and obs.risk_case:
        raise HTTPException(
            status_code=400,
            detail="AI analysis cannot be changed after a Risk Case is created.",
        )

    obs.human_review_status = review_status
    obs.reviewed_by = reviewer
    obs.notes = reviewer_notes or None
    obs.damage_tags = parse_damage_tags(manually_selected_tags or "")
    obs.severity = severity
    db.commit()

    if review_status == HumanReviewStatus.APPROVED_FOR_AI and analyze_after_approval:
        run_observation_analysis(obs, db)
        return RedirectResponse(
            url=f"/observations/{observation_id}/ai_review",
            status_code=303,
        )

    return RedirectResponse(url=f"/observations/{observation_id}", status_code=303)


@app.get("/observations/{obs_id}", response_class=HTMLResponse)
def observation_detail(obs_id: int, request: Request, db: Session = Depends(get_db)):
    obs = (
        db.query(Observation)
        .options(joinedload(Observation.site), selectinload(Observation.images))
        .filter(Observation.id == obs_id)
        .first()
    )
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    return templates.TemplateResponse(
        "observation_detail.html",
        {
            "request": request,
            "obs": obs,
            "site": obs.site,
            "ai_tags": extract_ai_damage_tags(obs),
            "ai_severity": extract_ai_severity(obs),
            "ai_uncertainty": extract_ai_uncertainty(obs),
            "ai_review": extract_ai_review(obs),
            "ai_result_v2": ai_schema_v2_data(obs),
            "ai_indicators": ai_v2_indicators(obs),
        },
    )


@app.post("/observations/{obs_id}/analyze")
async def observation_analyze(
    obs_id: int,
    _reviewer: str = Depends(require_reviewer_form),
    db: Session = Depends(get_db),
):
    obs = (
        db.query(Observation)
        .options(joinedload(Observation.site), selectinload(Observation.images))
        .filter(Observation.id == obs_id)
        .first()
    )
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    if obs.risk_case:
        raise HTTPException(
            status_code=400,
            detail="AI analysis cannot be changed after a Risk Case is created.",
        )

    run_observation_analysis(obs, db)
    return RedirectResponse(
        url=f"/observations/{obs_id}/ai_review",
        status_code=303,
    )


@app.get("/observations/{obs_id}/ai_review", response_class=HTMLResponse)
def observation_ai_review(
    obs_id: int,
    request: Request,
    _reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
):
    obs = (
        db.query(Observation)
        .options(
            joinedload(Observation.site),
            selectinload(Observation.images),
            selectinload(Observation.analysis_records),
        )
        .filter(Observation.id == obs_id)
        .first()
    )
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    ensure_observation_ready_for_case(obs)
    if obs.risk_case:
        raise HTTPException(
            status_code=400,
            detail="Observation already has a risk case.",
        )

    ai_tags = extract_ai_damage_tags(obs)
    ai_severity = extract_ai_severity(obs)
    selected_tags = set(obs.tags_list) | set(ai_tags)
    final_tags = [tag for tag in ALL_TAGS if tag in selected_tags]
    return templates.TemplateResponse(
        "ai_review_result.html",
        {
            "request": request,
            "obs": obs,
            "site": obs.site,
            "all_tags": ALL_TAGS,
            "ai_tags": ai_tags,
            "ai_severity": ai_severity,
            "final_severity_default": (
                ai_severity if ai_severity is not None else obs.severity
            ),
            "ai_uncertainty": extract_ai_uncertainty(obs),
            "final_tags": final_tags,
            "ai_result_v2": ai_schema_v2_data(obs),
            "ai_indicators": ai_v2_indicators(obs),
            "analysis_attempts": analysis_attempt_history(obs),
            "contributor_original": contributor_original(
                obs.contributor_original
            ),
        },
    )


@app.post("/observations/{obs_id}/create_risk_case")
def observation_create_risk_case(
    obs_id: int,
    reviewer: str = Depends(require_reviewer_form),
    final_damage_tags: list[str] = Form(default=[]),
    final_severity: int = Form(...),
    final_ai_summary: str = Form(""),
    final_recommended_action: str = Form(""),
    reviewer_final_notes: str = Form(""),
    indicator_action: list[str] = Form(default=[]),
    indicator_type: list[str] = Form(default=[]),
    indicator_severity: list[int] = Form(default=[]),
    routed_to: str = Form(""),
    db: Session = Depends(get_db),
):
    obs = db.query(Observation).filter(Observation.id == obs_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    ensure_observation_ready_for_case(obs)
    if obs.risk_case:
        raise HTTPException(
            status_code=400,
            detail="Observation already has a risk case.",
        )
    if final_severity < 1 or final_severity > 5:
        raise HTTPException(status_code=400, detail="Severity must be between 1 and 5.")

    indicator_final_tags: list[str] = []
    if indicator_action or indicator_type or indicator_severity:
        if not (
            len(indicator_action)
            == len(indicator_type)
            == len(indicator_severity)
        ):
            raise HTTPException(
                status_code=400,
                detail="Indicator review fields are incomplete.",
            )
        for action, tag, severity_value in zip(
            indicator_action,
            indicator_type,
            indicator_severity,
            strict=True,
        ):
            if action not in {"accept", "edit", "reject"}:
                raise HTTPException(status_code=400, detail="Invalid indicator action.")
            if action == "reject":
                continue
            if tag not in ALL_TAGS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported damage tag(s): {tag}",
                )
            if severity_value < 1 or severity_value > 5:
                raise HTTPException(
                    status_code=400,
                    detail="Indicator severity must be between 1 and 5.",
                )
            indicator_final_tags.append(tag)
        final_damage_tags = [
            tag for tag in ALL_TAGS if tag in set(indicator_final_tags)
        ]

    invalid_tags = [tag for tag in final_damage_tags if tag not in ALL_TAGS]
    if invalid_tags:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported damage tag(s): {', '.join(invalid_tags)}",
        )

    original_summary = obs.ai_summary or ""
    original_action = obs.ai_recommended_action or ""
    reviewed_summary = final_ai_summary.strip() or original_summary
    reviewed_action = final_recommended_action.strip() or original_action
    decision = ai_review_decision_label(
        observation=obs,
        final_tags=final_damage_tags,
        final_severity=final_severity,
        final_summary=reviewed_summary,
        final_recommended_action=reviewed_action,
    )
    review = record_ai_review_decision(
        obs,
        decision,
        reviewer,
        reviewer_final_notes,
    )

    case = create_risk_case_from_observation(
        db=db,
        observation=obs,
        final_tags=final_damage_tags,
        final_severity=final_severity,
        final_summary=reviewed_summary,
        final_recommended_action=reviewed_action,
        reviewer_decision=review,
        finalized_by=reviewer,
        routed_to=routed_to or None,
    )

    return RedirectResponse(url=f"/cases/{case.id}", status_code=303)


@app.post("/observations/{obs_id}/reject_ai_analysis")
def observation_reject_ai_analysis(
    obs_id: int,
    reviewer: str = Depends(require_reviewer_form),
    rejection_reason: str = Form(""),
    db: Session = Depends(get_db),
):
    obs = db.query(Observation).filter(Observation.id == obs_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    ensure_observation_ready_for_case(obs)
    if obs.risk_case:
        raise HTTPException(
            status_code=400,
            detail="Observation already has a risk case.",
        )

    record_ai_review_decision(obs, "Rejected", reviewer, rejection_reason)
    db.commit()
    return RedirectResponse(url=f"/observations/{obs_id}", status_code=303)


@app.post("/observations/{obs_id}/create_case")
async def observation_create_case(
    obs_id: int,
    reviewer: str = Depends(require_reviewer_form),
    db: Session = Depends(get_db),
):
    obs = db.query(Observation).filter(Observation.id == obs_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    if obs.risk_case:
        return RedirectResponse(url=f"/cases/{obs.risk_case.id}", status_code=303)

    ensure_observation_ready_for_case(obs)
    final_summary = obs.ai_summary or ""
    final_action = obs.ai_recommended_action or ""
    review = record_ai_review_decision(
        obs,
        ai_review_decision_label(
            observation=obs,
            final_tags=obs.tags_list,
            final_severity=obs.severity,
            final_summary=final_summary,
            final_recommended_action=final_action,
        ),
        reviewer,
    )
    case = create_risk_case_from_observation(
        db=db,
        observation=obs,
        final_tags=obs.tags_list,
        final_severity=obs.severity,
        final_summary=final_summary,
        final_recommended_action=final_action,
        reviewer_decision=review,
        finalized_by=reviewer,
    )

    return RedirectResponse(url=f"/cases/{case.id}", status_code=303)


@app.get("/cases", response_class=HTMLResponse)
def cases_list(
    request: Request,
    status: str = "",
    band: str = "",
    db: Session = Depends(get_db),
):
    query = db.query(RiskCase)
    if status:
        query = query.filter(RiskCase.status == status)
    if band:
        query = query.filter(RiskCase.risk_band == band)
    cases = query.order_by(RiskCase.created_at.desc()).all()
    case_items = [
        {"case": case, "snapshot": case_snapshot(case)} for case in cases
    ]
    return templates.TemplateResponse(
        "cases_list.html",
        {
            "request": request,
            "case_items": case_items,
            "statuses": RiskCase.STATUSES,
            "filter_status": status,
            "filter_band": band,
        },
    )


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail(case_id: int, request: Request, db: Session = Depends(get_db)):
    case = (
        db.query(RiskCase)
        .options(selectinload(RiskCase.events))
        .filter(RiskCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    snapshot = case_snapshot(case)
    next_statuses = allowed_next_statuses(case.status)
    return templates.TemplateResponse(
        "case_detail.html",
        {
            "request": request,
            "case": case,
            "site": snapshot["site"],
            "snapshot": snapshot,
            "next_statuses": next_statuses,
        },
    )


@app.get("/cases/{case_id}/status", response_class=HTMLResponse)
def case_status_form(
    case_id: int,
    request: Request,
    _reviewer: str = Depends(require_reviewer),
    db: Session = Depends(get_db),
):
    case = (
        db.query(RiskCase)
        .options(selectinload(RiskCase.events))
        .filter(RiskCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    snapshot = case_snapshot(case)
    next_statuses = allowed_next_statuses(case.status)
    return templates.TemplateResponse(
        "case_status.html",
        {
            "request": request,
            "case": case,
            "site": snapshot["site"],
            "snapshot": snapshot,
            "next_statuses": next_statuses,
        },
    )


@app.post("/cases/{case_id}/status")
def case_update_status(
    case_id: int,
    reviewer: str = Depends(require_reviewer_form),
    status: str = Form(...),
    routed_to: str = Form(""),
    status_note: str = Form(""),
    db: Session = Depends(get_db),
):
    case = (
        db.query(RiskCase)
        .options(selectinload(RiskCase.events))
        .filter(RiskCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if status not in RiskCase.STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    next_statuses = allowed_next_statuses(case.status)
    if status not in next_statuses:
        raise HTTPException(
            status_code=400,
            detail=invalid_transition_message(case.status, status),
        )

    routing_destination = routed_to.strip()
    if status == "Routed" and not routing_destination:
        raise HTTPException(
            status_code=400,
            detail="A routing destination is required for Routed cases.",
        )

    from_status = case.status
    case.status = status
    if status == "Routed":
        case.routed_to = routing_destination
    case.updated_at = datetime.utcnow()
    db.add(
        CaseEvent(
            case_id=case.id,
            from_status=from_status,
            to_status=status,
            reviewer=reviewer,
            note=status_note.strip() or None,
        )
    )
    db.commit()
    case.report_path = generate_report(case)
    db.commit()
    return RedirectResponse(url=f"/cases/{case_id}", status_code=303)


@app.get("/cases/{case_id}/report", response_class=HTMLResponse)
def case_report_html(case_id: int, request: Request, db: Session = Depends(get_db)):
    case = (
        db.query(RiskCase)
        .options(selectinload(RiskCase.events))
        .filter(RiskCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    snapshot = case_snapshot(case)
    case.report_path = generate_report(case)
    db.commit()

    report_file = Path(case.report_path) if case.report_path else None
    md_content = ""
    if report_file and report_file.exists():
        md_content = report_file.read_text(encoding="utf-8")

    return templates.TemplateResponse(
        "case_report.html",
        {
            "request": request,
            "case": case,
            "site": snapshot["site"],
            "snapshot": snapshot,
            "md_content": md_content,
        },
    )


@app.get("/cases/{case_id}/report.md")
def case_report_md(case_id: int, db: Session = Depends(get_db)):
    case = (
        db.query(RiskCase)
        .options(selectinload(RiskCase.events))
        .filter(RiskCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Report not found")
    case.report_path = generate_report(case)
    db.commit()
    report_file = Path(case.report_path)
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Report file missing")
    return FileResponse(
        report_file,
        media_type="text/markdown",
        filename=report_file.name,
    )
