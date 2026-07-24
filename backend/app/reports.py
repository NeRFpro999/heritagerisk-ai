"""Generate immutable-snapshot Markdown evidence reports for RiskCases."""

from datetime import datetime
import os
from pathlib import Path

from app.provenance import case_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = Path(os.environ.get("HERITAGERISK_REPORTS_DIR", REPO_ROOT / "reports"))
if not REPORTS_DIR.is_absolute():
    REPORTS_DIR = REPO_ROOT / REPORTS_DIR
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SAFETY_ETHICS_NOTE = (
    "HeritageRisk AI is for visible risk triage only. It does not replace "
    "professional conservation, engineering, emergency, legal, or cultural heritage "
    "advice. Human review is required before action."
)
FINAL_SAFETY_CLAUSE = (
    "HeritageRisk AI is for visible risk triage only and does not replace "
    "professional structural, conservation, or emergency advice. Do not rely on "
    "this report for safety decisions."
)


def _safe(value, fallback: str = "Not provided") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _format_timestamp(value) -> str:
    if not value:
        return "Not available"
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return _safe(value, "Not available")
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def _images_markdown(
    image_urls: list[str],
    fallback: str = "No image uploaded.",
) -> str:
    if not image_urls:
        return fallback
    return "\n".join(
        f"![Observation image {index}]({image_url})"
        for index, image_url in enumerate(image_urls, start=1)
    )


def _ai_summary_line(ai_proposal: dict) -> str:
    status = _safe(ai_proposal.get("analysis_status"), "not_run")
    summary = ai_proposal.get("summary")
    if status == "failed":
        return "AI analysis was attempted but failed. Human review required."
    if status == "not_run" or not summary:
        return "No AI analysis has been run for this observation."
    if status == "mock":
        return (
            "Mock analysis used because Azure AI is disabled or unavailable. "
            f"{summary}"
        )
    return str(summary)


def _confidence_line(ai_proposal: dict) -> str:
    confidence = ai_proposal.get("confidence")
    status = ai_proposal.get("analysis_status")
    if confidence is None or status in ("not_run", "failed"):
        return "Not available"
    return f"{confidence} / 100"


def _ai_provider_label(ai_proposal: dict) -> str:
    status = _safe(ai_proposal.get("analysis_status"), "not_run")
    provider = _safe(ai_proposal.get("provider"), "")
    if status == "mock" or provider == "mock":
        return "Mock Fallback"
    if status == "complete":
        return "Azure OpenAI Vision"
    return provider or "Not available"


def _case_events(case) -> list:
    events = list(getattr(case, "events", None) or [])
    return sorted(
        events,
        key=lambda event: getattr(event, "created_at", None) or datetime.min,
    )


def _case_event_lines(case) -> str:
    lines = []
    for event in _case_events(case):
        timestamp = _format_timestamp(getattr(event, "created_at", None))
        note = _safe(getattr(event, "note", None), "No note")
        lines.append(
            "* "
            f"{timestamp}: {_safe(getattr(event, 'from_status', None))} -> "
            f"{_safe(getattr(event, 'to_status', None))} by "
            f"{_safe(getattr(event, 'reviewer', None), 'Not available')}. "
            f"Note: {note}."
        )
    if not lines:
        return "* No status transitions have been recorded for this case."
    return "\n".join(lines)


def _indicator_lines(ai_proposal: dict) -> str:
    indicators = ai_proposal.get("indicators")
    if not isinstance(indicators, list) or not indicators:
        return "* No proposed indicators recorded."
    lines = []
    for indicator in indicators:
        if not isinstance(indicator, dict):
            continue
        image_refs = indicator.get("image_refs") or []
        if isinstance(image_refs, list):
            refs = ", ".join(str(ref) for ref in image_refs) or "Not available"
        else:
            refs = "Not available"
        confidence = indicator.get("confidence")
        confidence_text = (
            f"{round(confidence * 100)}%"
            if isinstance(confidence, (int, float))
            else "Not available"
        )
        lines.append(
            "* "
            f"**{_safe(indicator.get('indicator_type'))}** at "
            f"{_safe(indicator.get('evidence_location'))}; "
            f"images {refs}; confidence {confidence_text}; "
            f"severity contribution {_safe(indicator.get('severity_contribution'))}/5. "
            f"Evidence: {_safe(indicator.get('supporting_evidence'))}."
        )
    return "\n".join(lines) if lines else "* No proposed indicators recorded."


