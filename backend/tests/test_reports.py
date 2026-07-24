"""Tests for immutable-snapshot Markdown evidence reports."""

import json
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app.provenance import build_case_snapshot
from app.reports import generate_report
from app.risk import build_risk_snapshot


# Fakes

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
    ai_provider="azure:gpt-5-mini",
    ai_recommended_action="Ask a conservation officer to review the evidence.",
    ai_raw_response=None,
    ai_uncertainty=None,
    human_review_status="ApprovedForAI",
    reviewed_by="submission.reviewer",
    reviewer_decision=None,
):
    tags = [
        tag.strip()
        for tag in damage_tags.split(",")
        if tag.strip()
    ] if damage_tags else []
    created_at = datetime(2025, 6, 1, 10, 30)
    obs = types.SimpleNamespace(
        id=id,
        notes=notes,
        damage_tags=damage_tags,
        severity=severity,
        image_filename=image_filename,
        created_at=created_at,
        ai_analysis_status=ai_analysis_status,
        ai_summary=ai_summary,
        ai_confidence=ai_confidence,
        ai_provider=ai_provider,
        ai_recommended_action=ai_recommended_action,
        ai_raw_response=ai_raw_response,
        ai_uncertainty=ai_uncertainty,
        human_review_status=human_review_status,
        reviewed_by=reviewed_by,
        reviewer_decision=reviewer_decision or {
            "decision": "Accepted",
            "reviewer_notes": "Checked against the submitted images.",
            "reviewed_at": "2025-06-01T11:00:00+00:00",
        },
        contributor_original={
            "notes": notes,
            "tags": list(tags),
            "severity": severity,
            "submitted_at": "2025-06-01T10:30:00+00:00",
        },
        images=(
            [types.SimpleNamespace(image_url=f"/uploads/{image_filename}")]
            if image_filename
            else []
        ),
    )
    obs.tags_list = tags
    return obs


def _snapshot_from_observation(
    obs,
    risk_score=None,
    risk_band=None,
    site=None,
    finalized_by="case.finalizer",
):
    site = site or _make_site()
    snapshot = build_risk_snapshot(obs.tags_list, obs.severity)
    if risk_score is not None:
        snapshot["capped_score"] = risk_score
    if risk_band is not None:
        snapshot["band"] = risk_band
    snapshot.update(
        {
            "version": 1,
            "snapshot_source": "case_creation",
            "captured_at": "2025-06-01T11:00:00+00:00",
            "reviewed_by": obs.reviewed_by,
            "finalized_by": finalized_by,
            "observation_id": obs.id,
            "observation_created_at": "2025-06-01T10:30:00+00:00",
            "image_urls": [image.image_url for image in obs.images],
            "site": {
                "id": site.id,
                "name": site.name,
                "location": site.location,
                "description": site.description,
            },
            "contributor_original": obs.contributor_original,
            "current_reviewed": {
                "notes": obs.notes,
                "tags": list(obs.tags_list),
                "severity": obs.severity,
                "human_review_status": obs.human_review_status,
            },
            "ai_proposal": {
                "analysis_status": obs.ai_analysis_status,
                "summary": obs.ai_summary,
                "damage_tags": list(obs.tags_list),
                "severity": obs.severity,
                "confidence": obs.ai_confidence,
                "provider": obs.ai_provider,
                "recommended_action": obs.ai_recommended_action,
                "uncertainty": obs.ai_uncertainty,
                "raw_response": obs.ai_raw_response,
            },
            "reviewer_decision": obs.reviewer_decision,
            "final_summary": obs.ai_summary,
            "final_recommended_action": obs.ai_recommended_action,
        }
    )
    return snapshot


def _make_case(
    id=99,
    risk_score=45,
    risk_band=None,
    status="Needs Review",
    routed_to="Conservation Officer",
    final_snapshot=None,
    finalized_by="mutable.case.finalizer",
    events=None,
):
    if risk_band is None:
        if risk_score < 30:
            risk_band = "Low"
        elif risk_score < 60:
            risk_band = "Medium"
        else:
            risk_band = "High"
    return types.SimpleNamespace(
        id=id,
        risk_score=risk_score,
        risk_band=risk_band,
        status=status,
        routed_to=routed_to,
        final_snapshot=final_snapshot,
        finalized_by=finalized_by,
        observation_id=10,
        created_at=datetime(2025, 6, 1, 11, 0),
        events=events or [],
    )


