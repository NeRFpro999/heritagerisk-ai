"""
Generates a Markdown evidence report for a RiskCase and saves it to reports/.
Returns the absolute file path as a string.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.risk import calculate_risk_breakdown

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

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
    s = str(value).strip()
    return s if s else fallback


def _ai_summary_line(observation) -> str:
    """Build the AI/manual analysis line for the report."""
    status = _safe(getattr(observation, "ai_analysis_status", None), "not_run")
    summary = getattr(observation, "ai_summary", None)

    if status == "not_run":
        return "No AI analysis has been run for this observation."
    if status == "failed":
        return "AI analysis was attempted but failed. Human review required."
    if not summary:
        return "No AI analysis has been run for this observation."
    if status == "mock":
        return (
            "Mock analysis used because Azure AI is disabled or unavailable. "
            f"{summary}"
        )
    # status == "complete"
    return summary


def _confidence_line(observation) -> str:
    confidence = getattr(observation, "ai_confidence", None)
    status = _safe(getattr(observation, "ai_analysis_status", None), "not_run")
    if confidence is None or status in ("not_run", "failed"):
        return "Not available"
    return f"{confidence} / 100"


def _normalise_image_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    if raw_url.startswith(("/", "http://", "https://")):
        return raw_url
    return f"/uploads/{raw_url}"


def _image_urls(observation) -> list[str]:
    images = getattr(observation, "images", None) or []
    urls: list[str] = []
    if images:
        for image in images:
            image_url = _normalise_image_url(getattr(image, "image_url", None))
            if image_url:
                urls.append(image_url)
        if urls:
            return urls

    primary_url = _normalise_image_url(getattr(observation, "primary_image_url", None))
    if primary_url:
        return [primary_url]

    legacy_filename = getattr(observation, "image_filename", None)
    if legacy_filename:
        return [f"/uploads/{legacy_filename}"]

    return []


def _images_markdown(observation) -> str:
    urls = _image_urls(observation)
    if not urls:
        return "No image uploaded."

    return "\n".join(
        f"![Observation image {index}]({image_url})"
        for index, image_url in enumerate(urls, start=1)
    )


def _human_review_status_value(observation) -> str:
    status = getattr(observation, "human_review_status", None)
    if status is None:
        return "Not recorded"
    return _safe(getattr(status, "value", status))


def _ai_provider_label(observation) -> str:
    status = _safe(getattr(observation, "ai_analysis_status", None), "not_run")
    provider = _safe(getattr(observation, "ai_provider", None), "")
    if status == "mock" or provider == "mock":
        return "Mock Fallback"
    if status == "complete":
        return "Azure OpenAI Vision"
    if provider:
        return provider
    return "Not available"


def _ai_raw_data(observation) -> dict:
    raw_response = getattr(observation, "ai_raw_response", None)
    if not raw_response:
        return {}
    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _ai_uncertainty_line(observation) -> str:
    uncertainty = _ai_raw_data(observation).get("uncertainty")
    if isinstance(uncertainty, str) and uncertainty.strip():
        return uncertainty.strip()
    return "Not separately provided; use the confidence score and original images."


def _ai_review_data(observation) -> dict:
    review = _ai_raw_data(observation).get("human_ai_review", {})
    return review if isinstance(review, dict) else {}


def _risk_equation_line(breakdown: dict) -> str:
    weights = [str(item["weight"]) for item in breakdown["tag_weights"]]
    left_side = " + ".join(weights) if weights else "0"
    equation = (
        f"({left_side}) × Severity {breakdown['severity']} = "
        f"{breakdown['raw_score']}"
    )
    if breakdown["capped"]:
        equation += " → 100 (capped)"
    return equation


def generate_report(case, observation, site) -> str:
    """Write reports/case_<id>.md and return the absolute path."""
    tags_list = getattr(observation, "tags_list", None) or []
    tags = ", ".join(tags_list) if tags_list else "None recorded"
    image_markdown = _images_markdown(observation)
    human_review_status = _human_review_status_value(observation)
    reviewed_before_ai = human_review_status == "ApprovedForAI"
    risk_breakdown = calculate_risk_breakdown(
        tags_list,
        int(getattr(observation, "severity", 1) or 1),
    )
    tag_weight_lines = "\n".join(
        f"* **{item['tag']}** ({item['label']}): {item['weight']}"
        for item in risk_breakdown["tag_weights"]
    )
    if not tag_weight_lines:
        tag_weight_lines = "* No finalized tags recorded: 0"

    obs_created = getattr(observation, "created_at", None)
    obs_datetime = (
        obs_created.strftime("%Y-%m-%d %H:%M UTC") if obs_created else "Not available"
    )

    routed_to = _safe(getattr(case, "routed_to", None), "Not routed yet")
    recommended_action = _safe(
        getattr(observation, "ai_recommended_action", None),
        "No AI next step was recorded; human review is required.",
    )
    ai_review = _ai_review_data(observation)
    ai_review_decision = _safe(ai_review.get("decision"), "Accepted for Risk Case")
    ai_review_notes = _safe(ai_review.get("reviewer_notes"), "No finalization notes.")
    contributor_notes = _safe(
        getattr(observation, "notes", None),
        "No notes provided.",
    )
    ai_analysis_status = _safe(
        getattr(observation, "ai_analysis_status", None),
        "not_run",
    )

    md = f"""# HeritageRisk AI Evidence Report

