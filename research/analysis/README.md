# Paired Experiment Analysis

This package analyzes Task 7 experiment exports against human reference labels.
It treats the physical asset as the sample unit. Photos from one asset are never
counted as independent samples.

## Inputs

AI results come from:

```bash
python3 scripts/export_results.py --db-path data/experiment.db --output research/analysis/ai_export.csv
```

Human reference labels are a CSV with these columns:

| column | meaning |
|---|---|
| `asset_id` | Physical asset id matching `external_asset_id` in the AI export. |
| `indicator_type` | Damage indicator/tag being judged. |
| `present` | `true`, `false`, or `uncertain`. |
| `reviewer_id` | Anonymous reviewer id. Two reviewers may label a blinded subset. |

`uncertain` labels are included in inter-rater agreement, but are not treated as
positive reference indicators for precision/recall/F1.

## Command

```bash
python3 scripts/analyze_experiment.py \
  --ai-export research/analysis/ai_export.csv \
  --human-reference research/analysis/human_reference.csv \
  --output-dir research/analysis/outputs
```

Outputs:

- `results.md`
- `confusion_matrix.csv`
- `paired_deltas.csv`
- `confidence_reliability.csv`

The default bootstrap setting is 10,000 seeded resamples.
