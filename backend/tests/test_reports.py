"""
Tests for reports.py — verifies that generate_report() produces a
Markdown evidence report with the required 7-section structure.

These tests use lightweight fakes; no database or filesystem is required
beyond a writable temp directory (patched in via monkeypatch).
"""

import types
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.reports import generate_report


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _make_site(
    id=1,
    name="Blarney Castle",
    location="Cork, Ireland",
    description="Medieval castle, 15th century.",
):
    s = types.SimpleNamespace(
        id=id, name=name, location=location, description=description
    )
    return s


def _make_observation(
    id=10,
    notes="Cracks visible on the south-east corner.",
    damage_tags="crack,erosion",
    severity=3,
    image_filename="abc123.jpg",
    ai_analysis_status="complete",
    ai_summary="Visible crack pattern consistent with structural movement.",
    ai_confidence=72,
):
    obs = types.SimpleNamespace(
        id=id,
        notes=notes,
        damage_tags=damage_tags,
        severity=severity,
        image_filename=image_filename,
        created_at=datetime(2025, 6, 1, 10, 30),
        ai_analysis_status=ai_analysis_status,
        ai_summary=ai_summary,
        ai_confidence=ai_confidence,
    )
    # Replicate the model property
    obs.tags_list = [t.strip() for t in damage_tags.split(",") if t.strip()] if damage_tags else []
    return obs