def generate_report(case) -> str:
    """Write reports/case_<id>.md using only the stored case snapshot."""
    snapshot = case_snapshot(case)
    original = snapshot.get("contributor_original") or {}
    original_available = bool(snapshot.get("contributor_original"))
    reviewed = snapshot.get("current_reviewed") or {}
    ai_proposal = snapshot.get("ai_proposal") or {}
    review = snapshot.get("reviewer_decision") or {}
    site = snapshot.get("site") or {}
    legacy_snapshot = snapshot.get("snapshot_source") == "legacy_unavailable"

    final_tags = snapshot.get("final_tags") or []
    tags = ", ".join(final_tags) if final_tags else (
        "Not available" if legacy_snapshot else "None recorded"
    )
    original_tags = ", ".join(original.get("tags") or []) or (
        "None recorded" if original_available else "Not available"
    )
    ai_tags = ", ".join(ai_proposal.get("damage_tags") or []) or (
        "Not available" if legacy_snapshot else "None suggested"
    )
    ai_schema_version = _safe(ai_proposal.get("schema_version"), "v1")
    evidence_sufficiency = _safe(
        ai_proposal.get("evidence_sufficiency"),
        "Not recorded for v1 rows",
    )
    insufficient_reason = _safe(
        ai_proposal.get("insufficient_reason"),
        "Not provided",
    )
    indicator_lines = _indicator_lines(ai_proposal)
    tag_weight_lines = "\n".join(
        f"* **{item['tag']}** ({item['label']}): {item['weight']}"
        for item in snapshot.get("tag_weights") or []
    ) or (
        "* Detailed tag weights are not available for this legacy case."
        if legacy_snapshot
        else "* No finalized tags recorded: 0"
    )
    image_markdown = _images_markdown(
        snapshot.get("image_urls") or [],
        fallback=(
            "Image references are not available for this legacy case."
            if legacy_snapshot
            else "No image uploaded."
        ),
    )
    ai_uncertainty = _safe(
        ai_proposal.get("uncertainty"),
        (
            "Not available"
            if legacy_snapshot
            else "Not separately provided; use the confidence score and original images."
        ),
    )
    captured_at = _format_timestamp(snapshot.get("captured_at"))
    observation_created_at = _format_timestamp(
        snapshot.get("observation_created_at")
    )
    submitted_at = _format_timestamp(original.get("submitted_at"))
    contributor_notes = (
        "Preserved for reviewer audit; withheld from case reports."
        if original_available
        else "Not available"
    )
    reviewed_notes = _safe(
        reviewed.get("notes"),
        "Not available" if legacy_snapshot else "No reviewed notes recorded.",
    )
    review_status = _safe(
        reviewed.get("human_review_status"),
        "Not available" if legacy_snapshot else "Not recorded",
    )
    reviewed_by = _safe(snapshot.get("reviewed_by"), "Not available")
    finalized_by = _safe(snapshot.get("finalized_by"), "Not available")
    decision = _safe(
        review.get("decision"),
        "Not available" if legacy_snapshot else "Accepted for Risk Case",
    )
    reviewer_notes = _safe(
        review.get("reviewer_notes"),
        "Not available" if legacy_snapshot else "No finalization notes.",
    )
    final_summary = _safe(
        snapshot.get("final_summary"),
        (
            "Not available"
            if legacy_snapshot
            else "No final reviewed summary was recorded."
        ),
    )
    final_action = _safe(
        snapshot.get("final_recommended_action"),
        (
            "Not available"
            if legacy_snapshot
            else "No final next step was recorded; human review is required."
        ),
    )
    raw_equation = _safe(snapshot.get("raw_equation"), "Not available")
    capped_suffix = " (capped)" if snapshot.get("capped") else ""
    thresholds = snapshot.get("thresholds") or {}
    threshold_line = (
        f"Low {thresholds['Low']} | Medium {thresholds['Medium']} | "
        f"High {thresholds['High']}"
        if thresholds
        else "Not available"
    )
    legacy_notice = ""
    if legacy_snapshot:
        legacy_notice = (
            "\n> Detailed provenance is unavailable because this case predates "
            "immutable snapshots. No live Observation values were substituted.\n"
        )
    event_lines = _case_event_lines(case)

    md = f"""# HeritageRisk AI Evidence Report

**Case ID:** {_safe(getattr(case, 'id', None))}
**Case snapshot captured:** {captured_at}
{legacy_notice}
---

## 1. Site Information

* **Site name:** {_safe(site.get('name'), 'Not available')}
* **Location:** {_safe(site.get('location'), 'Not provided')}
* **Description:** {_safe(site.get('description'), 'Not provided')}

---

## 2. Observation

* **Observation ID:** {_safe(snapshot.get('observation_id'))}
* **Observation created:** {observation_created_at}
* **Contributor-original notes:** {contributor_notes}
* **Reviewed working notes at finalization:** {reviewed_notes}

### Submitted Images at Finalization

{image_markdown}

---

## 3. Three-Layer Provenance

### Contributor Original

* **Notes:** {contributor_notes}
* **Tags:** {original_tags}
* **Severity:** {_safe(original.get('severity'), 'Not available')} / 5
* **Submitted at:** {_format_timestamp(original.get('submitted_at'))}

### AI Proposal

* **Schema version:** {ai_schema_version}
* **Evidence sufficiency:** {evidence_sufficiency}
* **Insufficient evidence reason:** {insufficient_reason}
* **Suggested tags:** {ai_tags}
* **Suggested severity:** {_safe(ai_proposal.get('severity'), 'Not available')} / 5
* **Summary:** {'Not available' if legacy_snapshot else _ai_summary_line(ai_proposal)}
* **Confidence:** {'Not available' if legacy_snapshot else _confidence_line(ai_proposal)}
* **AI uncertainty:** {ai_uncertainty}
* **Recommended next step:** {_safe(ai_proposal.get('recommended_action'), 'Not available')}

#### Proposed Indicators

{indicator_lines}

### Reviewer-Accepted Final

* **Final tags:** {tags}
* **Final severity:** {_safe(snapshot.get('final_severity'), 'Not available')} / 5
* **Final reviewed summary:** {final_summary}
* **Final reviewed next step:** {final_action}

---

## 4. Human Review Audit Trail

* **Reviewed by:** {reviewed_by}
* **Finalized by:** {finalized_by}
* Human Review Status at Case Finalization: {review_status}
* AI Output Finalization: {decision}
* Reviewer Finalization Notes: {reviewer_notes}

---

## 5. AI Audit Trail

* AI summary generated by: Azure OpenAI Vision (or Mock Fallback)
* Actual analysis provider: {_ai_provider_label(ai_proposal)}
* AI analysis status: {_safe(ai_proposal.get('analysis_status'), 'Not available' if legacy_snapshot else 'not_run')}

---

## 6. Risk Case

* **Risk score:** {_safe(snapshot.get('capped_score'), 'Not available')} / 100
* **Risk band:** {_safe(snapshot.get('band'), 'Not available')}
* **Status:** {_safe(getattr(case, 'status', None))}
* Final routing destination: {_safe(getattr(case, 'routed_to', None), 'Not routed yet')}

### Status Event History

{event_lines}

---

## 7. Recommended Next Step

{final_action}

Human review is required before any action, forwarding, or routing decision.

---

## 8. Safety and Ethics Notice

{SAFETY_ETHICS_NOTE}

---

## 9. Risk Scoring Method

The risk score is rule-based, not decided by AI. These values were stored when
the Risk Case was created and are not recalculated from the Observation.

### Finalized Tag Weights

{tag_weight_lines}

* **Severity multiplier:** {_safe(snapshot.get('multiplier'), 'Not available')}
* **Raw equation:** {raw_equation}
* **Equation:** {raw_equation}
* **Capped score:** {_safe(snapshot.get('capped_score'), 'Not available')} / 100{capped_suffix}
* **Final score:** {_safe(snapshot.get('capped_score'), 'Not available')} / 100
* **Risk band:** {_safe(snapshot.get('band'), 'Not available')}
* **Band thresholds:** {threshold_line}

---

## 10. Limitations

* The analysis covers visible evidence in the submitted images and notes only.
* Hidden, internal, structural, legal, emergency, ownership, and
  cultural-authority issues are outside this report's scope.
* Confidence is not proof of condition, safety, cause, urgency, or diagnosis.
* The app does not send or submit the report; routing is recorded only.

> {FINAL_SAFETY_CLAUSE}
"""

    report_path = REPORTS_DIR / f"case_{case.id}.md"
    report_path.write_text(md, encoding="utf-8")
    return str(report_path)
