import io
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.auth_helpers import (
    TEST_REVIEWER_USERNAME,
    configure_test_reviewer,
    login_reviewer,
    post_form,
    restore_test_reviewer,
)
from tests.image_helpers import TINY_PNG


@pytest.fixture()
def auth_context(tmp_path):
    from app.database import Base, get_db
    import app.main as main_module
    from app.main import app
    from app.models import HumanReviewStatus, Observation, Site
    from app.provenance import build_contributor_original
    import app.reports as reports_module

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    connection = test_engine.connect()
    Base.metadata.create_all(bind=connection)
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection,
    )

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_uploads_dir = main_module.UPLOADS_DIR
    original_reports_dir = reports_module.REPORTS_DIR
    main_module.UPLOADS_DIR = tmp_path / "uploads"
    reports_module.REPORTS_DIR = tmp_path / "reports"
    main_module.UPLOADS_DIR.mkdir()
    reports_module.REPORTS_DIR.mkdir()

    db = TestSessionLocal()
    site = Site(name="Reviewer Auth Test Site", location="Test Square")
    db.add(site)
    db.flush()
    submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    observation = Observation(
        site_id=site.id,
        notes="Contributor evidence awaiting review.",
        damage_tags="crack",
        severity=2,
        human_review_status=HumanReviewStatus.PENDING,
        contributor_original=build_contributor_original(
            notes="Contributor evidence awaiting review.",
            tags=["crack"],
            severity=2,
            submitted_at=submitted_at,
        ),
        created_at=submitted_at,
    )
    db.add(observation)
    db.commit()

    reviewer_settings = configure_test_reviewer()
    client = TestClient(app, raise_server_exceptions=True)
    yield {
        "client": client,
        "db": db,
        "site_id": site.id,
        "observation_id": observation.id,
    }

    db.close()
    restore_test_reviewer(reviewer_settings)
    app.dependency_overrides.pop(get_db, None)
    main_module.UPLOADS_DIR = original_uploads_dir
    reports_module.REPORTS_DIR = original_reports_dir
    connection.close()


