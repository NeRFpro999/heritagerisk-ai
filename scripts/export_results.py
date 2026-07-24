#!/usr/bin/env python3
"""Export paired experiment sessions and indicator rows to CSV."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

FIELDNAMES = [
    "row_type",
    "external_asset_id",
    "site_label",
    "asset_db_id",
    "session_id",
    "condition",
    "run_index",
    "indicator_type",
    "evidence_sufficiency",
    "confidence",
    "evidence_location",
    "image_refs",
    "supporting_evidence",
    "severity_contribution",
    "insufficient_reason",
    "prompt_template_sha256",
    "rendered_request_sha256",
    "schema_version",
    "model_deployment",
    "run_order",
    "operator",
    "run_at",
    "session_image_ids",
    "settings",
    "analysis_status",
    "provider",
]


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True) if value is not None else ""


def _base_row(asset, session, result: dict[str, Any]) -> dict[str, Any]:
    structured = result.get("structured_response") or {}
    return {
        "external_asset_id": asset.external_asset_id,
        "site_label": asset.site_label or "",
        "asset_db_id": asset.id,
        "session_id": session.id,
        "condition": getattr(session.condition, "value", session.condition),
        "run_index": session.run_index,
        "evidence_sufficiency": structured.get("evidence_sufficiency", ""),
        "insufficient_reason": structured.get("insufficient_reason") or "",
        "prompt_template_sha256": session.prompt_template_sha256,
        "rendered_request_sha256": session.rendered_request_sha256 or "",
        "schema_version": session.schema_version,
        "model_deployment": session.model_deployment,
        "run_order": session.run_order,
        "operator": session.operator or "",
        "run_at": session.run_at.isoformat() if session.run_at else "",
        "session_image_ids": _json(session.image_ids),
        "settings": _json(session.settings),
        "analysis_status": result.get("status", ""),
        "provider": result.get("provider", ""),
    }


def export_results(*, db_path: Path, output_path: Path) -> dict[str, int]:
    os.environ["HERITAGERISK_DB_PATH"] = str(db_path)

    from app.database import SessionLocal, apply_sqlite_startup_migrations, engine
    from app.models import AssessmentSession

    apply_sqlite_startup_migrations(engine)
    db = SessionLocal()
    rows: list[dict[str, Any]] = []
    try:
        sessions = (
            db.query(AssessmentSession)
            .order_by(
                AssessmentSession.asset_id,
                AssessmentSession.run_index,
                AssessmentSession.run_order,
            )
            .all()
        )
        for session in sessions:
            asset = session.asset
            result = session.analysis_result or {}
            structured = result.get("structured_response") or {}
            base = _base_row(asset, session, result)
            rows.append(
                {
                    **{field: "" for field in FIELDNAMES},
                    **base,
                    "row_type": "session",
                }
            )
            for indicator in structured.get("indicators") or []:
                rows.append(
                    {
                        **{field: "" for field in FIELDNAMES},
                        **base,
                        "row_type": "indicator",
                        "indicator_type": indicator.get("indicator_type", ""),
                        "confidence": indicator.get("confidence", ""),
                        "evidence_location": indicator.get("evidence_location", ""),
                        "image_refs": _json(indicator.get("image_refs")),
                        "supporting_evidence": indicator.get("supporting_evidence", ""),
                        "severity_contribution": indicator.get(
                            "severity_contribution",
                            "",
                        ),
                    }
                )
    finally:
        db.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "sessions": sum(1 for row in rows if row["row_type"] == "session"),
        "indicator_rows": sum(1 for row in rows if row["row_type"] == "indicator"),
        "rows": len(rows),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=REPO_ROOT / "data" / "heritagerisk.db")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = export_results(db_path=args.db_path, output_path=args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
