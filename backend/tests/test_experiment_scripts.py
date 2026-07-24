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
                "site_label": "site-north",
                "wide_path": "a_wide.png",
                "medium_path": "a_medium.png",
                "close_path": "a_close.png",
                "notes": "Crack and water staining visible in test notes.",
            },
            {
                "asset_id": "asset-b",
                "site_label": "site-south",
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


def _run_experiment(
    manifest_path: Path,
    db_path: Path,
    asset_set: str | None = None,
    repeat_runs: int | None = None,
):
    env = os.environ.copy()
    env.update(
        {
            "AZURE_OPENAI_ENABLED": "false",
            "PYTHONPATH": str(REPO_ROOT / "backend"),
        }
    )
    command = [
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
    ]
    if asset_set is not None:
        command.extend(["--asset-set", asset_set])
    if repeat_runs is not None:
        command.extend(["--repeat-runs", str(repeat_runs)])
    return subprocess.run(
        command,
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
                experiment_assets.site_label,
                assessment_sessions.condition,
                assessment_sessions.run_index,
                assessment_sessions.image_ids,
                assessment_sessions.prompt_template_sha256,
                assessment_sessions.rendered_request_sha256,
                assessment_sessions.analysis_result,
                assessment_sessions.settings,
                assessment_sessions.run_order
            FROM assessment_sessions
            JOIN experiment_assets
              ON experiment_assets.id = assessment_sessions.asset_id
            ORDER BY
                experiment_assets.external_asset_id,
                assessment_sessions.run_index,
                assessment_sessions.condition
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
    prompt_template_hashes = set()
    rendered_hashes: dict[tuple[str, str], str] = {}
    for session in sessions:
        by_asset.setdefault(session["external_asset_id"], {})[session["condition"]] = session
        prompt_template_hashes.add(session["prompt_template_sha256"])
        rendered_hashes[
            (session["external_asset_id"], session["condition"])
        ] = session["rendered_request_sha256"]
        result = json.loads(session["analysis_result"])
        settings = json.loads(session["settings"])
        assert result["provider"] == "mock"
        assert result["status"] == "mock"
        assert result["structured_response"]["schema_version"] == "2"
        assert settings["asset_set"] == "pilot"
        assert settings["request_settings"] == {"max_completion_tokens": 600}
        assert "temperature" not in settings["request_settings"]
        assert "schema_version" not in settings["request_settings"]
        assert session["run_index"] == 0
    assert len(prompt_template_hashes) == 1
    for condition in ("single_medium", "three_view"):
        assert (
            rendered_hashes[("asset-a", condition)]
            != rendered_hashes[("asset-b", condition)]
        )
    assert {
        session["external_asset_id"]: session["site_label"]
        for session in sessions
    } == {
        "asset-a": "site-north",
        "asset-b": "site-south",
    }

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
    assert {row["condition"] for row in rows} == {
        "single_medium",
        "three_view",
    }
    assert {
        (row["external_asset_id"], row["site_label"])
        for row in rows
    } == {
        ("asset-a", "site-north"),
        ("asset-b", "site-south"),
    }
    assert all(row["site_label"] for row in indicator_rows)
    assert {row["run_index"] for row in rows} == {"0"}
    assert all(row["prompt_template_sha256"] for row in rows)
    assert all(row["rendered_request_sha256"] for row in rows)


def test_run_experiment_selects_pilot_held_out_and_all_asset_sets(tmp_path):
    image_bytes = make_image_bytes("PNG", size=(4, 4))

    def asset_row(asset_id: str) -> dict:
        for role in ("wide", "medium", "close"):
            (tmp_path / f"{asset_id}_{role}.png").write_bytes(image_bytes)
        return {
            "asset_id": asset_id,
            "wide_path": f"{asset_id}_wide.png",
            "medium_path": f"{asset_id}_medium.png",
            "close_path": f"{asset_id}_close.png",
            "notes": f"Synthetic notes for {asset_id}.",
        }

    manifest_path = tmp_path / "split_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "assets": [
                    asset_row("pilot-a"),
                    asset_row("pilot-b"),
                ],
                "held_out_assets": [
                    asset_row("held-a"),
                    asset_row("held-b"),
                    asset_row("held-c"),
                ],
            }
        ),
        encoding="utf-8",
    )

    expectations = {
        "pilot": (tmp_path / "pilot.db", 2, 4),
        "held_out": (tmp_path / "held-out.db", 3, 6),
        "all": (tmp_path / "all.db", 5, 10),
    }
    for asset_set, (db_path, asset_count, session_count) in expectations.items():
        result = _run_experiment(
            manifest_path,
            db_path,
            asset_set=asset_set,
        )
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert summary["asset_set"] == asset_set
        assert summary["selected_assets"] == asset_count
        assert summary["assets"] == asset_count
        assert summary["created_sessions"] == session_count
        assert summary["sessions"] == session_count

        sessions = _sessions(db_path)
        assert len(sessions) == session_count
        assert {
            json.loads(session["settings"])["asset_set"]
            for session in sessions
        } == {asset_set}


def test_repeat_runs_create_four_sessions_and_resume_by_run_index(tmp_path):
    manifest_path = _write_assets(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"] = manifest["assets"][:1]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    db_path = tmp_path / "repeat.db"
    export_path = tmp_path / "repeat.csv"

    first = _run_experiment(manifest_path, db_path, repeat_runs=2)
    assert first.returncode == 0, first.stderr
    first_summary = json.loads(first.stdout)
    assert first_summary["repeat_runs"] == 2
    assert first_summary["created_sessions"] == 4
    assert first_summary["sessions"] == 4

    sessions = _sessions(db_path)
    assert len(sessions) == 4
    assert {
        (session["condition"], session["run_index"])
        for session in sessions
    } == {
        ("single_medium", 0),
        ("three_view", 0),
        ("single_medium", 1),
        ("three_view", 1),
    }
    assert len(
        {session["prompt_template_sha256"] for session in sessions}
    ) == 1
    assert len(
        {
            json.dumps(json.loads(session["settings"]), sort_keys=True)
            for session in sessions
        }
    ) == 1
    for condition in ("single_medium", "three_view"):
        condition_rows = [
            session for session in sessions if session["condition"] == condition
        ]
        assert len(
            {
                session["rendered_request_sha256"]
                for session in condition_rows
            }
        ) == 1
        assert len(
            {
                tuple(json.loads(session["image_ids"]))
                for session in condition_rows
            }
        ) == 1

    exported = _export_results(db_path, export_path)
    assert exported.returncode == 0, exported.stderr
    rows = list(csv.DictReader(export_path.open(encoding="utf-8")))
    session_rows = [row for row in rows if row["row_type"] == "session"]
    indicator_rows = [row for row in rows if row["row_type"] == "indicator"]
    assert len(session_rows) == 4
    assert {row["run_index"] for row in session_rows} == {"0", "1"}
    assert indicator_rows
    assert {row["run_index"] for row in indicator_rows} == {"0", "1"}
    assert all(row["prompt_template_sha256"] for row in rows)
    assert all(row["rendered_request_sha256"] for row in rows)

    resumed = _run_experiment(manifest_path, db_path, repeat_runs=2)
    assert resumed.returncode == 0, resumed.stderr
    resumed_summary = json.loads(resumed.stdout)
    assert resumed_summary["created_sessions"] == 0
    assert resumed_summary["skipped_sessions"] == 4
    assert resumed_summary["sessions"] == 4
    assert len(_sessions(db_path)) == 4


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
