import io
import json
from copy import deepcopy
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
def provenance_context(tmp_path):
    from app.database import Base, get_db
    import app.main as main_module
    import app.reports as reports_module
    from app.main import app
    from app.models import Site

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
    site = Site(
        name="Provenance Test Place",
        location="Test Square",
        description="A site used to verify immutable evidence layers.",
    )
    db.add(site)
    db.commit()

    reviewer_settings = configure_test_reviewer()
    client = TestClient(app, raise_server_exceptions=True)
    login_reviewer(client)
    yield {"client": client, "db": db, "site_id": site.id}

    db.close()
    restore_test_reviewer(reviewer_settings)
    app.dependency_overrides.pop(get_db, None)
    main_module.UPLOADS_DIR = original_uploads_dir
    reports_module.REPORTS_DIR = original_reports_dir
    connection.close()


def _complete_review_cycle(context):
    from app.models import Observation, RiskCase
    from app.services.ai_analysis import AIAnalysisResult

    client = context["client"]
    db = context["db"]
    submitted = post_form(
        client,
        "/observations/submit",
        data={
            "site_id": str(context["site_id"]),
            "contributor_notes": "ORIGINAL contributor note about one crack.",
            "manually_selected_tags": "crack",
            "severity": "2",
        },
        files=[("images", ("evidence.png", io.BytesIO(TINY_PNG), "image/png"))],
    )
    assert submitted.status_code == 200
    observation_id = submitted.json()["observation_id"]

    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation_id).one()
    original = deepcopy(observation.contributor_original)

    result = AIAnalysisResult(
        damage_tags=["crack", "water_staining"],
        severity=4,
        confidence=78,
        summary="AI PROPOSAL: visible crack and staining indicators.",
        recommended_action="AI PROPOSAL: request human triage review.",
        provider="azure:fake-test-deployment",
        raw_response='{"provider_payload":"immutable-ai-bytes"}',
        uncertainty="AI PROPOSAL: the upper edge is partly obscured.",
    )
    with patch("app.main.analyze_observation_images", return_value=result):
        reviewed = post_form(
            client,
            f"/observations/{observation_id}/review",
            data={
                "human_review_status": "ApprovedForAI",
                "reviewer_notes": "CURRENT reviewed note after privacy edit.",
                "manually_selected_tags": "crack,erosion",
                "severity": "3",
                "analyze_after_approval": "true",
            },
            follow_redirects=False,
        )
    assert reviewed.status_code == 303

    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation_id).one()
    ai_proposal = {
        "status": observation.ai_analysis_status,
        "summary": observation.ai_summary,
        "confidence": observation.ai_confidence,
        "provider": observation.ai_provider,
        "action": observation.ai_recommended_action,
        "raw": observation.ai_raw_response,
    }

    second_edit = post_form(
        client,
        f"/observations/{observation_id}/review",
        data={
            "human_review_status": "ApprovedForAI",
            "reviewer_notes": "CURRENT second reviewed note.",
            "manually_selected_tags": "erosion,corrosion",
            "severity": "4",
        },
        follow_redirects=False,
    )
    assert second_edit.status_code == 303

    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation_id).one()
    assert {
        "status": observation.ai_analysis_status,
        "summary": observation.ai_summary,
        "confidence": observation.ai_confidence,
        "provider": observation.ai_provider,
        "action": observation.ai_recommended_action,
        "raw": observation.ai_raw_response,
    } == ai_proposal

    finalized = post_form(
        client,
        f"/observations/{observation_id}/create_risk_case",
        data={
            "final_damage_tags": ["crack", "erosion", "corrosion"],
            "final_severity": "5",
            "final_ai_summary": "FINAL reviewer-accepted visible evidence summary.",
            "final_recommended_action": "FINAL human-entered next step.",
            "reviewer_final_notes": "FINAL tags and wording checked against images.",
        },
        follow_redirects=False,
    )
    assert finalized.status_code == 303
    case_id = int(finalized.headers["location"].rsplit("/", 1)[-1])

    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation_id).one()
    case = db.query(RiskCase).filter_by(id=case_id).one()
    return observation, case, original, ai_proposal


def test_original_and_ai_proposal_survive_review_edit_finalize_cycle(
    provenance_context,
):
    from app.provenance import utc_iso

    observation, case, original, ai_proposal = _complete_review_cycle(
        provenance_context
    )

    assert set(original) == {"notes", "tags", "severity", "submitted_at"}
    assert original["notes"] == "ORIGINAL contributor note about one crack."
    assert original["tags"] == ["crack"]
    assert original["severity"] == 2
    assert original["submitted_at"] == utc_iso(observation.created_at)
    assert observation.contributor_original == original

    assert observation.ai_analysis_status == ai_proposal["status"]
    assert observation.ai_summary == ai_proposal["summary"]
    assert observation.ai_confidence == ai_proposal["confidence"]
    assert observation.ai_provider == ai_proposal["provider"]
    assert observation.ai_recommended_action == ai_proposal["action"]
    assert observation.ai_raw_response == ai_proposal["raw"]
    assert observation.ai_review_decision["decision"] == "Edited and accepted"
    assert observation.reviewed_by == TEST_REVIEWER_USERNAME
    assert case.finalized_by == TEST_REVIEWER_USERNAME

    snapshot = case.final_snapshot
    assert snapshot["reviewed_by"] == TEST_REVIEWER_USERNAME
    assert snapshot["finalized_by"] == TEST_REVIEWER_USERNAME
    assert snapshot["contributor_original"] == original
    assert snapshot["ai_proposal"]["raw_response"] == ai_proposal["raw"]
    assert snapshot["final_tags"] == ["crack", "erosion", "corrosion"]
    assert snapshot["final_severity"] == 5
    assert snapshot["final_summary"] == (
        "FINAL reviewer-accepted visible evidence summary."
    )
    assert snapshot["final_recommended_action"] == (
        "FINAL human-entered next step."
    )


