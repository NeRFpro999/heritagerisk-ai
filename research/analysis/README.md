# Paired Experiment Analysis

This package analyzes Task 7 experiment exports against human reference labels.
It treats the physical asset as the sample unit. Photos from one asset are never
counted as independent samples.

## Inputs

AI results come from:

```bash
python3 scripts/export_results.py --db-path data/experiment.db --output research/analysis/ai_export.csv
```

Each session- and indicator-level export row includes its zero-based
`run_index` and the nullable redacted `site_label` stored on its physical
`ExperimentAsset`. Older exports without either column remain loadable,
defaulting to run index 0 and reporting site concentration as unavailable.
Rows also carry `prompt_template_sha256` and `rendered_request_sha256`. The
first identifies the rendered system prompt, deployment, and request settings;
the second identifies the canonical per-session Azure-shaped request, including
dynamic notes and image content, without storing that raw request. A mock row's
second hash describes a would-be request rather than a transmission. Migrated
legacy database rows keep their earlier prompt hash under the renamed template
field without recomputation and export an empty rendered-request hash because
that value cannot be reconstructed.

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
Site counts and largest-site share use one row per labelled physical asset, not
one row per photo, condition, session, or indicator.

Primary condition metrics use `run_index = 0`. The repeatability table uses all
exported runs for each asset/condition and treats an exported session with zero
indicators as an empty indicator set.
