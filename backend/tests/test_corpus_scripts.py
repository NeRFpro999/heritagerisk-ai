import json
import subprocess
import sys
from pathlib import Path

from tests.image_helpers import make_image_bytes


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_corpus.py"
SELECT_SCRIPT = REPO_ROOT / "scripts" / "select_assets.py"


def _write_image(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_image_bytes("PNG", size=size))


def _write_fixture_corpus(root: Path) -> None:
    for group_index in range(1, 9):
        group = root / "site-a" / f"asset-{group_index:02d}"
        _write_image(group / f"asset-{group_index:02d}_wide.png", (group_index + 4, 5))
        _write_image(group / f"asset-{group_index:02d}_medium.png", (group_index + 4, 6))
        _write_image(group / f"asset-{group_index:02d}_close.png", (group_index + 4, 7))

    duplicate_bytes = make_image_bytes("PNG", size=(3, 3))
    duplicate_a = root / "site-a" / "asset-01" / "asset-01_wide.png"
    duplicate_b = root / "site-a" / "asset-incomplete" / "asset-incomplete_wide.png"
    duplicate_a.write_bytes(duplicate_bytes)
    duplicate_b.parent.mkdir(parents=True, exist_ok=True)
    duplicate_b.write_bytes(duplicate_bytes)
    _write_image(
        root / "site-a" / "asset-incomplete" / "asset-incomplete_medium.png",
        (3, 4),
    )

    for group_name in ("asset-private", "asset-sensitive"):
        group = root / "site-b" / group_name
        _write_image(group / f"{group_name}_wide.png", (9, 5))
        _write_image(group / f"{group_name}_medium.png", (9, 6))
        _write_image(group / f"{group_name}_close.png", (9, 7))


def _run_audit(photo_dir: Path, output: Path, report: Path, previous: Path | None = None):
    command = [
        sys.executable,
        str(AUDIT_SCRIPT),
        str(photo_dir),
        "--output",
        str(output),
        "--report",
        str(report),
        "--default-privacy-status",
        "cleared",
        "--default-cultural-sensitivity-status",
        "cleared",
    ]
    if previous is not None:
        command.extend(["--previous-manifest", str(previous)])
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_select(manifest: Path, output: Path):
    return subprocess.run(
        [
            sys.executable,
            str(SELECT_SCRIPT),
            str(manifest),
            "--output",
            str(output),
            "--seed",
            "42",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_audit_corpus_hashes_duplicates_groups_and_missing_files(tmp_path):
    corpus = tmp_path / "photos"
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "audit_report.md"
    previous = tmp_path / "previous.json"
    _write_fixture_corpus(corpus)

    first = _run_audit(corpus, manifest, report)
    assert first.returncode == 0, first.stderr
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    for photo in payload["photos"]:
        if photo["asset_group_id"] == "site-b/asset-private":
            photo["privacy_status"] = "excluded"
        if photo["asset_group_id"] == "site-b/asset-sensitive":
            photo["cultural_sensitivity_status"] = "sensitive"
    payload["photos"].append(
        {
            "photo_id": "PHOTO-MISSING",
            "sha256": "0" * 64,
            "relative_path": "site-z/missing/missing_wide.png",
            "width": 1,
            "height": 1,
            "capture_role": "WIDE",
            "asset_group_id": "site-z/missing",
            "site_label": "site-z",
            "privacy_status": "cleared",
            "cultural_sensitivity_status": "cleared",
            "provenance_note": "Previous manifest row for missing-file test.",
        }
    )
    previous.write_text(json.dumps(payload), encoding="utf-8")

    second = _run_audit(corpus, manifest, report, previous)
    assert second.returncode == 0, second.stderr
    audited = json.loads(manifest.read_text(encoding="utf-8"))
    summary = audited["summary"]

    assert summary["total_photos"] == 32
    assert summary["counts_by_role"] == {"WIDE": 11, "MEDIUM": 11, "CLOSE": 10}
    assert summary["complete_asset_groups"] == 10
    assert summary["candidate_groups_needing_validation"] == 1
    assert summary["excluded_privacy_or_sensitive_items"] == 6
    assert len(audited["missing_files"]) == 1
    assert audited["missing_files"][0]["relative_path"] == "site-z/missing/missing_wide.png"
    assert audited["duplicates"]
    duplicate_paths = {
        path
        for group in audited["duplicates"]
        for path in group["relative_paths"]
    }
    assert "site-a/asset-01/asset-01_wide.png" in duplicate_paths
    assert "site-a/asset-incomplete/asset-incomplete_wide.png" in duplicate_paths
    assert "- Total photos: 32" in report.read_text(encoding="utf-8")


def test_select_assets_excludes_uncleared_and_splits_deterministically(tmp_path):
    corpus = tmp_path / "photos"
    manifest = tmp_path / "manifest.json"
    previous = tmp_path / "previous.json"
    report = tmp_path / "audit_report.md"
    selected_a = tmp_path / "selected_a.json"
    selected_b = tmp_path / "selected_b.json"
    _write_fixture_corpus(corpus)

    first = _run_audit(corpus, manifest, report)
    assert first.returncode == 0, first.stderr
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for photo in payload["photos"]:
        if photo["asset_group_id"] == "site-b/asset-private":
            photo["privacy_status"] = "excluded"
        if photo["asset_group_id"] == "site-b/asset-sensitive":
            photo["cultural_sensitivity_status"] = "sensitive"
    previous.write_text(json.dumps(payload), encoding="utf-8")
    second = _run_audit(corpus, manifest, report, previous)
    assert second.returncode == 0, second.stderr

    result_a = _run_select(manifest, selected_a)
    result_b = _run_select(manifest, selected_b)
    assert result_a.returncode == 0, result_a.stderr
    assert result_b.returncode == 0, result_b.stderr

    output_a = json.loads(selected_a.read_text(encoding="utf-8"))
    output_b = json.loads(selected_b.read_text(encoding="utf-8"))
    assert output_a == output_b
    assert output_a["split_seed"] == 42
    assert len(output_a["assets"]) == 6
    assert len(output_a["held_out_assets"]) == 2
    selected_ids = {
        row["asset_id"]
        for row in output_a["assets"] + output_a["held_out_assets"]
    }
    assert "site-a/asset-incomplete" not in selected_ids
    assert "site-b/asset-private" not in selected_ids
    assert "site-b/asset-sensitive" not in selected_ids
    for row in output_a["assets"]:
        assert {"asset_id", "wide_path", "medium_path", "close_path"} <= set(row)
        assert Path(row["wide_path"]).exists()