**Case ID:** {_safe(getattr(case, 'id', None))}
**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

---

## 1. Site Information

* **Site name:** {_safe(getattr(site, 'name', None))}
* **Location:** {_safe(getattr(site, 'location', None))}
* **Description:** {_safe(getattr(site, 'description', None))}

---

## 2. Observation

* **Observation ID:** {_safe(getattr(observation, 'id', None))}
* **Date/time:** {obs_datetime}
* **Contributor notes:** {contributor_notes}

### Submitted Images

{image_markdown}

---

## 3. Visible Risk Indicators

* **Damage tags:** {tags}
* **Severity score:** {_safe(getattr(observation, 'severity', None))} / 5
* **AI/manual analysis summary:** {_ai_summary_line(observation)}
* **Confidence:** {_confidence_line(observation)}
* **AI uncertainty:** {_ai_uncertainty_line(observation)}

---

## 4. Human Review Audit Trail

* Human Review Status: {human_review_status}
* Reviewed before AI Analysis: {reviewed_before_ai}
* AI Output Finalization: {ai_review_decision}
* Reviewer Finalization Notes: {ai_review_notes}

---

## 5. AI Audit Trail

* AI summary generated by: Azure OpenAI Vision (or Mock Fallback)
* Actual analysis provider: {_ai_provider_label(observation)}
* AI analysis status: {ai_analysis_status}

---

## 6. Risk Case

* **Risk score:** {_safe(getattr(case, 'risk_score', None))} / 100
* **Risk band:** {_safe(getattr(case, 'risk_band', None))}
* **Status:** {_safe(getattr(case, 'status', None))}
* Final routing destination: {routed_to}

---

## 7. Recommended Next Step

{recommended_action}

Human review is required before any action, forwarding, or routing decision.

---

## 8. Safety and Ethics Notice

{SAFETY_ETHICS_NOTE}

---

## 9. Risk Scoring Method

The risk score is rule-based, not decided by AI.

### Finalized Tag Weights

{tag_weight_lines}

* **Severity multiplier:** {risk_breakdown['severity']}
* **Equation:** {_risk_equation_line(risk_breakdown)}
* **Final score:** {risk_breakdown['score']} / 100
* **Risk band:** {risk_breakdown['band']}
* **Band thresholds:** Low 0-29 | Medium 30-59 | High 60-100

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