def test_post_case_observation_edit_cannot_change_case_or_reports(
    provenance_context,
):
    from app.models import Observation, RiskCase, Site

    observation, case, _, _ = _complete_review_cycle(provenance_context)
    client = provenance_context["client"]
    db = provenance_context["db"]
    snapshot_before = json.dumps(case.final_snapshot, sort_keys=True)
    score_before = case.risk_score
    band_before = case.risk_band

    case_page_before = client.get(f"/cases/{case.id}").text
    case_list_before = client.get("/cases").text
    html_report_before = client.get(f"/cases/{case.id}/report").text
    markdown_before = client.get(f"/cases/{case.id}/report.md").text

    changed = post_form(
        client,
        f"/observations/{observation.id}/review",
        data={
            "human_review_status": "ApprovedForAI",
            "reviewer_notes": "MUTATED live observation note after case creation.",
            "manually_selected_tags": "graffiti",
            "severity": "1",
        },
        follow_redirects=False,
    )
    assert changed.status_code == 303

    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation.id).one()
    replacement_site = Site(
        name="MUTATED live site",
        location="Different location",
        description="This must not enter the finalized case.",
    )
    db.add(replacement_site)
    db.flush()
    observation.site_id = replacement_site.id
    observation.contributor_original = {
        "notes": "MUTATED live contributor original.",
        "tags": ["fire_damage"],
        "severity": 1,
        "submitted_at": "2099-01-01T00:00:00+00:00",
    }
    observation.ai_analysis_status = "complete"
    observation.ai_summary = "MUTATED live AI summary."
    observation.ai_confidence = 1
    observation.ai_provider = "MUTATED live AI provider"
    observation.ai_recommended_action = "MUTATED live AI action."
    observation.ai_raw_response = '{"marker":"MUTATED live AI raw"}'
    db.commit()
    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation.id).one()
    case = db.query(RiskCase).filter_by(id=case.id).one()
    assert observation.notes == "MUTATED live observation note after case creation."
    assert observation.tags_list == ["graffiti"]
    assert observation.severity == 1
    assert json.dumps(case.final_snapshot, sort_keys=True) == snapshot_before
    assert case.risk_score == score_before == 100
    assert case.risk_band == band_before == "High"

    case_page_after = client.get(f"/cases/{case.id}").text
    case_list_after = client.get("/cases").text
    html_report_after = client.get(f"/cases/{case.id}/report").text
    markdown_after = client.get(f"/cases/{case.id}/report.md").text
    assert case_page_after == case_page_before
    assert case_list_after == case_list_before
    assert html_report_after == html_report_before
    assert markdown_after == markdown_before
    for rendered in (
        case_page_after,
        case_list_after,
        html_report_after,
        markdown_after,
    ):
        assert "MUTATED live observation note" not in rendered
        assert "MUTATED live site" not in rendered
        assert "MUTATED live contributor original" not in rendered
        assert "MUTATED live AI" not in rendered
        assert "ORIGINAL contributor note" not in rendered

    assert "Crack" in case_list_after
    assert "Erosion" in case_list_after
    assert "Corrosion / Rust" in case_list_after
    assert "100" in case_list_after
    for rendered in (case_page_after, html_report_after, markdown_after):
        assert "FINAL reviewer-accepted visible evidence summary." in rendered
        assert "(8 + 7 + 7) × Severity 5 = 110" in rendered


def test_markdown_contains_every_stored_scoring_snapshot_field(
    provenance_context,
):
    _, case, _, _ = _complete_review_cycle(provenance_context)
    markdown = provenance_context["client"].get(
        f"/cases/{case.id}/report.md"
    ).text

    assert "**Final tags:** crack, erosion, corrosion" in markdown
    assert "**Final severity:** 5 / 5" in markdown
    assert "**crack** (Crack): 8" in markdown
    assert "**erosion** (Erosion): 7" in markdown
    assert "**corrosion** (Corrosion / Rust): 7" in markdown
    assert "**Severity multiplier:** 5" in markdown
    assert "**Raw equation:** (8 + 7 + 7) × Severity 5 = 110" in markdown
    assert "**Capped score:** 100 / 100 (capped)" in markdown
    assert "**Risk band:** High" in markdown


def test_review_route_cannot_replace_ai_proposal_after_case_creation(
    provenance_context,
):
    from app.models import Observation

    observation, _, original, ai_proposal = _complete_review_cycle(
        provenance_context
    )
    client = provenance_context["client"]
    db = provenance_context["db"]

    with patch("app.main.analyze_observation_images") as analyze_mock:
        response = post_form(
            client,
            f"/observations/{observation.id}/review",
            data={
                "human_review_status": "ApprovedForAI",
                "reviewer_notes": "Attempted post-case AI replacement.",
                "manually_selected_tags": "fire_damage",
                "severity": "5",
                "analyze_after_approval": "true",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "AI analysis cannot be changed after a Risk Case is created."
    )
    analyze_mock.assert_not_called()

    db.expire_all()
    observation = db.query(Observation).filter_by(id=observation.id).one()
    assert observation.contributor_original == original
    assert observation.ai_analysis_status == ai_proposal["status"]
    assert observation.ai_summary == ai_proposal["summary"]
    assert observation.ai_confidence == ai_proposal["confidence"]
    assert observation.ai_provider == ai_proposal["provider"]
    assert observation.ai_recommended_action == ai_proposal["action"]
    assert observation.ai_raw_response == ai_proposal["raw"]
    assert observation.notes == "CURRENT second reviewed note."
    assert observation.tags_list == ["crack", "erosion", "corrosion"]
    assert observation.severity == 5
