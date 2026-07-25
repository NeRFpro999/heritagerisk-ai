"""Build a demo database from privacy-cleared image assets."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import sys
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_ASSET_DIR = REPO_ROOT / "demo_assets"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "heritagerisk.db"
DEFAULT_UPLOADS_DIR = REPO_ROOT / "data" / "uploads"
DEFAULT_REPORTS_DIR = REPO_ROOT / "reports"
REQUIRED_AZURE_ENV = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


class SeedError(RuntimeError):
    pass


def _load_manifest(asset_dir: Path) -> dict[str, Any]:
    manifest_path = asset_dir / "manifest.json"
    if not manifest_path.exists():
        raise SeedError(f"Missing manifest: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SeedError(f"Invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sites"), list):
        raise SeedError("manifest.json must contain a top-level sites list.")
    return manifest


def _clean_output(db_path: Path, uploads_dir: Path, reports_dir: Path) -> None:
    for path in (db_path,):
        path = path.resolve()
        if path.exists():
            path.unlink()
    for directory in (uploads_dir, reports_dir):
        directory = directory.resolve()
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)


def _missing_azure_env() -> list[str]:
    return [
        name
        for name in REQUIRED_AZURE_ENV
        if not os.environ.get(name, "").strip()
    ]


def _csrf_data(client: TestClient, data: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.auth import CSRF_COOKIE_NAME, CSRF_FORM_FIELD

    client.get("/")
    token = client.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        raise SeedError("Could not establish CSRF cookie.")
    form_data = dict(data or {})
    form_data[CSRF_FORM_FIELD] = token
    return form_data


def _post_form(
    client: TestClient,
    path: str,
    *,
    data: dict[str, Any] | None = None,
    files: list[tuple[str, tuple[str, Any, str]]] | None = None,
    follow_redirects: bool = True,
):
    return client.post(
        path,
        data=_csrf_data(client, data),
        files=files,
        follow_redirects=follow_redirects,
    )


def _configure_reviewer() -> tuple[str, str]:
    from app.auth import hash_reviewer_password
    from app.config import settings

    username = os.environ.get("REVIEWER_USERNAME", "").strip()
    password = os.environ.get("REVIEWER_PASSWORD", "")
    password_hash = os.environ.get("REVIEWER_PASSWORD_HASH", "").strip()
    if not username:
        raise SeedError("Missing REVIEWER_USERNAME.")
    if not password and not password_hash:
        raise SeedError(
            "Set REVIEWER_PASSWORD for demo seeding, or provide both "
            "REVIEWER_PASSWORD_HASH and a REVIEWER_PASSWORD that can log in."
        )
    if password and not password_hash:
        password_hash = hash_reviewer_password(password)
        os.environ["REVIEWER_PASSWORD_HASH"] = password_hash

    settings.reviewer_username = username
    settings.reviewer_password_hash = password_hash
    return username, password


def _login(client: TestClient, password: str) -> str:
    from app.config import settings

    if not password:
        raise SeedError("REVIEWER_PASSWORD is required to exercise the login route.")
    response = _post_form(
        client,
        "/reviewer/login",
        data={
            "username": settings.reviewer_username,
            "password": password,
            "next_path": "/observations/review",
        },
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise SeedError(f"Reviewer login failed with status {response.status_code}.")
    return settings.reviewer_username


def _asset_path(asset_dir: Path, site_dir: str, image_name: str) -> Path:
    path = (asset_dir / site_dir / image_name).resolve()
    asset_root = asset_dir.resolve()
    if asset_root not in path.parents:
        raise SeedError(f"Image path escapes demo asset directory: {image_name}")
    if not path.exists():
        raise SeedError(f"Missing image: {path}")
    return path


def _image_files(
    stack: ExitStack,
    asset_dir: Path,
    site_dir: str,
    image_names: list[str],
) -> list[tuple[str, tuple[str, Any, str]]]:
    files = []
    for image_name in image_names:
        image_path = _asset_path(asset_dir, site_dir, image_name)
        mime_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
        files.append(
            (
                "images",
                (
                    image_path.name,
                    stack.enter_context(image_path.open("rb")),
                    mime_type,
                ),
            )
        )
    return files


def _submit_observation(
    client: TestClient,
    asset_dir: Path,
    site: dict[str, Any],
    observation: dict[str, Any],
    site_id: int | None = None,
) -> tuple[int, int]:
    image_names = observation.get("images")
    if not isinstance(image_names, list) or not image_names:
        raise SeedError("Each demo observation must list at least one image.")
    tags = observation.get("tags", [])
    if not isinstance(tags, list):
        raise SeedError("Observation tags must be a list.")

    with ExitStack() as stack:
        form_data = {
            "site_name": site["name"],
            "site_location": site.get("location", ""),
            "site_description": site.get("description", ""),
            "contributor_notes": observation.get("contributor_notes", ""),
            "manually_selected_tags": ",".join(tags),
            "severity": str(observation.get("severity", 1)),
            "response_mode": "json",
        }
        if site_id is not None:
            form_data = {
                "site_id": str(site_id),
                "contributor_notes": observation.get("contributor_notes", ""),
                "manually_selected_tags": ",".join(tags),
                "severity": str(observation.get("severity", 1)),
                "response_mode": "json",
            }
        response = _post_form(
            client,
            "/observations/submit",
            data=form_data,
            files=_image_files(
                stack,
                asset_dir,
                site.get("asset_dir", ""),
                image_names,
            ),
        )
    if response.status_code != 200:
        raise SeedError(f"Public submission failed: {response.status_code} {response.text}")
    payload = response.json()
    return int(payload["observation_id"]), int(payload["site_id"])


def _review_observation(
    client: TestClient,
    observation_id: int,
    observation: dict[str, Any],
) -> str:
    review_status = observation.get("review_status", "ApprovedForAI")
    response = _post_form(
        client,
        f"/observations/{observation_id}/review",
        data={
            "human_review_status": review_status,
            "reviewer_notes": observation.get(
                "reviewer_notes",
                observation.get("contributor_notes", ""),
            ),
            "manually_selected_tags": ",".join(
                observation.get("review_tags", observation.get("tags", []))
            ),
            "severity": str(observation.get("review_severity", observation.get("severity", 1))),
        },
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise SeedError(f"Review failed for observation {observation_id}: {response.text}")
    return str(review_status)


def _analyze_observation(client: TestClient, observation_id: int) -> None:
    response = _post_form(
        client,
        f"/observations/{observation_id}/analyze",
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise SeedError(f"Analysis failed for observation {observation_id}: {response.text}")


def _finalize_case(
    client: TestClient,
    observation_id: int,
    observation: dict[str, Any],
) -> int:
    response = _post_form(
        client,
        f"/observations/{observation_id}/create_risk_case",
        data={
            "final_damage_tags": observation.get(
                "final_tags",
                observation.get("review_tags", observation.get("tags", [])),
            ),
            "final_severity": str(
                observation.get(
                    "final_severity",
                    observation.get("review_severity", observation.get("severity", 1)),
                )
            ),
            "final_ai_summary": observation.get("final_summary", ""),
            "final_recommended_action": observation.get("final_recommended_action", ""),
            "reviewer_final_notes": observation.get("final_notes", ""),
        },
        follow_redirects=False,
    )
    if response.status_code != 303:
        raise SeedError(f"Case finalization failed for observation {observation_id}: {response.text}")
    return int(response.headers["location"].rsplit("/", 1)[-1])


def _apply_status_events(
    client: TestClient,
    case_id: int,
    status_events: list[dict[str, Any]],
) -> None:
    for event in status_events:
        response = _post_form(
            client,
            f"/cases/{case_id}/status",
            data={
                "status": event["status"],
                "routed_to": event.get("routed_to", ""),
                "status_note": event.get("note", ""),
            },
            follow_redirects=False,
        )
        if response.status_code != 303:
            raise SeedError(f"Status transition failed for case {case_id}: {response.text}")


def _assert_required_demo_state(db) -> None:
    from app.models import CaseEvent, HumanReviewStatus, Observation, ObservationImage, RiskCase

    observations = db.query(Observation).all()
    cases = db.query(RiskCase).all()
    if db.query(ObservationImage).count() == 0:
        raise SeedError("Seeded database has no ObservationImage rows.")
    if not any(len(observation.images) >= 3 for observation in observations):
        raise SeedError("Expected at least one observation with 3 images.")
    if not any(
        observation.human_review_status == HumanReviewStatus.REJECTED
        for observation in observations
    ):
        raise SeedError("Expected at least one rejected observation.")
    if not any(
        observation.human_review_status == HumanReviewStatus.SENSITIVE
        for observation in observations
    ):
        raise SeedError("Expected at least one sensitive observation.")
    case_statuses = {case.status for case in cases}
    if len(case_statuses) < 3:
        raise SeedError("Expected cases in at least three statuses.")
    if db.query(CaseEvent).count() == 0:
        raise SeedError("Expected status event history.")
    edited = [
        case
        for case in cases
        if isinstance(case.final_snapshot, dict)
        and case.final_snapshot.get("final_tags")
        != case.final_snapshot.get("ai_proposal", {}).get("damage_tags")
        and case.final_snapshot.get("final_tags")
        != case.final_snapshot.get("contributor_original", {}).get("tags")
    ]
    if not edited:
        raise SeedError("Expected at least one case where original, AI, and final tags differ.")


def _summary(db) -> dict[str, Any]:
    from app.models import CaseEvent, Observation, ObservationImage, RiskCase, Site

    return {
        "sites": db.query(Site).count(),
        "observations": db.query(Observation).count(),
        "images": db.query(ObservationImage).count(),
        "cases": db.query(RiskCase).count(),
        "case_events": db.query(CaseEvent).count(),
        "case_statuses": {
            status: db.query(RiskCase).filter(RiskCase.status == status).count()
            for status in RiskCase.STATUSES
        },
        "ai_statuses": {
            status: db.query(Observation).filter(Observation.ai_analysis_status == status).count()
            for status in ("not_run", "mock", "complete", "failed")
        },
    }


def run_seed(
    *,
    asset_dir: Path,
    db_path: Path,
    uploads_dir: Path,
    reports_dir: Path,
    use_azure: bool,
) -> dict[str, Any]:
    manifest = _load_manifest(asset_dir)
    if use_azure:
        missing = _missing_azure_env()
        if missing:
            raise SeedError(
                "Missing Azure environment variable(s): " + ", ".join(missing)
            )
    _clean_output(db_path, uploads_dir, reports_dir)

    os.environ["HERITAGERISK_DB_PATH"] = str(db_path)
    os.environ["HERITAGERISK_UPLOADS_DIR"] = str(uploads_dir)
    os.environ["HERITAGERISK_REPORTS_DIR"] = str(reports_dir)
    os.environ["AZURE_OPENAI_ENABLED"] = "true" if use_azure else "false"

    _, password = _configure_reviewer()

    from app.database import SessionLocal
    from app.main import app

    client = TestClient(app, raise_server_exceptions=True)
    _login(client, password)

    started = perf_counter()
    created_cases: list[int] = []
    for site in manifest["sites"]:
        for required in ("name",):
            if not str(site.get(required, "")).strip():
                raise SeedError(f"Manifest site is missing {required}.")
        observations = site.get("observations")
        if not isinstance(observations, list):
            raise SeedError(f"Site {site['name']} must include observations.")
        site_id = None
        for observation in observations:
            observation_id, site_id = _submit_observation(
                client,
                asset_dir,
                site,
                observation,
                site_id,
            )
            review_status = _review_observation(client, observation_id, observation)
            if review_status != "ApprovedForAI":
                continue
            _analyze_observation(client, observation_id)
            case_id = _finalize_case(client, observation_id, observation)
            created_cases.append(case_id)
            _apply_status_events(client, case_id, observation.get("status_events", []))

    db = SessionLocal()
    try:
        _assert_required_demo_state(db)
        summary = _summary(db)
    finally:
        db.close()

    summary["created_case_ids"] = created_cases
    summary["mode"] = "azure" if use_azure else "mock"
    summary["elapsed_seconds"] = round(perf_counter() - started, 3)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--uploads-dir", type=Path, default=DEFAULT_UPLOADS_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="Use offline mock analysis.")
    mode.add_argument("--azure", action="store_true", help="Use live Azure analysis.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_seed(
            asset_dir=args.assets.resolve(),
            db_path=args.db_path.resolve(),
            uploads_dir=args.uploads_dir.resolve(),
            reports_dir=args.reports_dir.resolve(),
            use_azure=bool(args.azure),
        )
    except SeedError as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