# Helpers

def _generate(tmp_path, site=None, obs=None, case=None):
    site = site or _make_site()
    obs = obs or _make_observation()
    case = case or _make_case()
    if case.final_snapshot is None:
        case.final_snapshot = _snapshot_from_observation(
            obs,
            risk_score=case.risk_score,
            risk_band=case.risk_band,
            site=site,
        )
    with patch("app.reports.REPORTS_DIR", tmp_path):
        path = generate_report(case)
    return Path(path).read_text(encoding="utf-8")


# Required section headings

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

    def test_three_layer_provenance_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Three-Layer Provenance" in md

    def test_risk_case_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Risk Case" in md

    def test_safety_ethics_notice_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Safety and Ethics Notice" in md

    def test_safety_ethics_note_is_clear(self, tmp_path):
        md = _generate(tmp_path)
        assert (
            "HeritageRisk AI is for visible risk triage only. It does not replace "
            "professional conservation, engineering, emergency, legal, or cultural heritage "
            "advice. Human review is required before action."
        ) in md

    def test_risk_scoring_method_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Risk Scoring Method" in md
        assert "Band thresholds:** Low 0-29 | Medium 30-59 | High 60-100" in md

    def test_human_review_recommended(self, tmp_path):
        md = _generate(tmp_path)
        assert "Human review is required before any action" in md

    def test_human_review_audit_trail_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "Human Review Audit Trail" in md
        assert "**Reviewed by:** submission.reviewer" in md
        assert "**Finalized by:** case.finalizer" in md
        assert "Human Review Status at Case Finalization: ApprovedForAI" in md
        assert "Reviewed before AI Analysis" not in md

    def test_ai_audit_trail_section(self, tmp_path):
        md = _generate(tmp_path)
        assert "AI Audit Trail" in md
        assert "AI summary generated by: Azure OpenAI Vision (or Mock Fallback)" in md
        assert "Actual analysis provider: Azure OpenAI Vision" in md


# Real data mapped correctly

