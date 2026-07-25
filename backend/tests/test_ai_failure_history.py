import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError
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
def failure_history_context(tmp_path):
    from app.database import Base, get_db
    from app.main import app
    import app.main as main_module
    import app.reports as reports_module
    from app.models import HumanReviewStatus, Observation, ObservationImage, Site
    from app.provenance import build_contributor_original

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
        route_db = TestSessionLocal()
        try:
            yield route_db
        finally:
            route_db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_uploads_dir = main_module.UPLOADS_DIR
    original_reports_dir = reports_module.REPORTS_DIR
    main_module.UPLOADS_DIR = tmp_path
    reports_module.REPORTS_DIR = tmp_path
    image_path = tmp_path / "evidence.png"
    image_path.write_bytes(b"image-bytes-for-mocked-provider")

    db = TestSessionLocal()
    created_at = datetime(2026, 7, 24, 9, 0, 0)
    site = Site(
        name="Azure Failure Test Site",
        location="Test",
        description="Test",
    )
    db.add(site)
    db.flush()
    observation = Observation(
        site_id=site.id,
        notes="A crack is visible in the reviewed notes.",
        damage_tags="crack",
        severity=2,
        human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
        reviewed_by=TEST_REVIEWER_USERNAME,
        contributor_original=build_contributor_original(
            notes="A crack is visible in the contributor notes.",
            tags=["crack"],
            severity=2,
            submitted_at=created_at,
        ),
        created_at=created_at,
    )
    db.add(observation)
    db.flush()
    image = ObservationImage(
        observation_id=observation.id,
        image_url="/uploads/evidence.png",
    )
    db.add(image)
    db.commit()

    reviewer_settings = configure_test_reviewer()
    client = TestClient(app, raise_server_exceptions=True)
    login_reviewer(client)

    yield {
        "client": client,
        "db": db,
        "observation_id": observation.id,
        "image_id": image.id,
    }

    db.close()
    restore_test_reviewer(reviewer_settings)
    app.dependency_overrides.pop(get_db, None)
    main_module.UPLOADS_DIR = original_uploads_dir
    reports_module.REPORTS_DIR = original_reports_dir
    connection.close()


def _azure_settings(ai_settings, provider_settings) -> None:
    ai_settings.azure_openai_enabled = True
    ai_settings.azure_credentials_present = True
    ai_settings.azure_openai_deployment = "mydeploy"
    provider_settings.azure_openai_endpoint = "https://fake.openai.azure.com/"
    provider_settings.azure_openai_api_key = "fake-key"
    provider_settings.azure_openai_deployment = "mydeploy"
    provider_settings.azure_openai_api_version = "v1"
    provider_settings.azure_openai_timeout_seconds = 30


def _valid_azure_payload(image_id: int, indicator_type: str = "crack") -> dict:
    return {
        "schema_version": "2",
        "provider": "azure:mydeploy",
        "overall_summary": "A narrow linear opening is visible in the masonry.",
        "evidence_sufficiency": "partial",
        "indicators": [
            {
                "indicator_type": indicator_type,
                "evidence_location": "centre of image",
                "image_refs": [image_id],
                "confidence": 0.78,
                "supporting_evidence": "A narrow linear opening is visible.",
                "severity_contribution": 3,
            }
        ],
        "insufficient_reason": None,
    }


