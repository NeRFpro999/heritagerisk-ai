from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def review_client():
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
        name="Review Test Site",
        location="Test Town",
        description="Site used for review queue tests.",
        created_at=now,
    )
    db.add(site)
    db.flush()

    observations = [
        Observation(
            site_id=site.id,
            notes="Pending review notes.",
            damage_tags="crack,water_staining",
            severity=4,
            human_review_status=HumanReviewStatus.PENDING,
            created_at=now - timedelta(hours=2),
        ),
        Observation(
            site_id=site.id,
            notes="Approved review notes.",
            damage_tags="erosion",
            severity=3,
            human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
            created_at=now - timedelta(days=1),
        ),
        Observation(
            site_id=site.id,
            notes="Rejected review notes.",
            damage_tags="graffiti",
            severity=2,
            human_review_status=HumanReviewStatus.REJECTED,
            created_at=now - timedelta(days=2),
        ),
        Observation(
            site_id=site.id,
            notes="Sensitive review notes.",
            damage_tags="other",
            severity=1,
            human_review_status=HumanReviewStatus.SENSITIVE,
            created_at=now - timedelta(days=3),
        ),
    ]
    db.add_all(observations)
    db.flush()

    db.add_all(
        [
            ObservationImage(
                observation_id=observations[0].id,
                image_url="/uploads/pending-one.png",
            ),
            ObservationImage(
                observation_id=observations[0].id,
                image_url="/uploads/pending-two.png",
            ),
            ObservationImage(
                observation_id=observations[1].id,
                image_url="/uploads/approved-one.png",
            ),
        ]
    )
    db.commit()
    db.close()

    client = TestClient(app, raise_server_exceptions=True)

    yield client

    app.dependency_overrides.pop(get_db, None)
    connection.close()


def test_review_queue_defaults_to_pending(review_client):
    response = review_client.get("/observations/review")

    assert response.status_code == 200
    assert "Observation Review Queue" in response.text
    assert "Pending review notes." in response.text
    assert "Approved review notes." not in response.text
    assert "2 images" in response.text
    assert "Crack" in response.text
    assert "Water Staining" in response.text
    assert "4 / 5" in response.text
    assert "Pending (1)" in response.text
    assert "ApprovedForAI (1)" in response.text
    assert "Rejected (1)" in response.text
    assert "Sensitive (1)" in response.text
    assert "Actions" in response.text


@pytest.mark.parametrize(
    ("status", "expected_notes", "unexpected_notes"),
    [
        ("ApprovedForAI", "Approved review notes.", "Pending review notes."),
        ("Rejected", "Rejected review notes.", "Pending review notes."),
        ("Sensitive", "Sensitive review notes.", "Pending review notes."),
    ],
)
def test_review_queue_filters_by_status(
    review_client,
    status,
    expected_notes,
    unexpected_notes,
):
    response = review_client.get(f"/observations/review?status={status}")

    assert response.status_code == 200
    assert expected_notes in response.text
    assert unexpected_notes not in response.text
    assert f'value="{status}"' in response.text


def test_review_queue_all_filter_shows_every_status(review_client):
    response = review_client.get("/observations/review?status=All")

    assert response.status_code == 200
    assert "Pending review notes." in response.text
    assert "Approved review notes." in response.text
    assert "Rejected review notes." in response.text
    assert "Sensitive review notes." in response.text
    assert "All statuses (4)" in response.text


def test_review_queue_rejects_invalid_status(review_client):
    response = review_client.get("/observations/review?status=Unknown")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid human review status"
