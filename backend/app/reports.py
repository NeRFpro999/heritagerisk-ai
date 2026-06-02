"""
Generates a Markdown evidence report for a RiskCase and saves it to reports/.
Returns the absolute file path as a string.
"""

from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


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
        return f"Mock analysis used because Azure AI is disabled or unavailable. {summary}"
    # status == "complete"
    return summary


def _confidence_line(observation) -> str:
    confidence = getattr(observation, "ai_confidence", None)
    status = _safe(getattr(observation, "ai_analysis_status", None), "not_run")
    if confidence is None or status in ("not_run", "failed"):
        return "Not available"
    return f"{confidence} / 100"


def generate_report(case, observation, site) -> str:
    """Write reports/case_<id>.md and return the absolute path."""
    tags_list = getattr(observation, "tags_list", None) or []
    tags = ", ".join(tags_list) if tags_list else "None recorded"

    image_filename = getattr(observation, "image_filename", None)
    image_path = f"/uploads/{image_filename}" if image_filename else "No image uploaded."

    obs_created = getattr(observation, "created_at", None)
    obs_datetime = (
        obs_created.strftime("%Y-%m-%d %H:%M UTC") if obs_created else "Not available"
    )

    routed_to = _safe(getattr(case, "routed_to", None), "Not routed yet")

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
* **Contributor notes:** {_safe(getattr(observation, 'notes', None), 'No notes provided.')}
* **Image path:** {image_path}

---

## 3. Visible Risk Indicators

* **Damage tags:** {tags}
* **Severity score:** {_safe(getattr(observation, 'severity', None))} / 5
* **AI/manual analysis summary:** {_ai_summary_line(observation)}
* **Confidence:** {_confidence_line(observation)}

---

## 4. Risk Case

* **Risk score:** {_safe(getattr(case, 'risk_score', None))} / 100
* **Risk band:** {_safe(getattr(case, 'risk_band', None))}
* **Status:** {_safe(getattr(case, 'status', None))}
* **Routed to:** {routed_to}

---

## 5. Recommended Next Step

Human review recommended before any action is taken.

---

## 6. Safety and Ethics Notice

HeritageRisk AI is for visible risk triage only. It does not replace professional conservation, engineering, emergency, legal, or cultural heritage advice.

---

## 7. Risk Scoring Method

Score = sum(tag weights) × severity, capped at 100.
Tags: crack 8 | erosion 7 | corrosion 7 | water_staining 6 | vegetation_growth 4 | graffiti 3 | other 2.
Bands: High > 60 | Medium 30–60 | Low < 30.
"""

    report_path = REPORTS_DIR / f"case_{case.id}.md"
    report_path.write_text(md, encoding="utf-8")
    return str(report_path)
