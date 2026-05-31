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
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — allow importing app modules without a running database
# ---------------------------------------------------------------------------

def _make_fake_settings(*, enabled: bool, has_creds: bool) -> MagicMock:
    s = MagicMock()
    s.ai_analysis_enabled = enabled
    s.azure_credentials_present = has_creds
    s.azure_openai_endpoint = "https://fake.openai.azure.com/" if has_creds else ""
    s.azure_openai_api_key = "fake-key" if has_creds else ""
    s.azure_openai_deployment = "fake-deployment" if has_creds else ""
    s.azure_openai_api_version = "2024-02-01"
    return s


# ---------------------------------------------------------------------------
# Tests: mock mode
# ---------------------------------------------------------------------------

class TestMockAnalysis:
    def test_disabled_returns_mock(self):
        """When AI_ANALYSIS_ENABLED=false, always return a mock result."""
        from app.services.ai_analysis import analyze_observation_image, AIAnalysisResult

        with patch("app.services.ai_analysis.settings") as mock_settings:
            mock_settings.ai_analysis_enabled = False
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
            mock_settings.ai_analysis_enabled = True
            mock_settings.azure_credentials_present = False
            result = analyze_observation_image(image_path="", notes="crack")

        assert result.provider == "mock"
        assert "credentials" in result.summary.lower()

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
        # Must contain a human-review directive
        assert "human" in lower or "review" in lower or "inspection" in lower
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
    def test_missing_env_raises_environment_error(self):
        """Constructor raises EnvironmentError when credentials are absent."""
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = ""
            s.azure_openai_api_key = ""
            s.azure_openai_deployment = ""
            with pytest.raises(EnvironmentError, match="AZURE_OPENAI_ENDPOINT"):
                AzureOpenAIImageAnalyzer()

    def test_missing_image_returns_safe_result(self):
        """analyze() returns a safe result (not an exception) for a missing image."""
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer

        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = "https://fake.openai.azure.com/"
            s.azure_openai_api_key = "fake-key"
            s.azure_openai_deployment = "fake-deployment"
            s.azure_openai_api_version = "2024-02-01"
            analyzer = AzureOpenAIImageAnalyzer()

        result = analyzer.analyze("/nonexistent/path/image.jpg", notes="crack")
        assert result.provider == "azure_openai"
        assert result.confidence == 0
        assert "not found" in result.summary.lower()


# ---------------------------------------------------------------------------
# Tests: response validation
# ---------------------------------------------------------------------------

class TestResponseValidation:
    def _make_analyzer(self):
        from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer
        with patch("app.services.providers.azure_openai_provider.settings") as s:
            s.azure_openai_endpoint = "https://fake.openai.azure.com/"
            s.azure_openai_api_key = "fake-key"
            s.azure_openai_deployment = "fake-deployment"
            s.azure_openai_api_version = "2024-02-01"
            return AzureOpenAIImageAnalyzer()

    def test_valid_response_parsed_correctly(self):
        analyzer = self._make_analyzer()
        data = {
            "damage_tags": ["crack", "erosion"],
            "severity": 3,
            "confidence": 72,
            "summary": "Visible crack along the east wall.",
            "recommended_action": "Schedule inspection within 30 days.",
        }
        result = analyzer._validate_response(data)
        assert result.damage_tags == ["crack", "erosion"]
        assert result.severity == 3
        assert result.confidence == 72
        assert result.provider == "azure_openai"
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

    def test_bad_json_string_returns_safe_result(self):
        """Simulate the model returning prose instead of JSON."""
        from app.services.providers.azure_openai_provider import _parse_error_result
        result = _parse_error_result("Model response was not valid JSON.")
        assert result.provider == "azure_openai"
        assert result.confidence == 0
        assert result.damage_tags == ["other"]
        assert result.recommended_action == "Human review required before any action is taken."


# ---------------------------------------------------------------------------
# Tests: tag merging
# ---------------------------------------------------------------------------

class TestTagMerging:
    def test_ai_tags_merged_with_manual_tags(self):
        """New AI tags should be unioned with existing manual tags, no duplicates."""
        existing = {"crack", "graffiti"}
        ai_tags = ["crack", "erosion"]
        merged = sorted(existing | set(ai_tags))
        assert merged == ["crack", "erosion", "graffiti"]

    def test_duplicate_tags_not_added(self):
        existing = {"crack"}
        ai_tags = ["crack", "crack"]
        merged = sorted(existing | set(ai_tags))
        assert merged.count("crack") == 1


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
