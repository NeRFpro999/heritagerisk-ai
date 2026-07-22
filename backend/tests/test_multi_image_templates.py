from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def multi_image_context():
    from app.database import Base, get_db
    from app.main import app
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

    db = TestSessionLocal()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    site = Site(
        name="Multi Image Site",
        location="Test Location",
        description="Used for multi-image template tests.",
        created_at=now,
    )
    db.add(site)
    db.flush()

    observation = Observation(
        site_id=site.id,
        notes="Multi-image observation notes.",
        damage_tags="crack,water_staining",
        severity=4,
        human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
        created_at=now,
    )
    db.add(observation)
    db.flush()
    site_id = site.id
    observation_id = observation.id
    db.add_all(
        [
            ObservationImage(
                observation_id=observation.id,
                image_url="/uploads/multi-one.png",
            ),
            ObservationImage(
                observation_id=observation.id,
                image_url="/uploads/multi-two.png",
            ),
            ObservationImage(
                observation_id=observation.id,
                image_url="/uploads/multi-three.png",
            ),
        ]
    )
    db.commit()
    db.close()

    client = TestClient(app, raise_server_exceptions=True)

    yield {
        "client": client,
        "site_id": site_id,
        "observation_id": observation_id,
    }

    app.dependency_overrides.pop(get_db, None)
    connection.close()


def test_observation_detail_renders_all_images_in_grid(multi_image_context):
    observation_id = multi_image_context["observation_id"]

    response = multi_image_context["client"].get(f"/observations/{observation_id}")

    assert response.status_code == 200
    assert 'class="obs-image-grid"' in response.text
    assert "/uploads/multi-one.png" in response.text
    assert "/uploads/multi-two.png" in response.text
    assert "/uploads/multi-three.png" in response.text
    assert "Image 1 of 3" in response.text
    assert "Image 2 of 3" in response.text
    assert "Image 3 of 3" in response.text


def test_site_detail_shows_first_thumbnail_with_more_badge(multi_image_context):
    site_id = multi_image_context["site_id"]
    observation_id = multi_image_context["observation_id"]

    response = multi_image_context["client"].get(f"/sites/{site_id}")

    assert response.status_code == 200
    assert f'href="/observations/{observation_id}"' in response.text
    assert 'class="obs-thumb-link"' in response.text
    assert 'src="/uploads/multi-one.png"' in response.text
    assert '+2 more' in response.text