def test_connection_failure_persists_failed_then_mock_and_renders(
    failure_history_context,
):
    from app.models import AIAnalysisRecord, Observation, RiskCase

    client = failure_history_context["client"]
    db = failure_history_context["db"]
    leaked_exception_text = "credential=must-not-be-persisted"
    connection_error = APIConnectionError(
        message=leaked_exception_text,
        request=httpx.Request(
            "POST",
            "https://fake.openai.azure.com/openai/v1/",
        ),
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = connection_error

    with (
        patch("app.services.ai_analysis.settings") as ai_settings,
        patch(
            "app.services.providers.azure_openai_provider.settings"
        ) as provider_settings,
        patch("openai.OpenAI", return_value=fake_client),
    ):
        _azure_settings(ai_settings, provider_settings)
        response = post_form(
            client,
            f"/observations/{failure_history_context['observation_id']}/analyze",
            follow_redirects=False,
        )

    assert response.status_code == 303
    db.expire_all()
    observation = db.get(
        Observation,
        failure_history_context["observation_id"],
    )
    records = (
        db.query(AIAnalysisRecord)
        .filter_by(observation_id=observation.id)
        .order_by(AIAnalysisRecord.id)
        .all()
    )
    assert [record.status for record in records] == ["failed", "mock"]
    assert [record.provider for record in records] == [
        "azure:mydeploy",
        "mock",
    ]
    assert (
        records[0].diagnostic
        == "transport_error: the Azure OpenAI request could not be completed."
    )
    assert records[0].created_at is not None
    assert records[1].created_at is not None
    assert records[1].diagnostic is None
    assert leaked_exception_text not in records[0].diagnostic
    assert observation.ai_analysis_status == "mock"
    assert observation.ai_provider == "mock"
    assert leaked_exception_text not in observation.ai_raw_response
    raw = json.loads(observation.ai_raw_response)
    assert raw["provider"] == "mock"
    assert raw["indicators"][0]["image_refs"] == [
        failure_history_context["image_id"]
    ]

    review_page = client.get(
        f"/observations/{observation.id}/ai_review"
    )
    assert review_page.status_code == 200
    assert "Analysis Attempt History" in review_page.text
    assert "azure:mydeploy" in review_page.text
    assert records[0].diagnostic in review_page.text
    assert review_page.text.index(records[0].diagnostic) < review_page.text.index(
        "labelled mock fallback"
    )

    finalize = post_form(
        client,
        f"/observations/{observation.id}/create_risk_case",
        data={
            "final_damage_tags": "crack",
            "final_severity": "2",
            "final_ai_summary": observation.ai_summary,
            "final_recommended_action": observation.ai_recommended_action,
        },
        follow_redirects=False,
    )
    assert finalize.status_code == 303
    db.expire_all()
    case = db.query(RiskCase).one()
    assert [
        attempt["status"]
        for attempt in case.final_snapshot["analysis_attempts"]
    ] == ["failed", "mock"]

    live_only_diagnostic = "MUTATED live attempt must not enter reports"
    db.add(
        AIAnalysisRecord(
            observation_id=observation.id,
            status="failed",
            provider="azure:later-deployment",
            diagnostic=live_only_diagnostic,
        )
    )
    db.commit()

    markdown_report = client.get(f"/cases/{case.id}/report.md")
    html_report = client.get(f"/cases/{case.id}/report")
    for report_text in (markdown_report.text, html_report.text):
        assert "Analysis Attempt History" in report_text
        assert "azure:mydeploy" in report_text
        assert records[0].diagnostic in report_text
        assert report_text.index(records[0].diagnostic) < report_text.index(
            "abelled mock fallback"
        )
        assert leaked_exception_text not in report_text
        assert live_only_diagnostic not in report_text


def test_malformed_json_remains_one_failed_record_without_mock(
    failure_history_context,
):
    from app.models import AIAnalysisRecord, Observation

    client = failure_history_context["client"]
    db = failure_history_context["db"]
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="This is not JSON.")
            )
        ]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with (
        patch("app.services.ai_analysis.settings") as ai_settings,
        patch(
            "app.services.providers.azure_openai_provider.settings"
        ) as provider_settings,
        patch("openai.OpenAI", return_value=fake_client),
    ):
        _azure_settings(ai_settings, provider_settings)
        response = post_form(
            client,
            f"/observations/{failure_history_context['observation_id']}/analyze",
            follow_redirects=False,
        )

    assert response.status_code == 303
    db.expire_all()
    observation = db.get(
        Observation,
        failure_history_context["observation_id"],
    )
    records = (
        db.query(AIAnalysisRecord)
        .filter_by(observation_id=observation.id)
        .order_by(AIAnalysisRecord.id)
        .all()
    )
    assert len(records) == 1
    assert records[0].status == "failed"
    assert records[0].provider == "azure:mydeploy"
    assert records[0].diagnostic == "Azure response was not valid JSON."
    assert all(record.provider != "mock" for record in records)
    assert observation.ai_analysis_status == "failed"
    assert observation.ai_provider == "azure:mydeploy"
    stored = json.loads(observation.ai_raw_response)
    assert stored["validation_status"] == "failed"
    assert stored["raw_payload"]["validation_status"] == "failed"


