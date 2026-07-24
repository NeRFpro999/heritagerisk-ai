#!/usr/bin/env python3
"""Run paired single-medium and three-view assessment sessions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REQUIRED_AZURE_ENV = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_PRIMARY_DEPLOYMENT",
)
CONDITIONS = ("single_medium", "three_view")
ROLE_INDEX = {"wide": 1, "medium": 2, "close": 3}


class ExperimentError(RuntimeError):
    pass


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ExperimentError(f"Manifest not found: {path}")
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    elif path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["assets"] if isinstance(payload, dict) else payload
    else:
        raise ExperimentError("Manifest must be CSV or JSON.")
    if not isinstance(rows, list):
        raise ExperimentError("Manifest must contain a list of assets.")
    for row in rows:
        for field in ("asset_id", "wide_path", "medium_path", "close_path"):
            if not str(row.get(field, "")).strip():
                raise ExperimentError(f"Manifest row is missing {field}: {row}")
    return rows


def _asset_path(manifest_path: Path, value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = manifest_path.parent / path
    if not path.exists():
        raise ExperimentError(f"Image file not found: {path}")
    return str(path)


def _missing_azure_env() -> list[str]:
    return [name for name in REQUIRED_AZURE_ENV if not os.environ.get(name)]


def _role_image_id(asset_db_id: int, role: str) -> int:
    return asset_db_id * 100 + ROLE_INDEX[role]


def _condition_paths_and_ids(
    asset_db_id: int,
    row: dict[str, Any],
    manifest_path: Path,
    condition: str,
) -> tuple[list[str], list[int]]:
    if condition == "single_medium":
        roles = ("medium",)
    elif condition == "three_view":
        roles = ("wide", "medium", "close")
    else:
        raise ExperimentError(f"Unknown condition: {condition}")
    paths = [_asset_path(manifest_path, str(row[f"{role}_path"])) for role in roles]
    image_ids = [_role_image_id(asset_db_id, role) for role in roles]
    return paths, image_ids


def _parse_site_id(value: Any) -> int | None:
    text = str(value or "").strip()
    return int(text) if text else None


def _result_payload(result, allowed_image_ids: list[int]) -> tuple[str, dict[str, Any]]:
    from app.ai_schema import validate_analysis_result, validation_error_text

    parsed_raw: Any = result.raw_response
    if isinstance(result.raw_response, str):
        try:
            parsed_raw = json.loads(result.raw_response)
        except json.JSONDecodeError:
            parsed_raw = result.raw_response

    status = "mock" if result.provider == "mock" else "complete"
    validation_error = result.validation_error
    structured_response = result.structured_response
    if structured_response is not None:
        try:
            validate_analysis_result(
                structured_response,
                allowed_image_ids=set(allowed_image_ids),
            )
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            validation_error = validation_error_text(exc)
            structured_response = None
    elif validation_error:
        status = "failed"

    return status, {
        "status": status,
        "provider": result.provider,
        "damage_tags": result.damage_tags,
        "severity": result.severity,
        "confidence": result.confidence,
        "summary": result.summary,
        "recommended_action": result.recommended_action,
        "uncertainty": result.uncertainty,
        "schema_version": result.schema_version,
        "validation_error": validation_error,
        "structured_response": structured_response,
        "raw_response": parsed_raw,
    }


def run_experiment(
    *,
    manifest_path: Path,
    db_path: Path,
    use_azure: bool,
    seed: int,
    operator: str,
) -> dict[str, Any]:
    rows = _load_manifest(manifest_path)
    if use_azure:
        missing = _missing_azure_env()
        if missing:
            raise ExperimentError(
                "Missing Azure environment variable(s): " + ", ".join(missing)
            )
    os.environ["HERITAGERISK_DB_PATH"] = str(db_path)
    os.environ["AZURE_OPENAI_ENABLED"] = "true" if use_azure else "false"

    from app.config import settings
    from app.database import Base, SessionLocal, apply_sqlite_startup_migrations, engine
    from app.models import AssessmentCondition, AssessmentSession, ExperimentAsset
    from app.services.ai_analysis import analyze_observation_images
    from app.services.providers.azure_openai_provider import (
        PROMPT_SETTINGS,
        analysis_prompt_sha256,
    )

    Base.metadata.create_all(bind=engine)
    apply_sqlite_startup_migrations(engine)

    model_deployment = (
        settings.azure_openai_deployment if use_azure else "mock"
    ) or "mock"
    prompt_sha256 = analysis_prompt_sha256(model_deployment)
    rng = random.Random(seed)
    created = 0
    skipped = 0
    db = SessionLocal()
    try:
        for row in rows:
            asset = (
                db.query(ExperimentAsset)
                .filter(ExperimentAsset.external_asset_id == str(row["asset_id"]))
                .one_or_none()
            )
            if asset is None:
                asset = ExperimentAsset(
                    external_asset_id=str(row["asset_id"]),
                    site_id=_parse_site_id(row.get("site_id")),
                    notes=str(row.get("notes", "") or ""),
                )
                db.add(asset)
                db.flush()
            else:
                asset.site_id = _parse_site_id(row.get("site_id")) or asset.site_id
                asset.notes = str(row.get("notes", asset.notes or "") or "")
                db.flush()

            order = list(CONDITIONS)
            rng.shuffle(order)
            for run_order, condition in enumerate(order, start=1):
                existing = (
                    db.query(AssessmentSession)
                    .filter(
                        AssessmentSession.asset_id == asset.id,
                        AssessmentSession.condition == condition,
                    )
                    .one_or_none()
                )
                if existing is not None:
                    skipped += 1
                    continue

                image_paths, image_ids = _condition_paths_and_ids(
                    asset.id,
                    row,
                    manifest_path,
                    condition,
                )
                result = analyze_observation_images(
                    image_paths,
                    notes=asset.notes,
                    image_ids=image_ids,
                )
                _, payload = _result_payload(result, image_ids)
                session = AssessmentSession(
                    asset_id=asset.id,
                    condition=AssessmentCondition(condition),
                    image_ids=image_ids,
                    prompt_sha256=prompt_sha256,
                    schema_version=payload["schema_version"],
                    model_deployment=model_deployment,
                    settings={
                        "mode": "azure" if use_azure else "mock",
                        "seed": seed,
                        "prompt_settings": PROMPT_SETTINGS,
                    },
                    analysis_result=payload,
                    run_at=datetime.utcnow(),
                    run_order=run_order,
                    operator=operator,
                )
                db.add(session)
                db.flush()
                session.analysis_result_id = session.id
                db.commit()
                created += 1

        summary = {
            "assets": db.query(ExperimentAsset).count(),
            "sessions": db.query(AssessmentSession).count(),
            "created_sessions": created,
            "skipped_sessions": skipped,
            "seed": seed,
            "mode": "azure" if use_azure else "mock",
            "prompt_sha256": prompt_sha256,
        }
    finally:
        db.close()
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--db-path", type=Path, default=REPO_ROOT / "data" / "heritagerisk.db")
    parser.add_argument("--seed", type=int, default=20260723)
    parser.add_argument("--operator", default=os.environ.get("USER", "experiment"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="Use offline mock analysis.")
    mode.add_argument("--azure", action="store_true", help="Use live Azure analysis.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        summary = run_experiment(
            manifest_path=args.manifest,
            db_path=args.db_path,
            use_azure=bool(args.azure),
            seed=args.seed,
            operator=args.operator,
        )
    except ExperimentError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
