import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def site_intake_context(tmp_path):
    from app.database import Base, get_db
    from app.main import app
    import app.main as main_module

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

    original_uploads_dir = main_module.UPLOADS_DIR
    main_module.UPLOADS_DIR = tmp_path

    db = TestSessionLocal()
    client = TestClient(app, raise_server_exceptions=True)

    yield {"client": client, "db": db, "uploads_dir": tmp_path}

    db.close()
    app.dependency_overrides.pop(get_db, None)
    main_module.UPLOADS_DIR = original_uploads_dir
    connection.close()


def test_add_site_without_images_keeps_site_only_flow(site_intake_context):
    from app.models import Observation, Site

    with patch("app.main.analyze_observation_images") as analyze_mock:
        response = site_intake_context["client"].post(
            "/sites",
            data={
                "name": "No Image Monument",
                "location": "Test Location",
                "description": "Created without intake photos.",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/sites/")
    analyze_mock.assert_not_called()

    db = site_intake_context["db"]
    assert db.query(Site).count() == 1
    assert db.query(Observation).count() == 0


def test_add_site_with_images_runs_ai_intake(site_intake_context):
    from app.models import HumanReviewStatus, Observation, Site
    from app.services.ai_analysis import AIAnalysisResult

    analysis_result = AIAnalysisResult(
        damage_tags=["crack", "water_staining"],
        severity=4,
        confidence=82,
        summary="Visible cracking and water staining are present.",
        recommended_action="Human review required before routing.",
        provider="azure:gpt-5-mini",
        raw_response='{"damage_tags": ["crack", "water_staining"]}',
    )

    files = [
        ("images", ("front.png", io.BytesIO(TINY_PNG), "image/png")),
        ("images", ("side.png", io.BytesIO(TINY_PNG), "image/png")),
    ]
    with patch(
        "app.main.analyze_observation_images",
        return_value=analysis_result,
    ) as analyze_mock:
        response = site_intake_context["client"].post(
            "/sites",
            data={
                "name": "AI Intake Monument",
                "location": "Council Square",
                "description": "Sandstone memorial with visible staining.",
                "intake_notes": "Photos show the front and side faces.",
            },
            files=files,
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/observations/")
    assert response.headers["location"].endswith("/ai_review")

    db = site_intake_context["db"]
    db.expire_all()
    site = db.query(Site).filter(Site.name == "AI Intake Monument").one()
    observation = db.query(Observation).filter(Observation.site_id == site.id).one()

    assert observation.human_review_status == HumanReviewStatus.APPROVED_FOR_AI
    assert len(observation.images) == 2
    assert observation.ai_analysis_status == "complete"
    assert observation.ai_provider == "azure:gpt-5-mini"
    assert observation.ai_summary == "Visible cracking and water staining are present."
    assert observation.tags_list == []
    assert observation.severity == 1
    assert '"damage_tags": ["crack", "water_staining"]' in observation.ai_raw_response
    assert '"severity": 4' in observation.ai_raw_response

    analyze_mock.assert_called_once()
    _, kwargs = analyze_mock.call_args
    assert len(kwargs["image_paths"]) == 2
    assert "Site name: AI Intake Monument" in kwargs["notes"]
    assert "Location: Council Square" in kwargs["notes"]
    assert "Sandstone memorial with visible staining." in kwargs["notes"]
    assert "Photos show the front and side faces." in kwargs["notes"]