class TestRealDataMapping:
    def test_case_snapshot_captures_normalized_reviewer_identities(self):
        observation = _make_observation(reviewed_by="  submission.reviewer  ")
        observation.site = _make_site()

        snapshot = build_case_snapshot(
            observation=observation,
            final_tags=observation.tags_list,
            final_severity=observation.severity,
            final_summary=observation.ai_summary,
            final_recommended_action=observation.ai_recommended_action,
            reviewer_decision=observation.reviewer_decision,
            finalized_by="  case.finalizer  ",
        )

        assert snapshot["reviewed_by"] == "submission.reviewer"
        assert snapshot["finalized_by"] == "case.finalizer"

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

    def test_status_event_history_appears(self, tmp_path):
        event = types.SimpleNamespace(
            from_status="Draft",
            to_status="Needs Review",
            reviewer="status.reviewer",
            note="Ready for review.",
            created_at=datetime(2025, 6, 1, 12, 30),
        )
        md = _generate(tmp_path, case=_make_case(events=[event]))
        assert "Status Event History" in md
        assert "Draft -> Needs Review by status.reviewer" in md
        assert "Ready for review." in md

    def test_routed_to_appears(self, tmp_path):
        md = _generate(tmp_path, case=_make_case(routed_to="Conservation Officer"))
        assert "Conservation Officer" in md
        assert "Final routing destination: Conservation Officer" in md

    def test_reviewed_notes_appear_but_original_notes_are_withheld(self, tmp_path):
        md = _generate(tmp_path, obs=_make_observation(notes="South wall cracking."))
        assert "South wall cracking." in md
        assert "Preserved for reviewer audit; withheld from case reports." in md

    def test_recommended_next_step_and_limitations_appear(self, tmp_path):
        md = _generate(tmp_path)
        assert "Ask a conservation officer to review the evidence." in md
        assert "## 10. Limitations" in md
        assert "does not send or submit the report" in md

    def test_uncertainty_and_ai_finalization_audit_appear(self, tmp_path):
        obs = _make_observation(
            ai_raw_response=json.dumps(
                {"uncertainty": "The rear elevation is not visible."}
            ),
            ai_uncertainty="The rear elevation is not visible.",
            reviewer_decision={
                "decision": "Edited and accepted",
                "reviewer_notes": "Removed unsupported wording.",
                "reviewed_at": "2025-06-01T11:00:00+00:00",
            },
        )
        md = _generate(tmp_path, obs=obs)
        assert "AI uncertainty:** The rear elevation is not visible." in md
        assert "AI Output Finalization: Edited and accepted" in md
        assert "Reviewer Finalization Notes: Removed unsupported wording." in md

    def test_observation_image_url_appears(self, tmp_path):
        obs = _make_observation(image_filename=None)
        obs.images = [types.SimpleNamespace(image_url="/uploads/new-image.png")]
        md = _generate(tmp_path, obs=obs)
        assert "/uploads/new-image.png" in md
        assert "![Observation image 1](/uploads/new-image.png)" in md

    def test_multiple_observation_images_are_embedded(self, tmp_path):
        obs = _make_observation(image_filename=None)
        obs.images = [
            types.SimpleNamespace(image_url="/uploads/one.png"),
            types.SimpleNamespace(image_url="/uploads/two.png"),
        ]
        md = _generate(tmp_path, obs=obs)
        assert "![Observation image 1](/uploads/one.png)" in md
        assert "![Observation image 2](/uploads/two.png)" in md

    def test_mock_fallback_provider_appears(self, tmp_path):
        obs = _make_observation(
            ai_analysis_status="mock",
            ai_provider="mock",
            ai_summary="Mock fallback summary.",
        )
        md = _generate(tmp_path, obs=obs)
        assert "Actual analysis provider: Mock Fallback" in md

    def test_markdown_contains_all_stored_risk_snapshot_fields(self, tmp_path):
        obs = _make_observation(damage_tags="crack,erosion", severity=3)
        case = _make_case(risk_score=45, risk_band="Medium")
        md = _generate(tmp_path, obs=obs, case=case)
        assert "Finalized Tag Weights" in md
        assert "**Final tags:** crack, erosion" in md
        assert "**Final severity:** 3 / 5" in md
        assert "**crack** (Crack): 8" in md
        assert "**erosion** (Erosion): 7" in md
        assert "Severity multiplier:** 3" in md
        assert "Raw equation:** (8 + 7) × Severity 3 = 45" in md
        assert "Capped score:** 45 / 100" in md
        assert "Final score:** 45 / 100" in md
        assert "Risk band:** Medium" in md

    def test_report_ignores_values_outside_the_stored_snapshot(self, tmp_path):
        snapshotted = _make_observation(
            notes="Reviewed south wall evidence.",
            damage_tags="crack",
            severity=2,
            ai_summary="Snapshotted AI proposal.",
        )
        case = _make_case(
            risk_score=16,
            risk_band="Low",
            final_snapshot=_snapshot_from_observation(snapshotted),
        )
        later_live_observation = _make_observation(
            id=999,
            notes="Later mutable notes that must not render.",
            damage_tags="fire_damage",
            severity=5,
            ai_summary="Later mutable AI text that must not render.",
        )

        md = _generate(
            tmp_path,
            obs=later_live_observation,
            case=case,
        )

        assert "Reviewed south wall evidence." in md
        assert "Snapshotted AI proposal." in md
        assert "Later mutable notes that must not render." not in md
        assert "Later mutable AI text that must not render." not in md

    def test_report_uses_only_snapshotted_reviewer_identities(self, tmp_path):
        observation = _make_observation(reviewed_by="snapshot.reviewer")
        snapshot = _snapshot_from_observation(
            observation,
            finalized_by="snapshot.finalizer",
        )
        case = _make_case(
            final_snapshot=snapshot,
            finalized_by="later.case.finalizer",
        )
        observation.reviewed_by = "later.observation.reviewer"

        md = _generate(tmp_path, obs=observation, case=case)

        assert "**Reviewed by:** snapshot.reviewer" in md
        assert "**Finalized by:** snapshot.finalizer" in md
        assert "later.observation.reviewer" not in md
        assert "later.case.finalizer" not in md

    def test_final_safety_clause_is_bottom_blockquote(self, tmp_path):
        md = _generate(tmp_path)
        final_line = (
            "> HeritageRisk AI is for visible risk triage only and does not replace "
            "professional structural, conservation, or emergency advice. Do not rely on "
            "this report for safety decisions."
        )
        assert final_line in md
        assert md.strip().endswith(final_line)


