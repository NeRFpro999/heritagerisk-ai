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
def review_action_context(tmp_path):
    from app.database import Base, get_db
    import app.main as main_module
    from app.main import app
    from app.models import HumanReviewStatus, Observation, ObservationImage, Site
    from app.provenance import build_contributor_original

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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    site = Site(
        name="Gatekeeper Test Site",
        location="Test Location",
        description="Used for reviewer action tests.",
        created_at=now,
    )
    db.add(site)
    db.flush()

    observation = Observation(
        site_id=site.id,
        notes="Original public submission notes.",
        damage_tags="crack",
        severity=2,
        human_review_status=HumanReviewStatus.PENDING,
        contributor_original=build_contributor_original(
            notes="Original public submission notes.",
            tags=["crack"],
            severity=2,
            submitted_at=now,
        ),
        created_at=now,
    )
    db.add(observation)
    db.flush()
    db.add(
        ObservationImage(
            observation_id=observation.id,
            image_url="/uploads/review-action.png",
        )
    )
    db.commit()

    reviewer_settings = configure_test_reviewer()
    client = TestClient(app, raise_server_exceptions=True)
    login_reviewer(client)

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
    connection.close()


def test_review_action_form_loads(review_action_context):
    observation_id = review_action_context["observation_id"]

    response = review_action_context["client"].get(
        f"/observations/{observation_id}/review"
    )

    assert response.status_code == 200
    assert "Review Observation" in response.text
    assert "Contributor Original" in response.text
    assert "Current Reviewed Values" in response.text
    assert "Original public submission notes." in response.text
    assert 'action="/observations/' in response.text
    assert 'name="human_review_status"' in response.text
    assert 'name="reviewer_notes"' in response.text
    assert 'name="manually_selected_tags"' in response.text
    assert 'name="severity"' in response.text
    assert "ApprovedForAI" in response.text
    assert "Rejected" in response.text
    assert "Sensitive" in response.text
    assert "Save and Run AI if Approved" in response.text


