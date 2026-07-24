#!/usr/bin/env python3
"""Compute paired-experiment metrics from AI export and human labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.analysis.metrics import analyze_experiment, load_ai_export, load_human_reference
from research.analysis.reporting import render_results_markdown


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai-export", type=Path, required=True)
    parser.add_argument("--human-reference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "research" / "analysis" / "outputs")
    parser.add_argument("--seed", type=int, default=20260723)
    parser.add_argument("--resamples", type=int, default=10_000)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sessions, indicators = load_ai_export(args.ai_export)
    reference = load_human_reference(args.human_reference)
    outputs = analyze_experiment(
        sessions,
        indicators,
        reference,
        seed=args.seed,
        resamples=args.resamples,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.md").write_text(
        render_results_markdown(outputs),
        encoding="utf-8",
    )
    outputs.confusion_matrix.to_csv(args.output_dir / "confusion_matrix.csv", index=False)
    outputs.paired_deltas.to_csv(args.output_dir / "paired_deltas.csv", index=False)
    outputs.confidence_reliability.to_csv(
        args.output_dir / "confidence_reliability.csv",
        index=False,
    )
    print(json.dumps(outputs.summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
