import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def ai_review_context(tmp_path):
    from app.database import Base, get_db
    from app.main import app
    import app.reports as reports_module
    from app.models import HumanReviewStatus, Observation, ObservationImage, Site

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    connection = test_engine.connect()
    Base.metadata.create_all(bind=connection)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_reports_dir = reports_module.REPORTS_DIR
    reports_module.REPORTS_DIR = tmp_path

    db = TestSessionLocal()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    site = Site(
        name="AI Review Test Site",
        location="Test Location",
        description="Used for AI review tests.",
        created_at=now,
    )
    db.add(site)
    db.flush()

    analyzed_observation = Observation(
        site_id=site.id,
        notes="Contributor notes mention cracking and staining.",
        damage_tags="crack,water_staining",
        severity=3,
        human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
        ai_analysis_status="mock",
        ai_summary="AI summary: crack and erosion indicators are visible.",
        ai_confidence=72,
        ai_provider="mock",
        ai_recommended_action="Human review required before routing.",
        ai_raw_response=json.dumps(
            {
                "damage_tags": ["crack", "erosion"],
                "severity": 4,
                "confidence": 72,
                "summary": "AI summary: crack and erosion indicators are visible.",
                "uncertainty": "The upper wall is partly obscured.",
                "recommended_action": "Human review required before routing.",
            }
        ),
        created_at=now,
    )
    no_ai_observation = Observation(
        site_id=site.id,
        notes="Observation with no AI summary.",
        damage_tags="graffiti",
        severity=2,
        human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
        ai_analysis_status="not_run",
        ai_summary=None,
        created_at=now,
    )
    db.add_all([analyzed_observation, no_ai_observation])
    db.flush()
    analyzed_id = analyzed_observation.id
    no_ai_id = no_ai_observation.id

    db.add_all(
        [
            ObservationImage(
                observation_id=analyzed_id,
                image_url="/uploads/ai-review-one.png",
            ),
            ObservationImage(
                observation_id=analyzed_id,
                image_url="/uploads/ai-review-two.png",
            ),
        ]
    )
    db.commit()

    client = TestClient(app, raise_server_exceptions=True)

    yield {
        "client": client,
        "db": db,
        "analyzed_observation_id": analyzed_id,
        "no_ai_observation_id": no_ai_id,
    }

    db.close()
    app.dependency_overrides.pop(get_db, None)
    reports_module.REPORTS_DIR = original_reports_dir
    connection.close()


def test_ai_review_page_shows_original_evidence_and_ai_output(ai_review_context):
    observation_id = ai_review_context["analyzed_observation_id"]

    response = ai_review_context["client"].get(
        f"/observations/{observation_id}/ai_review"
    )

    assert response.status_code == 200
    assert "Original Evidence" in response.text
    assert "AI Output" in response.text
    assert "Finalize Risk Case" in response.text
    assert "/uploads/ai-review-one.png" in response.text
    assert "/uploads/ai-review-two.png" in response.text
    assert "Contributor notes mention cracking and staining." in response.text
    assert "AI summary: crack and erosion indicators are visible." in response.text
    assert "72 / 100" in response.text
    assert "Suggested severity" in response.text
    assert "4 / 5" in response.text
    assert "The upper wall is partly obscured." in response.text
    assert "Reject AI Draft" in response.text
    assert 'name="final_ai_summary"' in response.text
    assert 'action="/observations/' in response.text
    assert "/create_risk_case" in response.text


