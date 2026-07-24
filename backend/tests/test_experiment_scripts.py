import csv
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.image_helpers import make_image_bytes


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = REPO_ROOT / "scripts" / "run_experiment.py"
EXPORT_SCRIPT = REPO_ROOT / "scripts" / "export_results.py"


def _write_assets(tmp_path: Path) -> Path:
    image_bytes = make_image_bytes("PNG", size=(4, 4))
    for name in ("a_wide.png", "a_medium.png", "a_close.png", "b_wide.png", "b_medium.png", "b_close.png"):
        (tmp_path / name).write_bytes(image_bytes)
    manifest = {
        "assets": [
            {
                "asset_id": "asset-a",
                "wide_path": "a_wide.png",
                "medium_path": "a_medium.png",
                "close_path": "a_close.png",
                "notes": "Crack and water staining visible in test notes.",
            },
            {
                "asset_id": "asset-b",
                "wide_path": "b_wide.png",
                "medium_path": "b_medium.png",
                "close_path": "b_close.png",
                "notes": "Graffiti visible in test notes.",
            },
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _run_experiment(manifest_path: Path, db_path: Path):
    env = os.environ.copy()
    env.update(
        {
            "AZURE_OPENAI_ENABLED": "false",
            "PYTHONPATH": str(REPO_ROOT / "backend"),
        }
    )
    return subprocess.run(
        [
            sys.executable,
            str(RUN_SCRIPT),
            str(manifest_path),
            "--db-path",
            str(db_path),
            "--mock",
            "--seed",
            "12345",
            "--operator",
            "test-operator",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _export_results(db_path: Path, output_path: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "backend")
    return subprocess.run(
        [
            sys.executable,
            str(EXPORT_SCRIPT),
            "--db-path",
            str(db_path),
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _sessions(db_path: Path):
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT
                experiment_assets.external_asset_id,
                assessment_sessions.condition,
                assessment_sessions.image_ids,
                assessment_sessions.prompt_sha256,
                assessment_sessions.analysis_result,
                assessment_sessions.run_order
            FROM assessment_sessions
            JOIN experiment_assets
              ON experiment_assets.id = assessment_sessions.asset_id
            ORDER BY experiment_assets.external_asset_id, assessment_sessions.condition
            """
        ).fetchall()


def test_run_experiment_mock_creates_paired_sessions_and_exports(tmp_path):
    manifest_path = _write_assets(tmp_path)
    db_path = tmp_path / "experiment.db"
    export_path = tmp_path / "results.csv"

    first = _run_experiment(manifest_path, db_path)
    assert first.returncode == 0, first.stderr
    first_summary = json.loads(first.stdout)
    assert first_summary["assets"] == 2
    assert first_summary["sessions"] == 4
    assert first_summary["created_sessions"] == 4

    sessions = _sessions(db_path)
    assert len(sessions) == 4
    by_asset: dict[str, dict[str, sqlite3.Row]] = {}
    prompt_hashes = set()
    for session in sessions:
        by_asset.setdefault(session["external_asset_id"], {})[session["condition"]] = session
        prompt_hashes.add(session["prompt_sha256"])
        result = json.loads(session["analysis_result"])
        assert result["provider"] == "mock"
        assert result["status"] == "mock"
        assert result["structured_response"]["schema_version"] == "2"
    assert len(prompt_hashes) == 1

    for conditions in by_asset.values():
        assert set(conditions) == {"single_medium", "three_view"}
        single_ids = json.loads(conditions["single_medium"]["image_ids"])
        three_ids = json.loads(conditions["three_view"]["image_ids"])
        assert single_ids == [three_ids[1]]

    second = _run_experiment(manifest_path, db_path)
    assert second.returncode == 0, second.stderr
    second_summary = json.loads(second.stdout)
    assert second_summary["sessions"] == 4
    assert second_summary["created_sessions"] == 0
    assert len(_sessions(db_path)) == 4

    exported = _export_results(db_path, export_path)
    assert exported.returncode == 0, exported.stderr
    rows = list(csv.DictReader(export_path.open(encoding="utf-8")))
    assert sum(row["row_type"] == "session" for row in rows) == 4
    indicator_rows = [row for row in rows if row["row_type"] == "indicator"]
    assert indicator_rows
    assert {row["condition"] for row in rows} == {"single_medium", "three_view"}
    assert all(row["prompt_sha256"] for row in rows)


def test_run_experiment_resume_after_partial_database_does_not_duplicate(tmp_path):
    manifest_path = _write_assets(tmp_path)
    db_path = tmp_path / "experiment.db"

    first = _run_experiment(manifest_path, db_path)
    assert first.returncode == 0, first.stderr

    with sqlite3.connect(db_path) as connection:
        asset_id = connection.execute(
            """
            SELECT asset_id
            FROM assessment_sessions
            WHERE condition = 'three_view'
            LIMIT 1
            """
        ).fetchone()[0]
        connection.execute(
            """
            DELETE FROM assessment_sessions
            WHERE asset_id = ? AND condition = 'three_view'
            """,
            (asset_id,),
        )
        connection.commit()

    resumed = _run_experiment(manifest_path, db_path)
    assert resumed.returncode == 0, resumed.stderr
    summary = json.loads(resumed.stdout)
    assert summary["created_sessions"] == 1
    assert summary["sessions"] == 4
    assert len(_sessions(db_path)) == 4