def _make_case(
    id=99,
    risk_score=63,
    risk_band="High",
    status="Needs Review",
    routed_to="Conservation Officer",
):
    return types.SimpleNamespace(
        id=id,
        risk_score=risk_score,
        risk_band=risk_band,
        status=status,
        routed_to=routed_to,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate(tmp_path, site=None, obs=None, case=None):
    site = site or _make_site()
    obs = obs or _make_observation()
    case = case or _make_case()
    with patch("app.reports.REPORTS_DIR", tmp_path):
        path = generate_report(case, obs, site)
    return Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Required section headings
# ---------------------------------------------------------------------------

class TestRequiredSections:
    def test_report_title(self, tmp_path):
        md = _generate(tmp_path)
        assert "HeritageRisk AI Evidence Report" in md

    def test_site_information_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Site Information" in md

    def test_observation_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "## 2. Observation" in md

    def test_visible_risk_indicators_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Visible Risk Indicators" in md

    def test_risk_case_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Risk Case" in md

    def test_safety_ethics_notice_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Safety and Ethics Notice" in md

    def test_risk_scoring_method_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Risk Scoring Method" in md

    def test_human_review_recommended(self, tmp_path):
        md = _generate(tmp_path)
        assert "Human review recommended before any action is taken." in md


# ---------------------------------------------------------------------------
# Real data mapped correctly
# ---------------------------------------------------------------------------

class TestRealDataMapping:
    def test_site_name_appears(self, tmp_path):
        md = _generate(tmp_path, site=_make_site(name="Blarney Castle"))
        assert "Blarney Castle" in md

    def test_site_location_appears(self, tmp_path):
        md = _generate(tmp_path, site=_make_site(location="Cork, Ireland"))
        assert "Cork, Ireland" in md

    def test_observation_id_appears(self, tmp_path):
        md = _generate(tmp_path, obs=_make_observation(id=42))
        assert "42" in md

    def test_damage_tags_appear(self, tmp_path):
        md = _generate(tmp_path, obs=_make_observation(damage_tags="crack,erosion"))
        assert "crack" in md
        assert "erosion" in md

    def test_risk_score_appears(self, tmp_path):
        md = _generate(tmp_path, case=_make_case(risk_score=77))
        assert "77" in md

    def test_risk_band_appears(self, tmp_path):
        md = _generate(tmp_path, case=_make_case(risk_band="High"))
        assert "High" in md

    def test_status_appears(self, tmp_path):
        md = _generate(tmp_path, case=_make_case(status="Verified"))
        assert "Verified" in md

    def test_routed_to_appears(self, tmp_path):
        md = _generate(tmp_path, case=_make_case(routed_to="Conservation Officer"))
        assert "Conservation Officer" in md

    def test_contributor_notes_appear(self, tmp_path):
        md = _generate(tmp_path, obs=_make_observation(notes="South wall cracking."))
        assert "South wall cracking." in md


# ---------------------------------------------------------------------------
# Safe fallbacks — missing fields must not crash
# ---------------------------------------------------------------------------

class TestSafeFallbacks:
    def test_missing_location_does_not_crash(self, tmp_path):
        md = _generate(tmp_path, site=_make_site(location=None))
        assert "Not provided" in md

    def test_missing_description_does_not_crash(self, tmp_path):
        md = _generate(tmp_path, site=_make_site(description=None))
        assert "Not provided" in md

    def test_missing_notes_does_not_crash(self, tmp_path):
        md = _generate(tmp_path, obs=_make_observation(notes=None))
        assert "No notes provided." in md

    def test_missing_image_does_not_crash(self, tmp_path):
        md = _generate(tmp_path, obs=_make_observation(image_filename=None))
        assert "No image uploaded." in md

    def test_no_damage_tags_does_not_crash(self, tmp_path):
        obs = _make_observation(damage_tags="")
        md = _generate(tmp_path, obs=obs)
        assert "None recorded" in md

    def test_missing_routed_to_shows_fallback(self, tmp_path):
        md = _generate(tmp_path, case=_make_case(routed_to=None))
        assert "Not routed yet" in md


# ---------------------------------------------------------------------------
# AI analysis status handling
# ---------------------------------------------------------------------------

class TestAIAnalysisSummary:
    def test_not_run_shows_no_analysis_message(self, tmp_path):
        obs = _make_observation(ai_analysis_status="not_run", ai_summary=None)
        md = _generate(tmp_path, obs=obs)
        assert "No AI analysis has been run for this observation." in md

    def test_complete_includes_summary(self, tmp_path):
        obs = _make_observation(
            ai_analysis_status="complete",
            ai_summary="Visible crack along east wall.",
        )
        md = _generate(tmp_path, obs=obs)
        assert "Visible crack along east wall." in md

    def test_mock_labels_as_fallback(self, tmp_path):
        obs = _make_observation(
            ai_analysis_status="mock",
            ai_summary="Mock: crack detected.",
        )
        md = _generate(tmp_path, obs=obs)
        assert "Mock/fallback analysis" in md

    def test_failed_shows_failure_message(self, tmp_path):
        obs = _make_observation(ai_analysis_status="failed", ai_summary=None)
        md = _generate(tmp_path, obs=obs)
        assert "AI analysis was attempted but failed." in md

    def test_confidence_shown_when_complete(self, tmp_path):
        obs = _make_observation(ai_analysis_status="complete", ai_confidence=85)
        md = _generate(tmp_path, obs=obs)
        assert "85" in md

    def test_confidence_not_available_when_not_run(self, tmp_path):
        obs = _make_observation(ai_analysis_status="not_run", ai_confidence=None)
        md = _generate(tmp_path, obs=obs)
        assert "Not available" in md

    def test_ai_summary_does_not_imply_final_decision(self, tmp_path):
        obs = _make_observation(
            ai_analysis_status="complete",
            ai_summary="Crack pattern detected.",
        )
        md = _generate(tmp_path, obs=obs)
        lower = md.lower()
        for final_phrase in ("confirmed damage", "is safe", "is not safe", "must be repaired"):
            assert final_phrase not in lower

    def test_report_contains_triage_principle(self, tmp_path):
        obs = _make_observation(ai_analysis_status="complete", ai_summary="Crack detected.")
        md = _generate(tmp_path, obs=obs)
        assert "Humans verify" in md


# ---------------------------------------------------------------------------
# File written correctly
# ---------------------------------------------------------------------------

class TestFileOutput:
    def test_file_created_with_correct_name(self, tmp_path):
        case = _make_case(id=7)
        _generate(tmp_path, case=case)
        assert (tmp_path / "case_7.md").exists()

    def test_return_value_is_absolute_path(self, tmp_path):
        case = _make_case(id=7)
        site = _make_site()
        obs = _make_observation()
        with patch("app.reports.REPORTS_DIR", tmp_path):
            result = generate_report(case, obs, site)
        assert Path(result).is_absolute()