def test_mocked_gpt5_mini_success_persists_schema_v2_azure_result(
    failure_history_context,
):
    from app.models import AIAnalysisRecord, Observation

    client = failure_history_context["client"]
    db = failure_history_context["db"]
    payload = _valid_azure_payload(failure_history_context["image_id"])
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload))
            )
        ]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with (
        patch("app.services.ai_analysis.settings") as ai_settings,
        patch(
            "app.services.providers.azure_openai_provider.settings"
        ) as provider_settings,
        patch("openai.OpenAI", return_value=fake_client),
    ):
        _azure_settings(ai_settings, provider_settings)
        response = post_form(
            client,
            f"/observations/{failure_history_context['observation_id']}/analyze",
            follow_redirects=False,
        )

    assert response.status_code == 303
    db.expire_all()
    observation = db.get(
        Observation,
        failure_history_context["observation_id"],
    )
    records = (
        db.query(AIAnalysisRecord)
        .filter_by(observation_id=observation.id)
        .order_by(AIAnalysisRecord.id)
        .all()
    )
    assert [(record.status, record.provider) for record in records] == [
        ("complete", "azure:mydeploy")
    ]
    assert observation.ai_analysis_status == "complete"
    assert observation.ai_provider == "azure:mydeploy"
    stored = json.loads(observation.ai_raw_response)
    assert stored["schema_version"] == "2"
    assert stored["provider"] == "azure:mydeploy"
    request = fake_client.chat.completions.create.call_args.kwargs
    assert request["max_completion_tokens"] == 600
    assert request["response_format"] == {"type": "json_object"}
    assert "temperature" not in request


def test_schema_invalid_payload_persists_one_failed_record_without_mock(
    failure_history_context,
):
    from app.models import AIAnalysisRecord, Observation

    client = failure_history_context["client"]
    db = failure_history_context["db"]
    payload = _valid_azure_payload(
        failure_history_context["image_id"],
        indicator_type="unsupported_damage",
    )
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload))
            )
        ]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with (
        patch("app.services.ai_analysis.settings") as ai_settings,
        patch(
            "app.services.providers.azure_openai_provider.settings"
        ) as provider_settings,
        patch("openai.OpenAI", return_value=fake_client),
    ):
        _azure_settings(ai_settings, provider_settings)
        response = post_form(
            client,
            f"/observations/{failure_history_context['observation_id']}/analyze",
            follow_redirects=False,
        )

    assert response.status_code == 303
    db.expire_all()
    observation = db.get(
        Observation,
        failure_history_context["observation_id"],
    )
    records = (
        db.query(AIAnalysisRecord)
        .filter_by(observation_id=observation.id)
        .order_by(AIAnalysisRecord.id)
        .all()
    )
    assert [(record.status, record.provider) for record in records] == [
        ("failed", "azure:mydeploy")
    ]
    assert observation.ai_analysis_status == "failed"
    assert observation.ai_provider == "azure:mydeploy"
    stored = json.loads(observation.ai_raw_response)
    assert stored["validation_status"] == "failed"
    assert "Unknown indicator_type" in stored["validation_error"]
