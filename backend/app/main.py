import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import apply_sqlite_startup_migrations, engine, get_db, Base
from app.models import (
    HumanReviewStatus,
    Observation,
    ObservationImage,
    RiskCase,
    Site,
)
from app.risk import calculate_risk, calculate_risk_breakdown, ALL_TAGS, TAG_LABELS
from app.reports import generate_report
from app.config import settings
from app.services.ai_analysis import (
    AIAnalysisResult,
    analyze_observation_image,
    analyze_observation_images,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = REPO_ROOT / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
MAX_OBSERVATION_IMAGES = 6

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

Base.metadata.create_all(bind=engine)
apply_sqlite_startup_migrations(engine)

app = FastAPI(title="HeritageRisk AI", version="0.1.0")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["TAG_LABELS"] = TAG_LABELS

REVIEW_ACTION_STATUSES = (
    HumanReviewStatus.APPROVED_FOR_AI,
    HumanReviewStatus.REJECTED,
    HumanReviewStatus.SENSITIVE,
)


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

    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image cannot be empty.")
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be 10 MB or smaller.")

    unique_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = UPLOADS_DIR / unique_name
    saved_path.write_bytes(content)
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


def extract_ai_damage_tags(observation: Observation) -> list[str]:
    raw_tags = ai_raw_data(observation).get("damage_tags", [])
    if not isinstance(raw_tags, list):
        return []
    return [
        tag
        for tag in raw_tags
        if isinstance(tag, str) and tag in ALL_TAGS
    ]


def extract_ai_severity(observation: Observation) -> int:
    raw_severity = ai_raw_data(observation).get("severity")
    try:
        return max(1, min(5, int(raw_severity)))
    except (TypeError, ValueError):
        return observation.severity


def extract_ai_uncertainty(observation: Observation) -> str:
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
    review = ai_raw_data(observation).get("human_ai_review", {})
    return review if isinstance(review, dict) else {}


def ensure_observation_approved_for_ai(observation: Observation) -> None:
    if observation.human_review_status != HumanReviewStatus.APPROVED_FOR_AI:
        raise HTTPException(
            status_code=403,
            detail=(
                "Observation must be approved by a human reviewer before AI "
                "analysis."
            ),
        )


def ensure_observation_ready_for_case(observation: Observation) -> None:
    ensure_observation_approved_for_ai(observation)
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
    routed_to: str | None = None,
) -> RiskCase:
    observation.damage_tags = ",".join(final_tags)
    observation.severity = final_severity

    score, band = calculate_risk(observation.tags_list, observation.severity)
    case = RiskCase(
        observation_id=observation.id,
        risk_score=score,
        risk_band=band,
        routed_to=routed_to,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    report_path = generate_report(case, observation, observation.site)
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
    azure_failed = (
        result.provider == "azure_openai"
        and result.confidence == 0
        and result.damage_tags == ["other"]
    )

    if azure_failed:
        observation.ai_analysis_status = "failed"
    elif result.provider == "mock":
        observation.ai_analysis_status = "mock"
    else:
        observation.ai_analysis_status = "complete"

    observation.ai_summary = result.summary
    observation.ai_confidence = result.confidence
    observation.ai_provider = result.provider
    observation.ai_recommended_action = result.recommended_action

    existing_raw_data = ai_raw_data(observation)
    review_history = existing_raw_data.get("human_ai_review_history", [])
    if not isinstance(review_history, list):
        review_history = []
    previous_review = existing_raw_data.get("human_ai_review")
    if isinstance(previous_review, dict):
        review_history.append(previous_review)

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
    if review_history:
        raw_data["human_ai_review_history"] = review_history
    observation.ai_raw_response = json.dumps(raw_data)


def record_ai_review_decision(
    observation: Observation,
    decision: str,
    reviewer_notes: str = "",
) -> None:
    raw_data = ai_raw_data(observation)
    existing_review = raw_data.get("human_ai_review")
    if isinstance(existing_review, dict):
        history = raw_data.get("human_ai_review_history", [])
        if not isinstance(history, list):
            history = []
        history.append(existing_review)
        raw_data["human_ai_review_history"] = history
    raw_data["human_ai_review"] = {
        "decision": decision,
        "reviewer_notes": reviewer_notes.strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    observation.ai_raw_response = json.dumps(raw_data)


def run_observation_analysis(observation: Observation, db: Session) -> None:
    ensure_observation_approved_for_ai(observation)
    image_paths = [
        image_url_to_local_path(image.image_url)
        for image in observation.images
    ]
    result = analyze_observation_images(
        image_paths=image_paths,
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


@app.post("/seed")
def seed_data(db: Session = Depends(get_db)):
    from app.seed import seed
    seed(db)
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
def site_new_form(request: Request):
    return templates.TemplateResponse("site_new.html", {"request": request})


@app.post("/sites")
async def site_create(
    request: Request,
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
            observation = Observation(
                site_id=site.id,
                notes=intake_notes or None,
                damage_tags="",
                severity=1,
                human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
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
        },
    )


@app.get("/sites/{site_id}/observations/new", response_class=HTMLResponse)
def observation_new_form(site_id: int, request: Request, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return templates.TemplateResponse(
        "observation_new.html",
        {"request": request, "site": site, "all_tags": ALL_TAGS},
    )


@app.post("/sites/{site_id}/observations")
async def observation_create(
    site_id: int,
    notes: str = Form(""),
    damage_tags: list[str] = Form(default=[]),
    severity: int = Form(1),
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    image_url = None
    saved_paths: list[Path] = []
    if image and image.filename:
        image_url, saved_path = await save_upload_image(image)
        saved_paths.append(saved_path)

    try:
        obs = Observation(
            site_id=site_id,
            notes=notes or None,
            damage_tags=",".join(damage_tags),
            severity=max(1, min(5, severity)),
            human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
        )
        db.add(obs)
        db.flush()

        if image_url:
            db.add(ObservationImage(observation_id=obs.id, image_url=image_url))

        db.commit()
        db.refresh(obs)
    except Exception:
        db.rollback()
        cleanup_saved_uploads(saved_paths)
        raise

    return RedirectResponse(url=f"/sites/{site_id}", status_code=303)


@app.post("/observations/submit")
async def observation_submit(
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
        obs = Observation(
            site_id=site.id,
            notes=contributor_notes or None,
            damage_tags=damage_tags,
            severity=severity,
            human_review_status=public_review_status,
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
        },
    )


@app.post("/observations/{observation_id}/review")
def observation_review_action(
    observation_id: int,
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

    obs.human_review_status = review_status
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
        },
    )


@app.post("/observations/{obs_id}/analyze")
def observation_analyze(obs_id: int, db: Session = Depends(get_db)):
    obs = (
        db.query(Observation)
        .options(joinedload(Observation.site), selectinload(Observation.images))
        .filter(Observation.id == obs_id)
        .first()
    )
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    ensure_observation_approved_for_ai(obs)
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
def observation_ai_review(obs_id: int, request: Request, db: Session = Depends(get_db)):
    obs = (
        db.query(Observation)
        .options(
            joinedload(Observation.site),
            selectinload(Observation.images),
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
            "ai_severity": extract_ai_severity(obs),
            "ai_uncertainty": extract_ai_uncertainty(obs),
            "final_tags": final_tags,
        },
    )


@app.post("/observations/{obs_id}/create_risk_case")
def observation_create_risk_case(
    obs_id: int,
    final_damage_tags: list[str] = Form(default=[]),
    final_severity: int = Form(...),
    final_ai_summary: str = Form(""),
    final_recommended_action: str = Form(""),
    reviewer_final_notes: str = Form(""),
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
    obs.ai_summary = reviewed_summary
    obs.ai_recommended_action = reviewed_action
    decision = (
        "Edited and accepted"
        if reviewed_summary != original_summary or reviewed_action != original_action
        else "Accepted"
    )
    record_ai_review_decision(obs, decision, reviewer_final_notes)

    case = create_risk_case_from_observation(
        db=db,
        observation=obs,
        final_tags=final_damage_tags,
        final_severity=final_severity,
        routed_to=routed_to or None,
    )

    return RedirectResponse(url=f"/cases/{case.id}", status_code=303)


@app.post("/observations/{obs_id}/reject_ai_analysis")
def observation_reject_ai_analysis(
    obs_id: int,
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

    record_ai_review_decision(obs, "Rejected", rejection_reason)
    obs.ai_analysis_status = "rejected"
    db.commit()
    return RedirectResponse(url=f"/observations/{obs_id}", status_code=303)


@app.post("/observations/{obs_id}/create_case")
def observation_create_case(obs_id: int, db: Session = Depends(get_db)):
    obs = db.query(Observation).filter(Observation.id == obs_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    if obs.risk_case:
        return RedirectResponse(url=f"/cases/{obs.risk_case.id}", status_code=303)

    ensure_observation_ready_for_case(obs)
    case = create_risk_case_from_observation(
        db=db,
        observation=obs,
        final_tags=obs.tags_list,
        final_severity=obs.severity,
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
    return templates.TemplateResponse(
        "cases_list.html",
        {
            "request": request,
            "cases": cases,
            "statuses": RiskCase.STATUSES,
            "filter_status": status,
            "filter_band": band,
        },
    )


@app.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail(case_id: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(RiskCase).filter(RiskCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    obs = case.observation
    risk_breakdown = calculate_risk_breakdown(obs.tags_list, obs.severity)
    return templates.TemplateResponse(
        "case_detail.html",
        {
            "request": request,
            "case": case,
            "obs": obs,
            "site": obs.site,
            "risk_breakdown": risk_breakdown,
        },
    )


@app.get("/cases/{case_id}/status", response_class=HTMLResponse)
def case_status_form(case_id: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(RiskCase).filter(RiskCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return templates.TemplateResponse(
        "case_status.html",
        {
            "request": request,
            "case": case,
            "site": case.observation.site,
        },
    )


@app.post("/cases/{case_id}/status")
def case_update_status(
    case_id: int,
    status: str = Form(...),
    routed_to: str = Form(""),
    db: Session = Depends(get_db),
):
    case = db.query(RiskCase).filter(RiskCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if status not in RiskCase.STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    if status == "Routed" and not routed_to.strip():
        raise HTTPException(
            status_code=400,
            detail="A routing destination is required for Routed cases.",
        )
    case.status = status
    case.routed_to = routed_to or None
    case.updated_at = datetime.utcnow()
    db.commit()
    case.report_path = generate_report(
        case,
        case.observation,
        case.observation.site,
    )
    db.commit()
    return RedirectResponse(url=f"/cases/{case_id}", status_code=303)


@app.get("/cases/{case_id}/report", response_class=HTMLResponse)
def case_report_html(case_id: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(RiskCase).filter(RiskCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.report_path = generate_report(
        case,
        case.observation,
        case.observation.site,
    )
    db.commit()

    report_file = Path(case.report_path) if case.report_path else None
    md_content = ""
    if report_file and report_file.exists():
        md_content = report_file.read_text(encoding="utf-8")

    observation = case.observation
    risk_breakdown = calculate_risk_breakdown(
        observation.tags_list,
        observation.severity,
    )

    return templates.TemplateResponse(
        "case_report.html",
        {
            "request": request,
            "case": case,
            "obs": observation,
            "site": observation.site,
            "risk_breakdown": risk_breakdown,
            "ai_tags": extract_ai_damage_tags(observation),
            "ai_severity": extract_ai_severity(observation),
            "ai_uncertainty": extract_ai_uncertainty(observation),
            "md_content": md_content,
        },
    )


@app.get("/cases/{case_id}/report.md")
def case_report_md(case_id: int, db: Session = Depends(get_db)):
    case = db.query(RiskCase).filter(RiskCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Report not found")
    case.report_path = generate_report(
        case,
        case.observation,
        case.observation.site,
    )
    db.commit()
    report_file = Path(case.report_path)
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Report file missing")
    return FileResponse(
        report_file,
        media_type="text/markdown",
        filename=report_file.name,
    )
