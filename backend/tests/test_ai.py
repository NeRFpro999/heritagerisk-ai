"""
Tests for the AI analysis service layer.

These tests NEVER call the real Azure OpenAI API. They cover:
  - Mock mode (default, no credentials needed)
  - Missing-credentials fallback
  - Provider validation logic
  - Invalid/bad JSON from Azure being handled safely
  - Tag merging behaviour in the route helper
  - Risk case creation still works after AI analysis runs
"""

import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — allow importing app modules without a running database
# ---------------------------------------------------------------------------

def _make_fake_settings(*, enabled: bool, has_creds: bool) -> MagicMock:
    s = MagicMock()
    s.azure_openai_enabled = enabled
    s.ai_analysis_enabled = enabled
    s.azure_credentials_present = has_creds
    s.azure_openai_endpoint = "https://fake.openai.azure.com/" if has_creds else ""
    s.azure_openai_api_key = "fake-key" if has_creds else ""
    s.azure_openai_deployment = "gpt-5-mini" if has_creds else ""
    s.azure_openai_timeout_seconds = 30
    return s


# ---------------------------------------------------------------------------
# Tests: mock mode
# ---------------------------------------------------------------------------

class TestMockAnalysis:
    def test_disabled_returns_mock(self):
        """When AZURE_OPENAI_ENABLED=false, always return a mock result."""
        from app.services.ai_analysis import analyze_observation_image, AIAnalysisResult

        with patch("app.services.ai_analysis.settings") as mock_settings:
            mock_settings.azure_openai_enabled = False
            result = analyze_observation_image(image_path="", notes="crack in wall")

        assert isinstance(result, AIAnalysisResult)
        assert result.provider == "mock"
        assert "crack" in result.damage_tags
        assert 1 <= result.severity <= 5
        assert 0 <= result.confidence <= 100

    def test_mock_detects_keywords(self):
        """Mock scanner picks up known damage keywords from notes."""
        from app.services.ai_analysis import _mock_analyze

        result = _mock_analyze("", "There is visible graffiti and some water staining")
        assert "graffiti" in result.damage_tags
        assert "water_staining" in result.damage_tags

    def test_mock_uses_other_when_no_keywords(self):
        """Mock always returns at least ['other'] when nothing is detected."""
        from app.services.ai_analysis import _mock_analyze

        result = _mock_analyze("", "Looks fine to me")
        assert result.damage_tags == ["other"]

    def test_mock_tags_are_in_allowed_set(self):
        """Every tag the mock produces must be in the allowed taxonomy."""
        from app.services.ai_analysis import _mock_analyze, ALLOWED_TAGS

        result = _mock_analyze("", "crack erosion vegetation graffiti water rust")
        for tag in result.damage_tags:
            assert tag in ALLOWED_TAGS, f"Mock produced unexpected tag: {tag!r}"

    def test_missing_credentials_falls_back_to_mock(self):
        """When AI is enabled but credentials are missing, fall back to mock."""
        from app.services.ai_analysis import analyze_observation_image

        with patch("app.services.ai_analysis.settings") as mock_settings:
            mock_settings.azure_openai_enabled = True
            mock_settings.azure_credentials_present = False
            result = analyze_observation_image(image_path="", notes="crack")

        assert result.provider == "mock"
        assert "mock analysis" in result.summary.lower()

    def test_mock_summary_says_demo_or_triage_only(self):
        """Mock summary must state it is for demonstration/triage only."""
        from app.services.ai_analysis import _mock_analyze

        result = _mock_analyze("", "crack in wall")
        lower = result.summary.lower()
        assert "demonstration" in lower or "triage" in lower or "mock" in lower

    def test_mock_recommended_action_is_safe(self):
        """Mock recommended action must not suggest touching, repairing, or entering a site."""
        from app.services.ai_analysis import _mock_analyze

        result = _mock_analyze("", "crack in wall")
        lower = result.recommended_action.lower()
        # Must contain a triage/safety directive
        assert "triage" in lower or "human" in lower or "review" in lower or "advice" in lower
        # Must not instruct the user to perform the action (imperative form)
        for unsafe_instruction in ("please repair", "you should repair", "go repair",
                                   "please clean", "please touch", "please climb",
                                   "please enter"):
            assert unsafe_instruction not in lower, (
                f"Unsafe instruction found in mock recommended_action: {unsafe_instruction!r}"
            )

    def test_mock_result_never_implies_final_decision(self):
        """Mock summary must not claim AI is making a final conservation decision."""
        from app.services.ai_analysis import _mock_analyze

        result = _mock_analyze("", "erosion on plinth")
        lower = result.summary.lower()
        for final_phrase in ("is safe", "is not safe", "must be repaired", "confirmed damage"):
            assert final_phrase not in lower, (
                f"Mock summary implies final decision: {final_phrase!r}"
            )


