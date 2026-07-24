import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.image_helpers import make_image_bytes


REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = REPO_ROOT / "scripts" / "seed_demo.py"


def _write_demo_assets(asset_dir: Path) -> None:
    site_a = asset_dir / "stone_church"
    site_b = asset_dir / "iron_bridge"
    site_c = asset_dir / "statue"
    for directory in (site_a, site_b, site_c):
        directory.mkdir(parents=True)

    png = make_image_bytes("PNG", size=(4, 4))
    for directory, names in {
        site_a: ["front.png", "side.png", "detail.png", "tower.png"],
        site_b: ["bridge.png", "joint.png"],
        site_c: ["statue.png"],
    }.items():
        for name in names:
            (directory / name).write_bytes(png)

    manifest = {
        "sites": [
            {
                "name": "Demo Stone Church",
                "location": "Demo Valley",
                "description": "Stone church with multiple elevations.",
                "asset_dir": "stone_church",
                "observations": [
                    {
                        "images": ["front.png", "side.png", "detail.png"],
                        "contributor_notes": "Contributor noted graffiti only.",
                        "tags": ["graffiti"],
                        "severity": 2,
                        "reviewer_notes": "Reviewer notes cracking and water staining.",
                        "review_tags": ["crack", "water_staining"],
                        "review_severity": 3,
                        "final_tags": ["erosion"],
                        "final_severity": 4,
                        "final_summary": "Reviewer finalized erosion as the main visible issue.",
                        "final_recommended_action": "Human review before routing.",
                        "status_events": [
                            {
                                "status": "Needs Review",
                                "note": "Ready for conservation review.",
                            }
                        ],
                    },
                    {
                        "images": ["tower.png"],
                        "contributor_notes": "Crack visible near tower opening.",
                        "tags": ["crack"],
                        "severity": 3,
                        "status_events": [
                            {"status": "Needs Review"},
                            {"status": "Verified", "note": "Verified by reviewer."},
                        ],
                    },
                ],
            },
            {
                "name": "Demo Iron Bridge",
                "location": "Demo River",
                "description": "Iron bridge with visible corrosion.",
                "asset_dir": "iron_bridge",
                "observations": [
                    {
                        "images": ["bridge.png"],
                        "contributor_notes": "Rust and corrosion around the joint.",
                        "tags": ["corrosion"],
                        "severity": 3,
                        "status_events": [
                            {"status": "Needs Review"},
                            {"status": "Verified"},
                            {
                                "status": "Routed",
                                "routed_to": "Demo Council Heritage Team",
                                "note": "Route to council contact.",
                            },
                        ],
                    },
                    {
                        "images": ["joint.png"],
                        "contributor_notes": "Blurry duplicate photo, not enough evidence.",
                        "tags": ["other"],
                        "severity": 1,
                        "review_status": "Rejected",
                    },
                ],
            },
            {
                "name": "Demo Statue",
                "location": "Demo Square",
                "description": "Statue with sensitive context.",
                "asset_dir": "statue",
                "observations": [
                    {
                        "images": ["statue.png"],
                        "contributor_notes": "Sensitive image context.",
                        "tags": ["other"],
                        "severity": 1,
                        "review_status": "Sensitive",
                    }
                ],
            },
        ]
    }
    (asset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _run_seed(asset_dir: Path, db_path: Path, uploads_dir: Path, reports_dir: Path):
    env = os.environ.copy()
    env.update(
        {
            "REVIEWER_USERNAME": "script.reviewer",
            "REVIEWER_PASSWORD": "fake-script-password",
            "AZURE_OPENAI_ENABLED": "false",
            "PYTHONPATH": str(REPO_ROOT / "backend"),
        }
    )
    return subprocess.run(
        [
            sys.executable,
            str(SEED_SCRIPT),
            "--mock",
            "--assets",
            str(asset_dir),
            "--db-path",
            str(db_path),
            "--uploads-dir",
            str(uploads_dir),
            "--reports-dir",
            str(reports_dir),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _db_counts(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        statuses = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM risk_cases
                GROUP BY status
                """
            ).fetchall()
        }
        ai_statuses = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT ai_analysis_status, COUNT(*) AS count
                FROM observations
                GROUP BY ai_analysis_status
                """
            ).fetchall()
        }
        return {
            "sites": connection.execute("SELECT COUNT(*) FROM sites").fetchone()[0],
            "observations": connection.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0],
            "images": connection.execute(
                "SELECT COUNT(*) FROM observation_images"
            ).fetchone()[0],
            "cases": connection.execute("SELECT COUNT(*) FROM risk_cases").fetchone()[0],
            "case_events": connection.execute(
                "SELECT COUNT(*) FROM case_events"
            ).fetchone()[0],
            "three_image_observations": connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT observation_id
                    FROM observation_images
                    GROUP BY observation_id
                    HAVING COUNT(*) >= 3
                )
                """
            ).fetchone()[0],
            "statuses": statuses,
            "ai_statuses": ai_statuses,
        }


def test_seed_demo_mock_mode_builds_expected_idempotent_database(tmp_path):
    asset_dir = tmp_path / "demo_assets"
    db_path = tmp_path / "demo.db"
    uploads_dir = tmp_path / "uploads"
    reports_dir = tmp_path / "reports"
    _write_demo_assets(asset_dir)

    first = _run_seed(asset_dir, db_path, uploads_dir, reports_dir)
    assert first.returncode == 0, first.stderr
    first_summary = json.loads(first.stdout)

    first_counts = _db_counts(db_path)
    assert first_counts["sites"] == 3
    assert first_counts["observations"] == 5
    assert first_counts["images"] == 7
    assert first_counts["cases"] == 3
    assert first_counts["case_events"] == 6
    assert first_counts["three_image_observations"] >= 1
    assert first_counts["statuses"]["Needs Review"] == 1
    assert first_counts["statuses"]["Verified"] == 1
    assert first_counts["statuses"]["Routed"] == 1
    assert first_counts["ai_statuses"]["mock"] == 3
    assert "complete" not in first_counts["ai_statuses"]
    assert first_summary["ai_statuses"]["mock"] == 3

    second = _run_seed(asset_dir, db_path, uploads_dir, reports_dir)
    assert second.returncode == 0, second.stderr
    second_counts = _db_counts(db_path)
    assert second_counts == first_counts