# Safe fallbacks — missing fields must not crash

class TestSafeFallbacks:
    def test_missing_location_does_not_crash(self, tmp_path):
        md = _generate(tmp_path, site=_make_site(location=None))
        assert "Not provided" in md

    def test_missing_description_does_not_crash(self, tmp_path):
        md = _generate(tmp_path, site=_make_site(description=None))
        assert "Not provided" in md

    def test_missing_notes_does_not_crash(self, tmp_path):
        md = _generate(tmp_path, obs=_make_observation(notes=None))
        assert "No reviewed notes recorded." in md

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

    def test_legacy_null_snapshot_does_not_read_live_observation(self, tmp_path):
        case = _make_case(final_snapshot=None)
        with patch("app.reports.REPORTS_DIR", tmp_path):
            path = generate_report(case)

        md = Path(path).read_text(encoding="utf-8")
        assert "predates immutable snapshots" in md
        assert "No live Observation values were substituted" in md
        assert "**Case snapshot captured:** Not available" in md
        assert "**Risk score:** 45 / 100" in md
        assert "Detailed tag weights are not available" in md
        assert "**Band thresholds:** Not available" in md
        assert "**Reviewed by:** Not available" in md
        assert "**Finalized by:** Not available" in md

    def test_malformed_nested_snapshot_values_do_not_crash(self, tmp_path):
        case = _make_case(
            final_snapshot={
                "snapshot_source": "case_creation",
                "site": "invalid",
                "contributor_original": "invalid",
                "current_reviewed": "invalid",
                "ai_proposal": {"damage_tags": [7]},
                "reviewer_decision": [],
                "reviewed_by": 7,
                "finalized_by": ["invalid"],
                "final_tags": [7],
                "tag_weights": [{}, "invalid"],
                "capped_score": 45,
                "band": "Medium",
            }
        )
        with patch("app.reports.REPORTS_DIR", tmp_path):
            path = generate_report(case)

        md = Path(path).read_text(encoding="utf-8")
        assert "HeritageRisk AI Evidence Report" in md
        assert "**Site name:** Not available" in md
        assert "**Capped score:** 45 / 100" in md
        assert "**Reviewed by:** Not available" in md
        assert "**Finalized by:** Not available" in md

    def test_new_case_with_missing_legacy_original_shows_unavailable(
        self,
        tmp_path,
    ):
        observation = _make_observation(notes="Reviewed working note.")
        snapshot = _snapshot_from_observation(observation)
        snapshot["contributor_original"] = None
        case = _make_case(final_snapshot=snapshot)

        with patch("app.reports.REPORTS_DIR", tmp_path):
            path = generate_report(case)

        md = Path(path).read_text(encoding="utf-8")
        assert "**Notes:** Not available" in md
        assert "**Tags:** Not available" in md
        assert "**Submitted at:** Not available" in md
        assert "Preserved for reviewer audit" not in md


# AI analysis status handling

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
        assert "Mock analysis" in md

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
        for final_phrase in (
            "this site is safe",
            "this site is unsafe",
            "must be repaired",
            "structural failure confirmed",
            "professional inspection not needed",
        ):
            assert final_phrase not in lower

    def test_report_contains_triage_principle(self, tmp_path):
        obs = _make_observation(ai_analysis_status="complete", ai_summary="Crack detected.")
        md = _generate(tmp_path, obs=obs)
        assert "visible risk triage" in md


# File written correctly

class TestFileOutput:
    def test_file_created_with_correct_name(self, tmp_path):
        case = _make_case(id=7)
        _generate(tmp_path, case=case)
        assert (tmp_path / "case_7.md").exists()

    def test_return_value_is_absolute_path(self, tmp_path):
        case = _make_case(id=7)
        obs = _make_observation()
        case.final_snapshot = _snapshot_from_observation(obs)
        with patch("app.reports.REPORTS_DIR", tmp_path):
            result = generate_report(case)
        assert Path(result).is_absolute()
