"""
MVP smoke tests for HeritageRisk AI.

Covers the full happy-path flow in order:
  dashboard → site list → seed → create site → site detail →
  upload observation → observation detail → AI analyze →
  create case → case list → case detail → update status →
  HTML report → Markdown report download.

Uses an in-memory SQLite DB so no real data is touched.
AI analysis runs in mock mode (AI_ANALYSIS_ENABLED=false by default).
Image uploads and report files are redirected to pytest tmp dirs.
"""

import io
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Tiny valid 1×1 white pixel PNG — no Pillow required
# ---------------------------------------------------------------------------
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Module-scoped fixtures — shared across all tests in this file
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_and_client(tmp_path_factory):
    """
    Set up an isolated in-memory SQLite DB and a FastAPI TestClient.

    Uses a single shared connection so the in-memory DB persists across
    all requests made by the TestClient (SQLite :memory: is per-connection).
    Patches UPLOADS_DIR and REPORTS_DIR to temp dirs for the whole module.
    """
    from app.main import app
    from app.database import Base, get_db
    import app.main as main_module
    import app.reports as reports_module

    # Temp dirs for file I/O
    uploads_tmp = tmp_path_factory.mktemp("uploads")
    reports_tmp = tmp_path_factory.mktemp("reports")

    # Single shared connection keeps the in-memory DB alive across all requests
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Use a single connection so all sessions share the same in-memory state
    connection = test_engine.connect()
    Base.metadata.create_all(bind=connection)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)

    # Dependency override: every request uses the shared connection's session
    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Patch path constants so uploads and reports go to temp dirs
    orig_uploads = main_module.UPLOADS_DIR
    orig_reports = reports_module.REPORTS_DIR
    main_module.UPLOADS_DIR = uploads_tmp
    reports_module.REPORTS_DIR = reports_tmp

    client = TestClient(app, raise_server_exceptions=True)
    # A direct session for test assertions (same connection = same data)
    db = TestSessionLocal()

    yield {"client": client, "db": db}

    # Teardown
    db.close()
    connection.close()
    app.dependency_overrides.pop(get_db, None)
    main_module.UPLOADS_DIR = orig_uploads
    reports_module.REPORTS_DIR = orig_reports


@pytest.fixture(scope="module")
def state():
    """Shared dict for passing IDs between ordered tests."""
    return {}


# ---------------------------------------------------------------------------
# Tests 01–14 — run in order, each builds on the previous
# ---------------------------------------------------------------------------