# ---------------------------------------------------------------------------
# Tests: AzureOpenAIImageAnalyzer validation
# ---------------------------------------------------------------------------

class TestProviderValidation:
    def test_missing_env_uses_mock(self):
        """Missing Azure provider credentials use the mock fallback."""
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = ""
            s.azure_openai_api_key = ""
            s.azure_openai_deployment = ""
            s.azure_openai_timeout_seconds = 30
            analyzer = AzureOpenAIImageAnalyzer()

        result = analyzer.analyze("", notes="crack")
        assert result.provider == "mock"
        assert "crack" in result.damage_tags

    def test_missing_image_returns_safe_result(self):
        """analyze() returns a safe result (not an exception) for a missing image."""
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = "https://fake.openai.azure.com/"
            s.azure_openai_api_key = "fake-key"
            s.azure_openai_deployment = "gpt-5-mini"
            s.azure_openai_timeout_seconds = 30
            analyzer = AzureOpenAIImageAnalyzer()

        result = analyzer.analyze("/nonexistent/path/image.jpg", notes="crack")
        assert result.provider == "mock"
        assert "crack" in result.damage_tags

    @pytest.mark.parametrize(
        ("endpoint", "api_key", "deployment"),
        [
            ("", "fake-key", "gpt-5-mini"),
            ("https://fake.openai.azure.com/", "", "gpt-5-mini"),
            ("https://fake.openai.azure.com/", "fake-key", ""),
        ],
    )
    def test_missing_required_azure_setting_uses_mock(self, endpoint, api_key, deployment):
        """Missing key, endpoint, or deployment each use mock fallback."""
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = endpoint
            s.azure_openai_api_key = api_key
            s.azure_openai_deployment = deployment
            s.azure_openai_timeout_seconds = 30
            analyzer = AzureOpenAIImageAnalyzer()

        result = analyzer.analyze("", notes="water staining")
        assert result.provider == "mock"
        assert "water_staining" in result.damage_tags

    def test_endpoint_is_normalised_for_v1(self):
        from app.services.providers.azure_openai_provider import _normalise_endpoint

        assert (
            _normalise_endpoint("https://fake.openai.azure.com/")
            == "https://fake.openai.azure.com/openai/v1/"
        )
        assert (
            _normalise_endpoint("https://fake.openai.azure.com/openai/v1/")
            == "https://fake.openai.azure.com/openai/v1/"
        )

    def test_azure_api_exception_uses_mock(self, tmp_path):
        """Any Azure API/client exception falls back to mock."""
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"not-a-real-png-but-mime-is-guessed")

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("non-secret failure")

        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = "https://fake.openai.azure.com/"
            s.azure_openai_api_key = "fake-key"
            s.azure_openai_deployment = "gpt-5-mini"
            s.azure_openai_timeout_seconds = 30
            analyzer = AzureOpenAIImageAnalyzer()

        with patch("openai.OpenAI", return_value=fake_client):
            result = analyzer.analyze(str(image_path), notes="erosion")

        assert result.provider == "mock"
        assert "erosion" in result.damage_tags

    def test_successful_azure_response_returns_deployment_provider(self, tmp_path):
        """Mocked successful Azure JSON returns provider azure:gpt-5-mini."""
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"not-a-real-png-but-mime-is-guessed")

        fake_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "damage_tags": ["crack"],
                                "severity": 3,
                                "confidence": 81,
                                "summary": "Visible crack along the wall.",
                                "uncertainty": "The crack depth cannot be determined.",
                                "recommended_action": "Human review required before action.",
                            }
                        )
                    )
                )
            ]
        )
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = "https://fake.openai.azure.com/"
            s.azure_openai_api_key = "fake-key"
            s.azure_openai_deployment = "gpt-5-mini"
            s.azure_openai_timeout_seconds = 30
            analyzer = AzureOpenAIImageAnalyzer()

        with patch("openai.OpenAI", return_value=fake_client) as openai_cls:
            result = analyzer.analyze(str(image_path), notes="crack")

        assert result.provider == "azure:gpt-5-mini"
        assert result.damage_tags == ["crack"]
        assert result.confidence == 81
        assert result.uncertainty == "The crack depth cannot be determined."
        openai_cls.assert_called_once_with(
            api_key="fake-key",
            base_url="https://fake.openai.azure.com/openai/v1/",
            timeout=30,
        )
        fake_client.chat.completions.create.assert_called_once()
        call_kwargs = fake_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-5-mini"
        assert call_kwargs["max_completion_tokens"] == 600

    def test_multiple_images_are_sent_in_one_analysis_request(self, tmp_path):
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        first_path = tmp_path / "first.png"
        second_path = tmp_path / "second.jpg"
        first_path.write_bytes(b"first-image")
        second_path.write_bytes(b"second-image")
        fake_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "damage_tags": ["erosion"],
                                "severity": 2,
                                "confidence": 65,
                                "summary": "Possible erosion is visible.",
                                "uncertainty": "Lighting differs between images.",
                                "recommended_action": "Human review required.",
                            }
                        )
                    )
                )
            ]
        )
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch("app.services.providers.azure_openai_provider.settings") as settings:
            settings.azure_openai_endpoint = "https://fake.openai.azure.com/"
            settings.azure_openai_api_key = "fake-key"
            settings.azure_openai_deployment = "gpt-5-mini"
            settings.azure_openai_timeout_seconds = 30
            analyzer = AzureOpenAIImageAnalyzer()

        with patch("openai.OpenAI", return_value=fake_client):
            result = analyzer.analyze_many(
                [str(first_path), str(second_path)],
                notes="Site name: Test Memorial",
            )

        assert result.provider == "azure:gpt-5-mini"
        call_kwargs = fake_client.chat.completions.create.call_args.kwargs
        user_content = call_kwargs["messages"][1]["content"]
        assert len([item for item in user_content if item["type"] == "image_url"]) == 2
        assert user_content[-1] == {
            "type": "text",
            "text": "Observer notes: Site name: Test Memorial",
        }


