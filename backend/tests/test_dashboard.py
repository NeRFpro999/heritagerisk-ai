import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def dashboard_context():
    from app.database import Base, get_db
    from app.main import app

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
    client = TestClient(app, raise_server_exceptions=True)

    yield {"client": client, "db": db}

    db.close()
    app.dependency_overrides.pop(get_db, None)
    connection.close()


def assert_metric(html: str, label: str, value: int) -> None:
    pattern = (
        rf'<span class="stat-number">\s*{value}\s*</span>\s*'
        rf'<span class="stat-label">{re.escape(label)}</span>'
    )
    assert re.search(pattern, html)


def test_dashboard_loads_with_empty_database(dashboard_context):
    response = dashboard_context["client"].get("/")

    assert response.status_code == 200
    assert "Total Observations Submitted" in response.text
    assert "Observations Awaiting Review" in response.text
    assert "Approved Observations" in response.text
    assert "Total Risk Cases Generated" in response.text
    assert "High Priority Cases" in response.text
    assert "Case Statuses" in response.text
    assert "Recent Activity" in response.text
    assert "No recent activity yet." in response.text

    assert_metric(response.text, "Total Observations Submitted", 0)
    assert_metric(response.text, "Observations Awaiting Review", 0)
    assert_metric(response.text, "Approved Observations", 0)
    assert_metric(response.text, "Total Risk Cases Generated", 0)
    assert_metric(response.text, "High Priority Cases", 0)


def test_dashboard_calculates_metrics_and_recent_activity(dashboard_context):
    from app.models import HumanReviewStatus, Observation, RiskCase, Site

    db = dashboard_context["db"]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    site = Site(
        name="Dashboard Test Site",
        location="Test Town",
        description="Dashboard metrics fixture.",
        created_at=now - timedelta(hours=1),
    )
    db.add(site)
    db.flush()

    pending_observation = Observation(
        site_id=site.id,
        notes="Pending dashboard observation.",
        damage_tags="crack",
        severity=3,
        human_review_status=HumanReviewStatus.PENDING,
        created_at=now - timedelta(minutes=4),
    )
    approved_observation = Observation(
        site_id=site.id,
        notes="Approved dashboard observation.",
        damage_tags="erosion",
        severity=4,
        human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
        created_at=now - timedelta(minutes=3),
    )
    db.add_all([pending_observation, approved_observation])
    db.flush()

    risk_case = RiskCase(
        observation_id=approved_observation.id,
        risk_score=80,
        risk_band="High",
        status="Needs Review",
        created_at=now - timedelta(minutes=1),
    )
    db.add(risk_case)
    db.commit()

    response = dashboard_context["client"].get("/")

    assert response.status_code == 200
    assert_metric(response.text, "Total Observations Submitted", 2)
    assert_metric(response.text, "Observations Awaiting Review", 1)
    assert_metric(response.text, "Approved Observations", 1)
    assert_metric(response.text, "Total Risk Cases Generated", 1)
    assert_metric(response.text, "High Priority Cases", 1)
    assert "Open Review Queue" in response.text
    assert "Case Statuses" in response.text
    assert "Needs Review" in response.text
    assert "Risk Case #" in response.text
    assert "Observation #" in response.text
    assert "Dashboard Test Site" in response.text
    assert "High" in response.text