def test_ai_review_finalize_creates_risk_case_with_overrides(ai_review_context):
    from app.models import Observation, RiskCase

    observation_id = ai_review_context["analyzed_observation_id"]
    response = ai_review_context["client"].post(
        f"/observations/{observation_id}/create_risk_case",
        data={
            "final_damage_tags": ["crack", "erosion", "corrosion"],
            "final_severity": "4",
            "final_ai_summary": "Reviewer-confirmed visible crack and erosion evidence.",
            "final_recommended_action": "Ask the local conservation officer to review.",
            "reviewer_final_notes": "Removed an unsupported certainty claim.",
            "routed_to": "Local Council",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/cases/")

    db = ai_review_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter(Observation.id == observation_id).first()
    risk_case = db.query(RiskCase).filter(RiskCase.observation_id == observation_id).first()

    assert observation.damage_tags == "crack,erosion,corrosion"
    assert observation.severity == 4
    assert observation.ai_summary == (
        "Reviewer-confirmed visible crack and erosion evidence."
    )
    assert observation.ai_recommended_action == (
        "Ask the local conservation officer to review."
    )
    raw_data = json.loads(observation.ai_raw_response)
    assert raw_data["human_ai_review"]["decision"] == "Edited and accepted"
    assert raw_data["human_ai_review"]["reviewer_notes"] == (
        "Removed an unsupported certainty claim."
    )
    assert risk_case is not None
    assert risk_case.routed_to == "Local Council"
    assert risk_case.risk_score > 0
    assert risk_case.report_path

    html_report = ai_review_context["client"].get(
        f"/cases/{risk_case.id}/report"
    )
    assert html_report.status_code == 200
    assert "Human Review Audit Trail" in html_report.text
    assert "Explainable Risk Breakdown" in html_report.text
    assert "/uploads/ai-review-one.png" in html_report.text
    assert "/uploads/ai-review-two.png" in html_report.text
    assert "not email, forward, or submit" in html_report.text


def test_reviewer_can_reject_ai_draft_and_block_case_creation(ai_review_context):
    from app.models import Observation, RiskCase

    observation_id = ai_review_context["analyzed_observation_id"]
    response = ai_review_context["client"].post(
        f"/observations/{observation_id}/reject_ai_analysis",
        data={"rejection_reason": "The second image was not addressed."},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/observations/{observation_id}"

    db = ai_review_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter(Observation.id == observation_id).one()
    assert observation.ai_analysis_status == "rejected"
    review_data = json.loads(observation.ai_raw_response)["human_ai_review"]
    assert review_data["decision"] == "Rejected"
    assert review_data["reviewer_notes"] == "The second image was not addressed."
    assert review_data["reviewed_at"]
    assert (
        db.query(RiskCase)
        .filter(RiskCase.observation_id == observation_id)
        .first()
        is None
    )

    blocked = ai_review_context["client"].post(
        f"/observations/{observation_id}/create_risk_case",
        data={"final_damage_tags": ["crack"], "final_severity": "3"},
    )
    assert blocked.status_code == 403


def test_case_status_has_manual_page_and_routed_requires_destination(ai_review_context):
    from app.models import RiskCase

    observation_id = ai_review_context["analyzed_observation_id"]
    created = ai_review_context["client"].post(
        f"/observations/{observation_id}/create_risk_case",
        data={"final_damage_tags": ["crack"], "final_severity": "3"},
        follow_redirects=False,
    )
    case_id = int(created.headers["location"].rsplit("/", 1)[-1])

    page = ai_review_context["client"].get(f"/cases/{case_id}/status")
    assert page.status_code == 200
    assert "Manual Workflow Update" in page.text
    assert "does not email, submit" in page.text

    invalid = ai_review_context["client"].post(
        f"/cases/{case_id}/status",
        data={"status": "Routed", "routed_to": ""},
    )
    assert invalid.status_code == 400

    updated = ai_review_context["client"].post(
        f"/cases/{case_id}/status",
        data={"status": "Routed", "routed_to": "Local Council"},
        follow_redirects=False,
    )
    assert updated.status_code == 303
    db = ai_review_context["db"]
    db.expire_all()
    case = db.query(RiskCase).filter(RiskCase.id == case_id).one()
    assert case.status == "Routed"
    assert case.routed_to == "Local Council"

    report = ai_review_context["client"].get(f"/cases/{case_id}/report.md")
    assert report.status_code == 200
    assert "**Status:** Routed" in report.text
    assert "Final routing destination: Local Council" in report.text


@pytest.mark.parametrize("path_suffix", ["create_risk_case", "create_case"])
def test_risk_case_creation_requires_ai_summary(ai_review_context, path_suffix):
    no_ai_id = ai_review_context["no_ai_observation_id"]

    response = ai_review_context["client"].post(
        f"/observations/{no_ai_id}/{path_suffix}",
        data={
            "final_damage_tags": ["graffiti"],
            "final_severity": "2",
            "routed_to": "",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "AI analysis summary is required before creating a Risk Case."
    )


def test_pending_observation_cannot_create_case_even_with_ai_fields(
    ai_review_context,
):
    from app.models import HumanReviewStatus, Observation

    db = ai_review_context["db"]
    approved_observation = db.query(Observation).filter(
        Observation.id == ai_review_context["analyzed_observation_id"]
    ).one()
    pending = Observation(
        site_id=approved_observation.site_id,
        notes="Pending evidence.",
        damage_tags="crack",
        severity=3,
        human_review_status=HumanReviewStatus.PENDING,
        ai_analysis_status="mock",
        ai_summary="Injected AI summary must not bypass review.",
    )
    db.add(pending)
    db.commit()

    response = ai_review_context["client"].post(
        f"/observations/{pending.id}/create_risk_case",
        data={"final_damage_tags": ["crack"], "final_severity": "3"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Observation must be approved by a human reviewer before AI analysis."
    )
