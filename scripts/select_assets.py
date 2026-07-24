#!/usr/bin/env python3
"""Select cleared complete asset groups for paired experiment runs."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "research" / "corpus" / "experiment_manifest.json"
ROLES = ("WIDE", "MEDIUM", "CLOSE")


class AssetSelectionError(RuntimeError):
    pass


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssetSelectionError(f"Manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("photos"), list):
        raise AssetSelectionError("Manifest must contain a photos list.")
    return payload


def _photo_is_cleared(photo: dict[str, Any]) -> bool:
    return (
        photo.get("privacy_status") == "cleared"
        and photo.get("cultural_sensitivity_status") == "cleared"
    )


def _complete_groups(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for photo in manifest["photos"]:
        if not _photo_is_cleared(photo):
            continue
        role = photo.get("capture_role")
        if role in ROLES:
            grouped[photo["asset_group_id"]][role] = photo

    complete: list[dict[str, Any]] = []
    source_root = Path(manifest.get("source_root") or ".")
    for group_id, by_role in grouped.items():
        if not all(role in by_role for role in ROLES):
            continue
        site_labels = sorted({by_role[role].get("site_label", "") for role in ROLES})
        notes = "; ".join(
            sorted(
                {
                    note
                    for role in ROLES
                    if (note := str(by_role[role].get("provenance_note", "")).strip())
                }
            )
        )
        complete.append(
            {
                "asset_id": group_id,
                "wide_path": str(source_root / by_role["WIDE"]["relative_path"]),
                "medium_path": str(source_root / by_role["MEDIUM"]["relative_path"]),
                "close_path": str(source_root / by_role["CLOSE"]["relative_path"]),
                "notes": notes,
                "site_label": ", ".join(site_labels),
            }
        )
    return sorted(complete, key=lambda row: row["asset_id"])


def select_assets(
    *,
    manifest_path: Path,
    output_path: Path,
    seed: int,
    pilot_size: int = 6,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    complete = _complete_groups(manifest)
    rng = random.Random(seed)
    shuffled = list(complete)
    rng.shuffle(shuffled)
    pilot = shuffled[:pilot_size]
    held_out = shuffled[pilot_size:]
    output = {
        "schema_version": "1",
        "source_manifest": str(manifest_path),
        "split_seed": seed,
        "pilot_size": min(pilot_size, len(shuffled)),
        "assets": pilot,
        "held_out_assets": held_out,
        "summary": {
            "complete_cleared_asset_groups": len(complete),
            "pilot_assets": len(pilot),
            "held_out_assets": len(held_out),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260723)
    parser.add_argument("--pilot-size", type=int, default=6)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        output = select_assets(
            manifest_path=args.manifest,
            output_path=args.output,
            seed=args.seed,
            pilot_size=args.pilot_size,
        )
    except AssetSelectionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(output["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
