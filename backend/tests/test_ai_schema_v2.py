import json
from datetime import datetime

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


@pytest.fixture()
def v2_context(tmp_path):
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
    site = Site(name="V2 Test Site", location="Test", description="Test")
    db.add(site)
    db.flush()
    observation = Observation(
        site_id=site.id,
        notes="Reviewed notes mention crack and water staining.",
        damage_tags="crack",
        severity=2,
        human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
        reviewed_by=TEST_REVIEWER_USERNAME,
        created_at=datetime.utcnow(),
    )
    db.add(observation)
    db.flush()
    db.add_all(
        [
            ObservationImage(observation_id=observation.id, image_url="/uploads/one.png"),
            ObservationImage(observation_id=observation.id, image_url="/uploads/two.png"),
        ]
    )
    db.commit()
    observation_id = observation.id

    reviewer_settings = configure_test_reviewer()
    client = TestClient(app, raise_server_exceptions=True)
    login_reviewer(client)

    yield {"client": client, "db": db, "observation_id": observation_id}

    db.close()
    restore_test_reviewer(reviewer_settings)
    app.dependency_overrides.pop(get_db, None)
    reports_module.REPORTS_DIR = original_reports_dir
    connection.close()


def _valid_v2_payload(image_ids: list[int]) -> dict:
    return {
        "schema_version": "2",
        "provider": "azure:fake-deployment",
        "overall_summary": "Visible cracking is present in the upper wall.",
        "evidence_sufficiency": "partial",
        "indicators": [
            {
                "indicator_type": "crack",
                "evidence_location": "upper left of image 2",
                "image_refs": [image_ids[-1]],
                "confidence": 0.72,
                "supporting_evidence": "A narrow linear opening is visible.",
                "severity_contribution": 3,
            }
        ],
        "insufficient_reason": None,
    }


def _apply_result(v2_context, payload: dict, provider="azure:fake-deployment"):
    from app.main import apply_ai_analysis_result
    from app.models import Observation
    from app.services.ai_analysis import AIAnalysisResult

    db = v2_context["db"]
    observation = db.query(Observation).filter_by(id=v2_context["observation_id"]).one()
    result = AIAnalysisResult(
        damage_tags=["crack"],
        severity=3,
        confidence=72,
        summary=payload.get("overall_summary", "Summary"),
        recommended_action="Human review required before action.",
        provider=provider,
        raw_response=json.dumps(payload),
        structured_response=payload,
    )
    apply_ai_analysis_result(observation, result)
    db.commit()
    db.refresh(observation)
    return observation


def test_valid_v2_parses_and_renders(v2_context):
    db = v2_context["db"]
    observation = db.get(
        __import__("app.models", fromlist=["Observation"]).Observation,
        v2_context["observation_id"],
    )
    payload = _valid_v2_payload([image.id for image in observation.images])
    _apply_result(v2_context, payload)

    response = v2_context["client"].get(
        f"/observations/{v2_context['observation_id']}/ai_review"
    )

    assert response.status_code == 200
    assert "Evidence sufficiency" in response.text
    assert "partial" in response.text
    assert "upper left of image 2" in response.text
    assert "72%" in response.text


def test_invalid_indicator_type_becomes_failed_state_with_raw_payload(v2_context):
    db = v2_context["db"]
    observation = db.get(
        __import__("app.models", fromlist=["Observation"]).Observation,
        v2_context["observation_id"],
    )
    payload = _valid_v2_payload([image.id for image in observation.images])
    payload["indicators"][0]["indicator_type"] = "alien_growth"

    observation = _apply_result(v2_context, payload)
    stored = json.loads(observation.ai_raw_response)

    assert observation.ai_analysis_status == "failed"
    assert stored["schema_version"] == "2"
    assert stored["validation_status"] == "failed"
    assert "Unknown indicator_type" in stored["validation_error"]
    assert stored["raw_payload"]["indicators"][0]["indicator_type"] == "alien_growth"


def test_insufficient_evidence_result_finalizes_with_no_visible_indicators(v2_context):
    from app.models import RiskCase

    payload = {
        "schema_version": "2",
        "provider": "mock",
        "overall_summary": "No visible indicators could be confirmed.",
        "evidence_sufficiency": "insufficient",
        "indicators": [],
        "insufficient_reason": "Images are too distant to support a visible indicator.",
    }
    _apply_result(v2_context, payload, provider="mock")

    response = post_form(
        v2_context["client"],
        f"/observations/{v2_context['observation_id']}/create_risk_case",
        data={
            "final_severity": "1",
            "final_ai_summary": "No visible indicators confirmed.",
            "final_recommended_action": "No visible indicators confirmed; keep record for audit.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    db = v2_context["db"]
    db.expire_all()
    case = db.query(RiskCase).one()
    assert case.final_snapshot["final_tags"] == []
    assert case.risk_score == 0
    report = v2_context["client"].get(f"/cases/{case.id}/report.md")
    assert "No visible indicators confirmed" in report.text
    assert "**Evidence sufficiency:** insufficient" in report.text


def test_v1_rows_still_render(v2_context):
    from app.models import Observation

    db = v2_context["db"]
    observation = db.query(Observation).filter_by(id=v2_context["observation_id"]).one()
    observation.ai_analysis_status = "mock"
    observation.ai_summary = "Legacy v1 summary."
    observation.ai_confidence = 35
    observation.ai_provider = "mock"
    observation.ai_recommended_action = "Human review required."
    observation.ai_raw_response = json.dumps(
        {
            "damage_tags": ["crack"],
            "severity": 2,
            "confidence": 35,
            "summary": "Legacy v1 summary.",
        }
    )
    db.commit()

    response = v2_context["client"].get(
        f"/observations/{v2_context['observation_id']}/ai_review"
    )

    assert response.status_code == 200
    assert "Legacy v1 summary." in response.text
    assert "Crack" in response.text