@pytest.mark.parametrize(
    "path",
    [
        "/sites/new",
        "/observations/review",
        "/observations/1/review",
        "/observations/1/ai_review",
        "/cases/1/status",
    ],
)
def test_guarded_get_routes_redirect_logged_out(auth_context, path):
    response = auth_context["client"].get(path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/reviewer/login?")


@pytest.mark.parametrize(
    ("path", "data"),
    [
        ("/reviewer/logout", {}),
        ("/seed", {}),
        ("/sites", {"name": "Unauthorized Site"}),
        (
            "/observations/1/review",
            {
                "human_review_status": "ApprovedForAI",
                "reviewer_notes": "Unauthorized edit.",
                "severity": "2",
            },
        ),
        ("/observations/1/analyze", {}),
        (
            "/observations/1/create_risk_case",
            {"final_damage_tags": ["crack"], "final_severity": "2"},
        ),
        (
            "/observations/1/reject_ai_analysis",
            {"rejection_reason": "Unauthorized rejection."},
        ),
        ("/observations/1/create_case", {}),
        ("/cases/1/status", {"status": "Verified"}),
    ],
)
def test_guarded_post_routes_redirect_logged_out(auth_context, path, data):
    response = auth_context["client"].post(
        path,
        data=data,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/reviewer/login?")


def test_logged_out_analysis_never_invokes_analyzer(auth_context):
    observation_id = auth_context["observation_id"]

    with patch("app.main.analyze_observation_images") as analyze_mock:
        response = auth_context["client"].post(
            f"/observations/{observation_id}/analyze",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/reviewer/login?")
    analyze_mock.assert_not_called()


def test_authenticated_form_without_csrf_is_rejected(auth_context):
    from app.models import HumanReviewStatus, Observation

    client = auth_context["client"]
    observation_id = auth_context["observation_id"]
    login_reviewer(client)

    response = client.post(
        f"/observations/{observation_id}/review",
        data={
            "human_review_status": "ApprovedForAI",
            "reviewer_notes": "This must not be saved.",
            "manually_selected_tags": "crack",
            "severity": "2",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid or missing CSRF token."
    db = auth_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation_id).one()
    assert observation.human_review_status == HumanReviewStatus.PENDING
    assert observation.reviewed_by is None
    assert observation.notes == "Contributor evidence awaiting review."


def test_public_submission_works_logged_out_and_stays_pending(auth_context):
    from app.models import HumanReviewStatus, Observation

    client = auth_context["client"]
    response = post_form(
        client,
        "/observations/submit",
        data={
            "site_id": str(auth_context["site_id"]),
            "contributor_notes": "Logged-out public evidence.",
            "manually_selected_tags": "water_staining",
            "severity": "3",
        },
        files=[("images", ("public.png", io.BytesIO(TINY_PNG), "image/png"))],
    )

    assert response.status_code == 200
    assert response.json()["human_review_status"] == "Pending"
    db = auth_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter_by(
        id=response.json()["observation_id"]
    ).one()
    assert observation.human_review_status == HumanReviewStatus.PENDING
    assert observation.reviewed_by is None

    queue = client.get("/observations/review", follow_redirects=False)
    assert queue.status_code == 303
    assert queue.headers["location"].startswith("/reviewer/login?")


def test_reviewer_identity_is_persisted_and_rendered(auth_context):
    from app.models import Observation, RiskCase
    from app.services.ai_analysis import AIAnalysisResult

    client = auth_context["client"]
    observation_id = auth_context["observation_id"]
    login_reviewer(client)
    result = AIAnalysisResult(
        damage_tags=["crack"],
        severity=3,
        confidence=45,
        summary="Mock proposal for reviewer identity testing.",
        recommended_action="Human review is required before action.",
        provider="mock",
        raw_response='{"source":"identity-test"}',
        uncertainty="Mock output requires human verification.",
    )

    with patch("app.main.analyze_observation_images", return_value=result):
        reviewed = post_form(
            client,
            f"/observations/{observation_id}/review",
            data={
                "human_review_status": "ApprovedForAI",
                "reviewer_notes": "Privacy and evidence checked.",
                "manually_selected_tags": "crack",
                "severity": "3",
                "analyze_after_approval": "true",
            },
            follow_redirects=False,
        )
    assert reviewed.status_code == 303

    finalized = post_form(
        client,
        f"/observations/{observation_id}/create_risk_case",
        data={
            "final_damage_tags": ["crack"],
            "final_severity": "3",
            "final_ai_summary": "Reviewer-confirmed visible crack evidence.",
            "reviewer_final_notes": "Final evidence checked.",
        },
        follow_redirects=False,
    )
    assert finalized.status_code == 303
    case_id = int(finalized.headers["location"].rsplit("/", 1)[-1])

    db = auth_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation_id).one()
    case = db.query(RiskCase).filter_by(id=case_id).one()
    assert observation.reviewed_by == TEST_REVIEWER_USERNAME
    assert observation.ai_review_decision["reviewed_by"] == (
        TEST_REVIEWER_USERNAME
    )
    assert case.finalized_by == TEST_REVIEWER_USERNAME
    assert case.final_snapshot["reviewed_by"] == TEST_REVIEWER_USERNAME
    assert case.final_snapshot["finalized_by"] == TEST_REVIEWER_USERNAME

    case_page = client.get(f"/cases/{case_id}")
    html_report = client.get(f"/cases/{case_id}/report")
    markdown_report = client.get(f"/cases/{case_id}/report.md")
    assert case_page.status_code == 200
    assert html_report.status_code == 200
    assert markdown_report.status_code == 200
    assert TEST_REVIEWER_USERNAME in case_page.text
    assert TEST_REVIEWER_USERNAME in html_report.text
    assert f"**Reviewed by:** {TEST_REVIEWER_USERNAME}" in markdown_report.text
    assert f"**Finalized by:** {TEST_REVIEWER_USERNAME}" in markdown_report.text


def test_logout_ends_reviewer_access(auth_context):
    client = auth_context["client"]
    login_reviewer(client)
    assert client.get("/observations/review").status_code == 200

    logout = post_form(
        client,
        "/reviewer/logout",
        follow_redirects=False,
    )
    assert logout.status_code == 303
    assert logout.headers["location"] == "/reviewer/login"

    after_logout = client.get("/observations/review", follow_redirects=False)
    assert after_logout.status_code == 303
    assert after_logout.headers["location"].startswith("/reviewer/login?")
