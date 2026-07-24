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


@pytest.fixture()
def ai_gate_context():
    from app.database import Base, get_db
    from app.main import app
    from app.models import (
        HumanReviewStatus,
        Observation,
        ObservationImage,
        Site,
    )

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

    db = TestSessionLocal()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    site = Site(
        name="AI Gate Test Site",
        location="Test Location",
        description="Used for AI gate tests.",
        created_at=now,
    )
    db.add(site)
    db.flush()

    pending_observation = Observation(
        site_id=site.id,
        notes="Pending notes with crack.",
        damage_tags="crack",
        severity=2,
        human_review_status=HumanReviewStatus.PENDING,
        created_at=now,
    )
    approved_observation = Observation(
        site_id=site.id,
        notes="Approved notes with water staining.",
        damage_tags="water_staining",
        severity=3,
        human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
        reviewed_by=TEST_REVIEWER_USERNAME,
        created_at=now,
    )
    db.add_all([pending_observation, approved_observation])
    db.flush()
    db.add_all(
        [
            ObservationImage(
                observation_id=approved_observation.id,
                image_url="/uploads/approved-one.png",
            ),
            ObservationImage(
                observation_id=approved_observation.id,
                image_url="/uploads/approved-two.png",
            ),
        ]
    )
    db.commit()

    reviewer_settings = configure_test_reviewer()
    client = TestClient(app, raise_server_exceptions=True)
    login_reviewer(client)

    yield {
        "client": client,
        "db": db,
        "pending_observation_id": pending_observation.id,
        "approved_observation_id": approved_observation.id,
    }

    db.close()
    restore_test_reviewer(reviewer_settings)
    app.dependency_overrides.pop(get_db, None)
    connection.close()


def test_pending_observation_ai_analysis_returns_403(ai_gate_context):
    pending_id = ai_gate_context["pending_observation_id"]

    with patch("app.main.analyze_observation_images") as analyze_mock:
        response = post_form(
            ai_gate_context["client"],
            f"/observations/{pending_id}/analyze",
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Observation must be approved by a human reviewer before AI analysis."
    )
    analyze_mock.assert_not_called()


def test_approved_observation_ai_analysis_proceeds(ai_gate_context):
    from app.models import Observation
    from app.services.ai_analysis import AIAnalysisResult

    approved_id = ai_gate_context["approved_observation_id"]
    analysis_result = AIAnalysisResult(
        damage_tags=["crack"],
        severity=2,
        confidence=35,
        summary="Mock analysis used for approved observation.",
        recommended_action="Human review required before action.",
        provider="mock",
        raw_response=None,
    )

    with patch(
        "app.main.analyze_observation_images",
        return_value=analysis_result,
    ) as analyze_mock:
        response = post_form(
            ai_gate_context["client"],
            f"/observations/{approved_id}/analyze",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/observations/{approved_id}/ai_review"
    analyze_mock.assert_called_once()
    _, kwargs = analyze_mock.call_args
    assert len(kwargs["image_paths"]) == 2
    assert kwargs["image_paths"][0].endswith("approved-one.png")
    assert kwargs["image_paths"][1].endswith("approved-two.png")
    assert "Site name: AI Gate Test Site" in kwargs["notes"]
    assert "Location: Test Location" in kwargs["notes"]
    assert "Approved notes with water staining." in kwargs["notes"]

    db = ai_gate_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter(Observation.id == approved_id).first()
    assert observation.ai_analysis_status == "mock"
    assert observation.ai_provider == "mock"
    assert observation.ai_summary == "Mock analysis used for approved observation."
    assert observation.damage_tags == "water_staining"
    assert '"damage_tags": ["crack"]' in observation.ai_raw_response
