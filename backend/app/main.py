import uuid
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, get_db, Base
from app.models import Site, Observation, RiskCase
from app.risk import calculate_risk, ALL_TAGS, TAG_LABELS
from app.reports import generate_report
from app.config import settings
from app.services.ai_analysis import analyze_observation_image

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = REPO_ROOT / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# ── App setup ──────────────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

app = FastAPI(title="HeritageRisk AI", version="0.1.0")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Make TAG_LABELS available in every template without passing it explicitly
templates.env.globals["TAG_LABELS"] = TAG_LABELS


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── Seed (idempotent demo data) ────────────────────────────────────────────────

@app.post("/seed")
def seed_data(db: Session = Depends(get_db)):
    from app.seed import seed
    result = seed(db)
    return RedirectResponse(url="/?seeded=1", status_code=303)


# ── Dashboard / Home ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.created_at.desc()).all()
    all_cases = db.query(RiskCase).order_by(RiskCase.created_at.desc()).all()
    all_obs = db.query(Observation).order_by(Observation.created_at.desc()).all()

    high_risk_cases = [c for c in all_cases if c.risk_band == "High"]
    needs_attention = [
        c for c in all_cases if c.status in ("Draft", "Needs Review")
    ]
    recent_cases = all_cases[:8]
    recent_obs = all_obs[:6]

    seeded = request.query_params.get("seeded") == "1"

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "sites": sites,
            "total_sites": len(sites),
            "total_obs": len(all_obs),
            "total_cases": len(all_cases),
            "high_risk_count": len(high_risk_cases),
            "needs_attention_count": len(needs_attention),
            "recent_cases": recent_cases,
            "recent_obs": recent_obs,
            "seeded": seeded,
        },
    )


# ── Sites ──────────────────────────────────────────────────────────────────────

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
def site_create(
    request: Request,
    name: str = Form(...),
    location: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    site = Site(name=name, location=location or None, description=description or None)
    db.add(site)
    db.commit()
    db.refresh(site)
    return RedirectResponse(url=f"/sites/{site.id}", status_code=303)


@app.get("/sites/{site_id}", response_class=HTMLResponse)
def site_detail(site_id: int, request: Request, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return templates.TemplateResponse(
        "site_detail.html", {"request": request, "site": site}
    )


# ── Observations ───────────────────────────────────────────────────────────────

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

    image_filename = None
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise HTTPException(status_code=400, detail="Only JPG, PNG, or WEBP images allowed")
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOADS_DIR / unique_name
        content = await image.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image must be under 10 MB")
        dest.write_bytes(content)
        image_filename = unique_name

    obs = Observation(
        site_id=site_id,
        image_filename=image_filename,
        notes=notes or None,
        damage_tags=",".join(damage_tags),
        severity=max(1, min(5, severity)),
    )
    db.add(obs)
    db.commit()
    db.refresh(obs)
    return RedirectResponse(url=f"/sites/{site_id}", status_code=303)


@app.get("/observations/{obs_id}", response_class=HTMLResponse)
def observation_detail(obs_id: int, request: Request, db: Session = Depends(get_db)):
    obs = db.query(Observation).filter(Observation.id == obs_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    return templates.TemplateResponse(
        "observation_detail.html", {"request": request, "obs": obs, "site": obs.site}
    )


@app.post("/observations/{obs_id}/analyze")
def observation_analyze(obs_id: int, db: Session = Depends(get_db)):
    obs = db.query(Observation).filter(Observation.id == obs_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")

    image_path = str(UPLOADS_DIR / obs.image_filename) if obs.image_filename else ""

    result = analyze_observation_image(image_path=image_path, notes=obs.notes)

    azure_failed = (
        result.provider == "azure_openai"
        and result.confidence == 0
        and result.damage_tags == ["other"]
    )

    if azure_failed:
        obs.ai_analysis_status = "failed"
    elif result.provider == "mock":
        obs.ai_analysis_status = "mock"
    else:
        obs.ai_analysis_status = "complete"

    obs.ai_summary = result.summary
    obs.ai_confidence = result.confidence
    obs.ai_provider = result.provider
    obs.ai_recommended_action = result.recommended_action
    obs.ai_raw_response = result.raw_response

    if not azure_failed:
        existing = set(obs.tags_list)
        merged = list(existing | set(result.damage_tags))
        obs.damage_tags = ",".join(sorted(merged))

    db.commit()
    return RedirectResponse(url=f"/observations/{obs_id}", status_code=303)


@app.post("/observations/{obs_id}/create_case")
def observation_create_case(obs_id: int, db: Session = Depends(get_db)):
    obs = db.query(Observation).filter(Observation.id == obs_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    if obs.risk_case:
        return RedirectResponse(url=f"/cases/{obs.risk_case.id}", status_code=303)

    score, band = calculate_risk(obs.tags_list, obs.severity)
    case = RiskCase(observation_id=obs.id, risk_score=score, risk_band=band)
    db.add(case)
    db.commit()
    db.refresh(case)

    report_path = generate_report(case, obs, obs.site)
    case.report_path = report_path
    db.commit()

    return RedirectResponse(url=f"/cases/{case.id}", status_code=303)


# ── Cases ──────────────────────────────────────────────────────────────────────

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
    return templates.TemplateResponse(
        "case_detail.html",
        {
            "request": request,
            "case": case,
            "obs": case.observation,
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
    case.status = status
    case.routed_to = routed_to or None
    case.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/cases/{case_id}", status_code=303)


@app.get("/cases/{case_id}/report", response_class=HTMLResponse)
def case_report_html(case_id: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(RiskCase).filter(RiskCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    obs = case.observation
    site = obs.site

    generate_report(case, obs, site)

    report_file = Path(case.report_path) if case.report_path else None
    md_content = report_file.read_text(encoding="utf-8") if report_file and report_file.exists() else ""

    return templates.TemplateResponse(
        "case_report.html",
        {"request": request, "case": case, "md_content": md_content},
    )


@app.get("/cases/{case_id}/report.md")
def case_report_md(case_id: int, db: Session = Depends(get_db)):
    case = db.query(RiskCase).filter(RiskCase.id == case_id).first()
    if not case or not case.report_path:
        raise HTTPException(status_code=404, detail="Report not found")
    report_file = Path(case.report_path)
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Report file missing")
    return FileResponse(report_file, media_type="text/markdown", filename=report_file.name)
