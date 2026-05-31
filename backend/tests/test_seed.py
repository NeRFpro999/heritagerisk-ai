"""
Tests for the seed data definition in app/seed.py.

These tests validate the SEED_SITES and SEED_OBSERVATIONS constants and the
risk-scoring logic against them — no database is required.

A separate integration test (test_seed_db.py) could exercise the actual seed()
function against a real in-memory SQLite DB, but the constants-level checks here
are sufficient to catch the most common breakage: wrong names, wrong bands,
duplicate statuses, unsafe recommended actions.
"""

import pytest

from app.seed import SEED_SITES, SEED_OBSERVATIONS
from app.risk import calculate_risk


# ---------------------------------------------------------------------------
# Site definitions
# ---------------------------------------------------------------------------

class TestSeedSites:
    def test_exactly_three_sites(self):
        assert len(SEED_SITES) == 3

    def test_required_site_names_present(self):
        names = {s["name"] for s in SEED_SITES}
        assert "Old Stone Church" in names
        assert "Historic Iron Bridge" in names
        assert "Memorial Statue" in names

    def test_all_sites_have_location(self):
        for s in SEED_SITES:
            assert s.get("location"), f"Site {s['name']!r} missing location"

    def test_all_sites_have_description(self):
        for s in SEED_SITES:
            assert s.get("description"), f"Site {s['name']!r} missing description"


# ---------------------------------------------------------------------------
# Observation definitions
# ---------------------------------------------------------------------------

class TestSeedObservations:
    def test_exactly_three_observations(self):
        assert len(SEED_OBSERVATIONS) == 3

    def test_one_observation_per_site(self):
        site_names = [o["site_name"] for o in SEED_OBSERVATIONS]
        assert len(site_names) == len(set(site_names)), "Duplicate site_name in observations"

    def test_all_observations_reference_known_sites(self):
        known = {s["name"] for s in SEED_SITES}
        for o in SEED_OBSERVATIONS:
            assert o["site_name"] in known, f"Unknown site_name: {o['site_name']!r}"

    def test_severities_differ(self):
        severities = [o["severity"] for o in SEED_OBSERVATIONS]
        assert len(set(severities)) == 3, "All three observations should have different severity scores"

    def test_damage_tags_differ(self):
        tags = [o["damage_tags"] for o in SEED_OBSERVATIONS]
        assert len(set(tags)) == 3, "All three observations should have different damage tag sets"

    def test_statuses_differ(self):
        statuses = [o["case"]["status"] for o in SEED_OBSERVATIONS]
        assert len(set(statuses)) == 3, "All three cases should have different statuses"

    def test_all_notes_are_non_empty(self):
        for o in SEED_OBSERVATIONS:
            assert o.get("notes", "").strip(), f"Empty notes for {o['site_name']!r}"

    def test_all_ai_summaries_are_non_empty(self):
        for o in SEED_OBSERVATIONS:
            assert o.get("ai_summary", "").strip(), f"Empty ai_summary for {o['site_name']!r}"


# ---------------------------------------------------------------------------
# Risk band verification — bands must match what calculate_risk() actually returns
# ---------------------------------------------------------------------------

class TestSeedRiskBands:
    def _band_for(self, site_name: str) -> str:
        obs = next(o for o in SEED_OBSERVATIONS if o["site_name"] == site_name)
        tags = [t.strip() for t in obs["damage_tags"].split(",") if t.strip()]
        _, band = calculate_risk(tags, obs["severity"])
        return band

    def test_old_stone_church_is_high(self):
        assert self._band_for("Old Stone Church") == "High"

    def test_historic_iron_bridge_is_medium(self):
        assert self._band_for("Historic Iron Bridge") == "Medium"

    def test_memorial_statue_is_low(self):
        assert self._band_for("Memorial Statue") == "Low"

    def test_all_three_bands_represented(self):
        bands = set()
        for o in SEED_OBSERVATIONS:
            tags = [t.strip() for t in o["damage_tags"].split(",") if t.strip()]
            _, band = calculate_risk(tags, o["severity"])
            bands.add(band)
        assert bands == {"High", "Medium", "Low"}


# ---------------------------------------------------------------------------
# Workflow status coverage
# ---------------------------------------------------------------------------

class TestSeedStatuses:
    def test_needs_review_present(self):
        statuses = {o["case"]["status"] for o in SEED_OBSERVATIONS}
        assert "Needs Review" in statuses

    def test_verified_present(self):
        statuses = {o["case"]["status"] for o in SEED_OBSERVATIONS}
        assert "Verified" in statuses

    def test_routed_present(self):
        statuses = {o["case"]["status"] for o in SEED_OBSERVATIONS}
        assert "Routed" in statuses

    def test_all_statuses_are_valid_app_values(self):
        from app.models import RiskCase
        for o in SEED_OBSERVATIONS:
            status = o["case"]["status"]
            assert status in RiskCase.STATUSES, (
                f"Status {status!r} is not in RiskCase.STATUSES: {RiskCase.STATUSES}"
            )


# ---------------------------------------------------------------------------
# Safety — recommended actions must not encourage physical intervention
# ---------------------------------------------------------------------------

class TestSeedSafety:
    UNSAFE_PHRASES = [
        "please repair",
        "you should repair",
        "go repair",
        "please clean",
        "please touch",
        "please climb",
        "please enter",
        "start cleaning",
        "begin repair",
    ]

    def _check_field(self, text: str, label: str):
        lower = text.lower()
        for phrase in self.UNSAFE_PHRASES:
            assert phrase not in lower, (
                f"Unsafe phrase {phrase!r} found in {label}: {text!r}"
            )

    def test_recommended_actions_are_safe(self):
        for o in SEED_OBSERVATIONS:
            self._check_field(o["ai_recommended_action"], f"ai_recommended_action ({o['site_name']})")

    def test_ai_summaries_do_not_imply_final_decision(self):
        final_phrases = ["confirmed damage", "is safe", "is not safe", "must be repaired"]
        for o in SEED_OBSERVATIONS:
            lower = o["ai_summary"].lower()
            for phrase in final_phrases:
                assert phrase not in lower, (
                    f"Final-decision phrase {phrase!r} found in ai_summary for {o['site_name']!r}"
                )

    def test_all_summaries_acknowledge_mock_status(self):
        for o in SEED_OBSERVATIONS:
            lower = o["ai_summary"].lower()
            assert "mock" in lower or "fallback" in lower, (
                f"ai_summary for {o['site_name']!r} should note it is a mock/fallback result"
            )

    def test_all_summaries_contain_triage_principle(self):
        for o in SEED_OBSERVATIONS:
            summary = o["ai_summary"]
            assert "Humans verify" in summary, (
                f"ai_summary for {o['site_name']!r} should contain the triage principle"
            )
