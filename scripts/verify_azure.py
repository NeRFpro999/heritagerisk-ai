"""Verify one live Azure analysis through the HeritageRisk app workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi.testclient import TestClient

from seed_demo import (
    DEFAULT_ASSET_DIR,
    REPO_ROOT,
    SeedError,
    _analyze_observation,
    _clean_output,
    _configure_reviewer,
    _load_manifest,
    _login,
    _review_observation,
    _submit_observation,
)


DEFAULT_VERIFY_DB = REPO_ROOT / "data" / "azure_verify.db"
DEFAULT_VERIFY_UPLOADS = REPO_ROOT / "data" / "azure_verify_uploads"
DEFAULT_VERIFY_REPORTS = REPO_ROOT / "reports" / "azure_verify"
REQUIRED_AZURE_ENV = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_PRIMARY_DEPLOYMENT",
)


def _missing_azure_env() -> list[str]:
    missing = [name for name in REQUIRED_AZURE_ENV if not os.environ.get(name, "").strip()]
    if os.environ.get("AZURE_OPENAI_ENABLED", "").lower() != "true":
        missing.append("AZURE_OPENAI_ENABLED=true")
    return missing


def _first_approved_observation(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    for site in manifest["sites"]:
        for observation in site.get("observations", []):
            if observation.get("review_status", "ApprovedForAI") == "ApprovedForAI":
                return site, observation
    raise SeedError("Manifest has no ApprovedForAI observation to verify.")


def _result_payload(db, observation_id: int, latency_seconds: float) -> dict[str, Any]:
    from app.config import settings
    from app.models import Observation

    observation = db.query(Observation).filter_by(id=observation_id).one()
    raw = {}
    if observation.ai_raw_response:
        try:
            raw = json.loads(observation.ai_raw_response)
        except json.JSONDecodeError:
            raw = {"unparseable_raw_response": observation.ai_raw_response}

    validation_passed = (
        observation.ai_analysis_status == "complete"
        and isinstance(observation.ai_provider, str)
        and observation.ai_provider.startswith("azure:")
        and isinstance(raw.get("damage_tags"), list)
        and isinstance(raw.get("severity"), int)
        and isinstance(raw.get("confidence"), int)
        and isinstance(raw.get("summary"), str)
        and isinstance(raw.get("recommended_action"), str)
    )
    return {
        "validation_passed": validation_passed,
        "latency_seconds": round(latency_seconds, 3),
        "deployment": settings.azure_openai_deployment,
        "observation_id": observation.id,
        "analysis_status": observation.ai_analysis_status,
        "provider": observation.ai_provider,
        "structured_result": {
            "damage_tags": raw.get("damage_tags"),
            "severity": raw.get("severity"),
            "confidence": raw.get("confidence"),
            "summary": raw.get("summary"),
            "uncertainty": raw.get("uncertainty"),
            "recommended_action": raw.get("recommended_action"),
        },
        "preserved_failure_state": None
        if validation_passed
        else {
            "ai_analysis_status": observation.ai_analysis_status,
            "ai_provider": observation.ai_provider,
            "ai_summary": observation.ai_summary,
            "ai_confidence": observation.ai_confidence,
            "ai_raw_response": observation.ai_raw_response,
        },
    }


def run_verify(
    *,
    asset_dir: Path,
    db_path: Path,
    uploads_dir: Path,
    reports_dir: Path,
) -> dict[str, Any]:
    missing = _missing_azure_env()
    if missing:
        raise SeedError("Missing Azure environment variable(s): " + ", ".join(missing))

    os.environ["HERITAGERISK_DB_PATH"] = str(db_path)
    os.environ["HERITAGERISK_UPLOADS_DIR"] = str(uploads_dir)
    os.environ["HERITAGERISK_REPORTS_DIR"] = str(reports_dir)
    _clean_output(db_path, uploads_dir, reports_dir)

    manifest = _load_manifest(asset_dir)
    site, observation = _first_approved_observation(manifest)
    _, password = _configure_reviewer()

    from app.database import SessionLocal
    from app.main import app

    client = TestClient(app, raise_server_exceptions=True)
    _login(client, password)

    observation_id, _ = _submit_observation(client, asset_dir, site, observation)
    _review_observation(client, observation_id, observation)

    started = perf_counter()
    _analyze_observation(client, observation_id)
    latency_seconds = perf_counter() - started

    db = SessionLocal()
    try:
        return _result_payload(db, observation_id, latency_seconds)
    finally:
        db.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_VERIFY_DB)
    parser.add_argument("--uploads-dir", type=Path, default=DEFAULT_VERIFY_UPLOADS)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_VERIFY_REPORTS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_verify(
            asset_dir=args.assets.resolve(),
            db_path=args.db_path.resolve(),
            uploads_dir=args.uploads_dir.resolve(),
            reports_dir=args.reports_dir.resolve(),
        )
    except SeedError as exc:
        print(f"Azure verification refused: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
