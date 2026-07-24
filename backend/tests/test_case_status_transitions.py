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
def status_context(tmp_path):
    from app.database import Base, get_db
    from app.main import app
    import app.reports as reports_module
    from app.models import HumanReviewStatus, Observation, RiskCase, Site

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
    site = Site(name="Status Test Site", location="Test", description="Test")
    db.add(site)
    db.flush()

    cases = {}
    for status in RiskCase.STATUSES:
        observation = Observation(
            site_id=site.id,
            notes=f"{status} observation",
            damage_tags="crack",
            severity=2,
            human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
            reviewed_by=TEST_REVIEWER_USERNAME,
            ai_analysis_status="mock",
            ai_summary="Mock summary.",
            ai_confidence=50,
            ai_provider="mock",
            ai_recommended_action="Human review required.",
            ai_raw_response=(
                '{"damage_tags":["crack"],"severity":2,"confidence":50,'
                '"summary":"Mock summary.","recommended_action":"Human review required."}'
            ),
            created_at=datetime.utcnow(),
        )
        db.add(observation)
        db.flush()
        case = RiskCase(
            observation_id=observation.id,
            risk_score=16,
            risk_band="Low",
            status=status,
            routed_to=(
                "Existing destination"
                if status in {"Routed", "Closed"}
                else None
            ),
            finalized_by=TEST_REVIEWER_USERNAME,
            created_at=datetime.utcnow(),
        )
        db.add(case)
        db.flush()
        cases[status] = case.id
    db.commit()

    reviewer_settings = configure_test_reviewer()
    client = TestClient(app, raise_server_exceptions=True)
    login_reviewer(client)

    yield {"client": client, "db": db, "case_ids": cases}

    db.close()
    restore_test_reviewer(reviewer_settings)
    app.dependency_overrides.pop(get_db, None)
    reports_module.REPORTS_DIR = original_reports_dir
    connection.close()


@pytest.mark.parametrize(
    ("from_status", "to_status", "destination"),
    [
        ("Draft", "Needs Review", ""),
        ("Needs Review", "Verified", ""),
        ("Needs Review", "Draft", ""),
        ("Verified", "Routed", "Local Council"),
        ("Verified", "Needs Review", ""),
        ("Routed", "Closed", "Existing destination"),
    ],
)
def test_allowed_case_status_transitions_succeed_and_are_logged(
    status_context,
    from_status,
    to_status,
    destination,
):
    from app.models import CaseEvent, RiskCase

    case_id = status_context["case_ids"][from_status]
    response = post_form(
        status_context["client"],
        f"/cases/{case_id}/status",
        data={
            "status": to_status,
            "routed_to": destination,
            "status_note": f"{from_status} to {to_status} test",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/cases/{case_id}"

    db = status_context["db"]
    db.expire_all()
    case = db.query(RiskCase).filter_by(id=case_id).one()
    event = db.query(CaseEvent).filter_by(case_id=case_id).one()
    assert case.status == to_status
    assert event.from_status == from_status
    assert event.to_status == to_status
    assert event.reviewer == TEST_REVIEWER_USERNAME
    assert event.note == f"{from_status} to {to_status} test"
    if to_status == "Routed":
        assert case.routed_to == "Local Council"


def test_draft_to_routed_is_rejected_with_allowed_states(status_context):
    case_id = status_context["case_ids"]["Draft"]

    response = post_form(
        status_context["client"],
        f"/cases/{case_id}/status",
        data={"status": "Routed", "routed_to": "Local Council"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Invalid transition from Draft to Routed. "
        "Allowed next states: Needs Review."
    )


def test_routed_transition_requires_destination(status_context):
    case_id = status_context["case_ids"]["Verified"]

    response = post_form(
        status_context["client"],
        f"/cases/{case_id}/status",
        data={"status": "Routed", "routed_to": ""},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "A routing destination is required for Routed cases."
    )


def test_closed_is_terminal(status_context):
    case_id = status_context["case_ids"]["Closed"]

    response = post_form(
        status_context["client"],
        f"/cases/{case_id}/status",
        data={"status": "Verified"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Invalid transition from Closed to Verified. Allowed next states: none."
    )

    page = status_context["client"].get(f"/cases/{case_id}/status")
    assert page.status_code == 200
    assert "No valid next status" in page.text
    assert 'value="Verified"' not in page.text


def test_event_history_renders_on_case_page_and_markdown_report(status_context):
    case_id = status_context["case_ids"]["Draft"]
    post_form(
        status_context["client"],
        f"/cases/{case_id}/status",
        data={
            "status": "Needs Review",
            "status_note": "Ready for conservation lead review.",
        },
        follow_redirects=False,
    )

    case_page = status_context["client"].get(f"/cases/{case_id}")
    markdown = status_context["client"].get(f"/cases/{case_id}/report.md")

    assert case_page.status_code == 200
    assert "Status Event History" in case_page.text
    assert "Draft -> Needs Review" in markdown.text
    assert TEST_REVIEWER_USERNAME in markdown.text
    assert "Ready for conservation lead review." in markdown.text