def test_reviewer_can_approve_and_override_tags_and_severity(review_action_context):
    from app.models import HumanReviewStatus, Observation

    observation_id = review_action_context["observation_id"]
    db = review_action_context["db"]
    db.expire_all()
    before = db.query(Observation).filter(Observation.id == observation_id).one()
    original_submission = before.contributor_original.copy()

    response = post_form(
        review_action_context["client"],
        f"/observations/{observation_id}/review",
        data={
            "human_review_status": "ApprovedForAI",
            "reviewer_notes": "Redacted public submission notes.",
            "manually_selected_tags": "erosion, corrosion",
            "severity": "5",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/observations/{observation_id}"

    db.expire_all()
    observation = db.query(Observation).filter(Observation.id == observation_id).first()
    assert observation.human_review_status == HumanReviewStatus.APPROVED_FOR_AI
    assert observation.notes == "Redacted public submission notes."
    assert observation.damage_tags == "erosion,corrosion"
    assert observation.severity == 5
    assert observation.reviewed_by == TEST_REVIEWER_USERNAME
    assert observation.contributor_original == original_submission

    reviewer_page = review_action_context["client"].get(
        f"/observations/{observation_id}/review"
    )
    assert reviewer_page.status_code == 200
    assert "Contributor Original" in reviewer_page.text
    assert "Current Reviewed Values" in reviewer_page.text
    assert "Original public submission notes." in reviewer_page.text
    assert "Redacted public submission notes." in reviewer_page.text


def test_reviewer_can_approve_and_run_all_image_analysis(review_action_context):
    from app.models import Observation
    from app.services.ai_analysis import AIAnalysisResult

    observation_id = review_action_context["observation_id"]
    result = AIAnalysisResult(
        damage_tags=["erosion"],
        severity=4,
        confidence=76,
        summary="Visible erosion may be present.",
        recommended_action="Human review before any forwarding decision.",
        provider="azure:gpt-5-mini",
        uncertainty="Fine surface detail is unclear in the submitted image.",
    )

    with patch(
        "app.main.analyze_observation_images",
        return_value=result,
    ) as analyze_mock:
        response = post_form(
            review_action_context["client"],
            f"/observations/{observation_id}/review",
            data={
                "human_review_status": "ApprovedForAI",
                "reviewer_notes": "Privacy details removed.",
                "manually_selected_tags": "crack",
                "severity": "2",
                "analyze_after_approval": "true",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/observations/{observation_id}/ai_review"
    )
    analyze_mock.assert_called_once()
    _, kwargs = analyze_mock.call_args
    assert len(kwargs["image_paths"]) == 1
    assert kwargs["image_paths"][0].endswith("review-action.png")
    assert "Site name: Gatekeeper Test Site" in kwargs["notes"]
    assert "Privacy details removed." in kwargs["notes"]

    db = review_action_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter(Observation.id == observation_id).one()
    assert observation.damage_tags == "crack"
    assert observation.severity == 2
    assert '"damage_tags": ["erosion"]' in observation.ai_raw_response
    assert "Fine surface detail is unclear" in observation.ai_raw_response


def test_sensitive_observation_is_hidden_from_general_views(review_action_context):
    observation_id = review_action_context["observation_id"]
    site_id = review_action_context["site_id"]
    client = review_action_context["client"]

    response = post_form(
        client,
        f"/observations/{observation_id}/review",
        data={
            "human_review_status": "Sensitive",
            "reviewer_notes": "Private cultural detail for reviewer only.",
            "manually_selected_tags": "other",
            "severity": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    observation_page = client.get(f"/observations/{observation_id}")
    assert "Sensitive evidence hidden" in observation_page.text
    assert "Private cultural detail for reviewer only." not in observation_page.text
    assert "/uploads/review-action.png" not in observation_page.text

    site_page = client.get(f"/sites/{site_id}")
    assert "Sensitive evidence hidden" in site_page.text
    assert "Private cultural detail for reviewer only." not in site_page.text
    assert "/uploads/review-action.png" not in site_page.text

    reviewer_page = client.get(f"/observations/{observation_id}/review")
    assert "Private cultural detail for reviewer only." in reviewer_page.text
    assert "/uploads/review-action.png" in reviewer_page.text


@pytest.mark.parametrize("status", ["Pending", "Escalated"])
def test_review_action_rejects_invalid_status(review_action_context, status):
    from app.models import HumanReviewStatus, Observation

    observation_id = review_action_context["observation_id"]
    response = post_form(
        review_action_context["client"],
        f"/observations/{observation_id}/review",
        data={
            "human_review_status": status,
            "reviewer_notes": "Should not save.",
            "manually_selected_tags": "crack",
            "severity": "3",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid human review status"

    db = review_action_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter(Observation.id == observation_id).first()
    assert observation.human_review_status == HumanReviewStatus.PENDING
    assert observation.notes == "Original public submission notes."
    assert observation.damage_tags == "crack"
    assert observation.severity == 2


def test_public_submission_ignores_injected_review_status(review_action_context):
    from app.models import HumanReviewStatus, Observation

    site_id = review_action_context["site_id"]
    response = post_form(
        review_action_context["client"],
        "/observations/submit",
        data={
            "site_id": str(site_id),
            "contributor_notes": "Attempted status injection.",
            "manually_selected_tags": "graffiti",
            "severity": "4",
            "human_review_status": "ApprovedForAI",
        },
        files=[("images", ("test.png", io.BytesIO(TINY_PNG), "image/png"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["human_review_status"] == "Pending"

    db = review_action_context["db"]
    db.expire_all()
    observation = db.query(Observation).filter(
        Observation.id == payload["observation_id"]
    ).first()
    assert observation.human_review_status == HumanReviewStatus.PENDING
    assert observation.contributor_original["notes"] == "Attempted status injection."
    assert observation.contributor_original["tags"] == ["graffiti"]
    assert observation.contributor_original["severity"] == 4
    assert observation.contributor_original["submitted_at"]


def test_browser_submission_redirects_to_pending_confirmation(review_action_context):
    site_id = review_action_context["site_id"]
    response = post_form(
        review_action_context["client"],
        "/observations/submit",
        data={
            "site_id": str(site_id),
            "contributor_notes": "Browser submission evidence.",
            "manually_selected_tags": "erosion",
            "severity": "2",
            "response_mode": "html",
        },
        files=[("images", ("test.png", io.BytesIO(TINY_PNG), "image/png"))],
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/submitted")

    confirmation = review_action_context["client"].get(
        response.headers["location"]
    )
    assert confirmation.status_code == 200
    assert "Submission received" in confirmation.text
    assert "Pending" in confirmation.text
    assert "AI analysis cannot run unless" in confirmation.text


def test_public_submission_limits_image_count(review_action_context):
    site_id = review_action_context["site_id"]
    files = [
        ("images", (f"image-{index}.png", io.BytesIO(TINY_PNG), "image/png"))
        for index in range(7)
    ]
    response = post_form(
        review_action_context["client"],
        "/observations/submit",
        data={"site_id": str(site_id), "severity": "1"},
        files=files,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Upload no more than 6 images."


def test_public_submission_can_describe_new_site(review_action_context):
    from app.models import HumanReviewStatus, Observation, Site

    response = post_form(
        review_action_context["client"],
        "/observations/submit",
        data={
            "site_name": "New Public Monument",
            "site_location": "High Street",
            "site_description": "Small memorial beside the library.",
            "contributor_notes": "Visible water staining on the base.",
            "manually_selected_tags": "water_staining",
            "severity": "3",
        },
        files=[("images", ("new-site.png", io.BytesIO(TINY_PNG), "image/png"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["human_review_status"] == "Pending"

    db = review_action_context["db"]
    db.expire_all()
    site = db.query(Site).filter(Site.name == "New Public Monument").one()
    observation = db.query(Observation).filter(
        Observation.id == payload["observation_id"]
    ).one()

    assert observation.site_id == site.id
    assert site.location == "High Street"
    assert site.description == "Small memorial beside the library."
    assert observation.human_review_status == HumanReviewStatus.PENDING
    assert observation.notes == "Visible water staining on the base."
    assert observation.damage_tags == "water_staining"
    assert observation.contributor_original["notes"] == (
        "Visible water staining on the base."
    )
    assert observation.contributor_original["tags"] == ["water_staining"]
    assert observation.contributor_original["severity"] == 3
    assert observation.contributor_original["submitted_at"]