def test_01_dashboard(db_and_client, state):
    """GET / should return an HTML dashboard with 200."""
    r = db_and_client["client"].get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_02_sites_list(db_and_client, state):
    """GET /sites should return an HTML site list with 200."""
    r = db_and_client["client"].get("/sites")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_03_seed(db_and_client, state):
    """POST /seed should redirect (303) and eventually land on the dashboard."""
    client = db_and_client["client"]
    # Don't follow redirects — just confirm the 303 and Location header
    r = client.post("/seed", allow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/?seeded=1"

    # Follow through to confirm the final page is 200
    r2 = client.get("/?seeded=1")
    assert r2.status_code == 200


def test_04_create_site(db_and_client, state):
    """POST /sites with a site name should redirect to /sites/{id}."""
    client = db_and_client["client"]
    r = client.post(
        "/sites",
        data={"name": "Test Site", "location": "Test City", "description": "A test heritage site"},
        allow_redirects=False,
    )
    assert r.status_code == 303
    location = r.headers["location"]
    # e.g. /sites/3  (seed may have added earlier ones)
    assert location.startswith("/sites/")
    site_id = int(location.split("/")[-1])
    assert site_id > 0
    state["site_id"] = site_id


def test_05_site_detail(db_and_client, state):
    """GET /sites/{id} should return the site detail page."""
    site_id = state["site_id"]
    r = db_and_client["client"].get(f"/sites/{site_id}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Test Site" in r.text


def test_06_upload_observation(db_and_client, state):
    """POST /sites/{site_id}/observations with a PNG image should redirect to /sites/{site_id}."""
    client = db_and_client["client"]
    site_id = state["site_id"]

    # Send a multipart form with our tiny valid PNG
    r = client.post(
        f"/sites/{site_id}/observations",
        data={"notes": "Some cracks visible", "severity": "3", "damage_tags": ["crack"]},
        files={"image": ("test.png", io.BytesIO(TINY_PNG), "image/png")},
        allow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/sites/{site_id}"

    # Retrieve the observation ID from the DB
    from app.models import Observation
    db = db_and_client["db"]
    obs = db.query(Observation).filter(Observation.site_id == site_id).first()
    assert obs is not None
    state["obs_id"] = obs.id


def test_07_observation_detail(db_and_client, state):
    """GET /observations/{obs_id} should return the observation detail page."""
    obs_id = state["obs_id"]
    r = db_and_client["client"].get(f"/observations/{obs_id}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_08_analyze_observation(db_and_client, state):
    """POST /observations/{obs_id}/analyze should run mock AI and redirect back."""
    client = db_and_client["client"]
    obs_id = state["obs_id"]

    # AI_ANALYSIS_ENABLED is false by default, so the mock provider is used —
    # no Azure calls are made.
    r = client.post(f"/observations/{obs_id}/analyze", allow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/observations/{obs_id}"

    # Confirm the observation now has ai_analysis_status set (mock or complete)
    from app.models import Observation
    db = db_and_client["db"]
    db.expire_all()  # reload from DB
    obs = db.query(Observation).filter(Observation.id == obs_id).first()
    assert obs.ai_analysis_status in ("mock", "complete", "failed")


def test_09_create_case(db_and_client, state):
    """POST /observations/{obs_id}/create_case should create a RiskCase and redirect to /cases/{id}."""
    client = db_and_client["client"]
    obs_id = state["obs_id"]

    r = client.post(f"/observations/{obs_id}/create_case", allow_redirects=False)
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith("/cases/")
    case_id = int(location.split("/")[-1])
    assert case_id > 0
    state["case_id"] = case_id


def test_10_cases_list(db_and_client, state):
    """GET /cases should return the HTML case list with 200."""
    r = db_and_client["client"].get("/cases")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_11_case_detail(db_and_client, state):
    """GET /cases/{case_id} should return the case detail page."""
    case_id = state["case_id"]
    r = db_and_client["client"].get(f"/cases/{case_id}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_12_update_case_status(db_and_client, state):
    """POST /cases/{case_id}/status with status=Verified should redirect back to the case."""
    client = db_and_client["client"]
    case_id = state["case_id"]

    r = client.post(
        f"/cases/{case_id}/status",
        data={"status": "Verified"},
        allow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/cases/{case_id}"

    # Confirm status was saved
    from app.models import RiskCase
    db = db_and_client["db"]
    db.expire_all()
    case = db.query(RiskCase).filter(RiskCase.id == case_id).first()
    assert case.status == "Verified"


def test_13_report_html(db_and_client, state):
    """GET /cases/{case_id}/report should return an HTML report page with 200."""
    case_id = state["case_id"]
    r = db_and_client["client"].get(f"/cases/{case_id}/report")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # The report page should contain the case ID somewhere
    assert str(case_id) in r.text


def test_14_report_md(db_and_client, state):
    """GET /cases/{case_id}/report.md should return the Markdown file as a download."""
    case_id = state["case_id"]
    r = db_and_client["client"].get(f"/cases/{case_id}/report.md")
    assert r.status_code == 200
    # Content-type should indicate markdown or octet-stream
    content_type = r.headers.get("content-type", "")
    assert "markdown" in content_type or "text" in content_type or "octet" in content_type
    # The Markdown content should start with the HeritageRisk header
    assert "HeritageRisk AI Evidence Report" in r.text