# ---------------------------------------------------------------------------
# Tests: response validation
# ---------------------------------------------------------------------------

class TestResponseValidation:
    def _make_analyzer(self):
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer
        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = "https://fake.openai.azure.com/"
            s.azure_openai_api_key = "fake-key"
            s.azure_openai_deployment = "gpt-5-mini"
            s.azure_openai_timeout_seconds = 30
            return AzureOpenAIImageAnalyzer()

    def test_valid_response_parsed_correctly(self):
        analyzer = self._make_analyzer()
        data = {
            "damage_tags": ["crack", "erosion"],
            "severity": 3,
            "confidence": 72,
            "summary": "Visible crack along the east wall.",
            "uncertainty": "The image does not show the crack depth.",
            "recommended_action": "Schedule inspection within 30 days.",
        }
        result = analyzer._validate_response(data)
        assert result.damage_tags == ["crack", "erosion"]
        assert result.severity == 3
        assert result.confidence == 72
        assert result.uncertainty == "The image does not show the crack depth."
        assert result.provider == "azure:gpt-5-mini"
        assert result.raw_response is not None
        # raw_response must not contain base64 image data — just the small JSON fields
        assert len(result.raw_response) < 2000

    def test_unknown_tags_are_dropped(self):
        analyzer = self._make_analyzer()
        data = {
            "damage_tags": ["crack", "alien_invasion", "fire"],
            "severity": 2,
            "confidence": 50,
            "summary": "Some damage.",
            "recommended_action": "Inspect.",
        }
        result = analyzer._validate_response(data)
        assert "alien_invasion" not in result.damage_tags
        assert "fire" not in result.damage_tags
        assert "crack" in result.damage_tags

    def test_empty_tags_becomes_other(self):
        analyzer = self._make_analyzer()
        data = {
            "damage_tags": [],
            "severity": 1,
            "confidence": 60,
            "summary": "No damage visible.",
            "recommended_action": "Continue monitoring.",
        }
        result = analyzer._validate_response(data)
        assert result.damage_tags == ["other"]

    def test_severity_clamped_to_range(self):
        analyzer = self._make_analyzer()
        result_low = analyzer._validate_response({
            "damage_tags": ["crack"], "severity": -5,
            "confidence": 50, "summary": "x", "recommended_action": "y",
        })
        result_high = analyzer._validate_response({
            "damage_tags": ["crack"], "severity": 99,
            "confidence": 50, "summary": "x", "recommended_action": "y",
        })
        assert result_low.severity == 1
        assert result_high.severity == 5

    def test_confidence_clamped_to_range(self):
        analyzer = self._make_analyzer()
        result = analyzer._validate_response({
            "damage_tags": ["crack"], "severity": 2,
            "confidence": 999, "summary": "x", "recommended_action": "y",
        })
        assert result.confidence == 100

    def test_bad_json_string_returns_mock_result(self, tmp_path):
        """Simulate the model returning prose instead of JSON."""
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"not-a-real-png-but-mime-is-guessed")

        fake_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="This is not JSON.")
                )
            ]
        )
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = "https://fake.openai.azure.com/"
            s.azure_openai_api_key = "fake-key"
            s.azure_openai_deployment = "gpt-5-mini"
            s.azure_openai_timeout_seconds = 30
            analyzer = AzureOpenAIImageAnalyzer()

        with patch("openai.OpenAI", return_value=fake_client):
            result = analyzer.analyze(str(image_path), notes="crack")

        assert result.provider == "mock"
        assert "crack" in result.damage_tags


