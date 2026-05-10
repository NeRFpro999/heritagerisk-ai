"""
Generates a Markdown evidence report for a RiskCase and saves it to reports/.
Returns the file path relative to the repo root.
"""

from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def generate_report(case, observation, site) -> str:
    """
    Build the Markdown content and write it to reports/case_<id>.md.
    Returns the absolute path as a string.
    """
    tags = observation.tags_list or ["(none)"]
    image_line = (
        f"![Observation image](/uploads/{observation.image_filename})"
        if observation.image_filename
        else "_No image uploaded._"
    )

    md = f"""# Heritage Risk Evidence Report

**Case ID:** {case.id}
**Generated:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}

---

## Site

| Field | Value |
|-------|-------|
| Name | {site.name} |
| Location | {site.location or "—"} |
| Description | {site.description or "—"} |

---

## Observation

**Date:** {observation.created_at.strftime("%Y-%m-%d %H:%M UTC")}

{image_line}

**Notes:**
{observation.notes or "_No notes provided._"}

**Damage tags:** {", ".join(tags)}
**Severity:** {observation.severity} / 5

---

## Risk Assessment

| Field | Value |
|-------|-------|
| Score | {case.risk_score} / 100 |
| Band | {case.risk_band} |
| Status | {case.status} |
| Routed to | {case.routed_to or "—"} |

---

_Report generated automatically by HeritageRisk AI MVP._
_Risk scoring is rule-based and has not been validated by a conservation expert._
"""

    report_path = REPORTS_DIR / f"case_{case.id}.md"
    report_path.write_text(md, encoding="utf-8")
    return str(report_path)