# ---------------------------------------------------------------------------
# Tests: submitted evidence and AI suggestions remain separate
# ---------------------------------------------------------------------------

class TestEvidenceSeparation:
    def test_ai_result_does_not_overwrite_human_tags_or_severity(self):
        from app.main import apply_ai_analysis_result
        from app.models import Observation
        from app.services.ai_analysis import AIAnalysisResult

        observation = Observation(
            site_id=1,
            damage_tags="crack,graffiti",
            severity=2,
        )
        result = AIAnalysisResult(
            damage_tags=["erosion"],
            severity=5,
            confidence=74,
            summary="Possible erosion is visible.",
            recommended_action="Human review required.",
            provider="azure:gpt-5-mini",
        )

        apply_ai_analysis_result(observation, result)

        assert observation.damage_tags == "crack,graffiti"
        assert observation.severity == 2
        raw_data = json.loads(observation.ai_raw_response)
        assert raw_data["damage_tags"] == ["erosion"]
        assert raw_data["severity"] == 5


# ---------------------------------------------------------------------------
# Tests: risk case creation unaffected by AI fields
# ---------------------------------------------------------------------------

class TestRiskCaseAfterAI:
    def test_risk_score_calculated_from_tags_and_severity(self):
        """calculate_risk() works normally regardless of AI fields."""
        from app.risk import calculate_risk

        score, band = calculate_risk(["crack", "erosion"], severity=3)
        assert 0 <= score <= 100
        assert band in ("Low", "Medium", "High")

    def test_empty_tags_gives_zero_score(self):
        from app.risk import calculate_risk

        score, band = calculate_risk([], severity=1)
        assert score == 0
        assert band == "Low"
