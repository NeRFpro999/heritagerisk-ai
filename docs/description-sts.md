# HeritageRisk AI — STS Experiment Description

A fresh Python 3.12 audit on 24 July 2026 verified `220 passed, 538 warnings`
with `cd backend && AZURE_OPENAI_ENABLED=false pytest -q`; elapsed time varies
by host and load.

## Implemented Experiment Framing

The implemented research tooling supports a paired comparison of AI analysis
conditions on the same physical asset:

- `single_medium`: analysis of the medium-distance photo only.
- `three_view`: analysis of the wide, medium, and close photos together.

The data model keeps experiment sessions separate from the community/demo
workflow. `ExperimentAsset` represents one physical asset, and
`AssessmentSession` stores one condition run with image ids, structured result
payload, schema version, model deployment, run settings, run order, operator,
and a SHA-256 hash of the system prompt, model deployment, and configured prompt
settings. Dynamic notes and image-id user content are not included, so this is
not proof that the exact rendered request was frozen.

The experiment runner accepts a CSV or JSON manifest with:

```text
asset_id, wide_path, medium_path, close_path
```

It creates both conditions per asset in seeded randomized order. The
`single_medium` condition uses the identical medium image id as the `three_view`
condition. The runner writes incrementally and can resume without duplicating
existing asset/condition sessions. `--mock` is the tested offline mode; `--azure`
is opt-in and requires live credentials.

## Corpus Metadata Tooling

`research/corpus/` contains a manifest schema and metadata-only workflow for a
private photo corpus. Raw photographs are not committed.

`scripts/audit_corpus.py` can scan a private photo directory, compute SHA-256
hashes, read dimensions, detect duplicate hashes, detect files missing since a
previous manifest, preserve previous privacy/cultural-sensitivity statuses, and
summarize counts by role and asset group.

`scripts/select_assets.py` keeps only complete WIDE/MEDIUM/CLOSE asset groups
whose privacy status and cultural-sensitivity status are both `cleared`, then
writes a seeded pilot of up to six eligible assets and a held-out list. To run
the held-out list, it must first be copied or transformed into a separate
manifest's `assets` array because `scripts/run_experiment.py` does not read
`held_out_assets`.

## Analysis Code

`research/analysis/` contains pure analysis functions and a CLI for exported AI
results and human reference labels.

The human reference CSV format is:

```text
asset_id, indicator_type, present, reviewer_id
```

`present` is `true`, `false`, or `uncertain`. The CSV supports overlapping
labels from two reviewer ids for inter-rater agreement; blinding is managed
outside the software and is not recorded.

Implemented metrics:

- Indicator-level precision, recall, and F1, micro and macro, per condition.
- False-positive and missed-indicator counts.
- Unsupported-claim rate.
- Insufficient-evidence rate per condition.
- Paired per-asset recall and F1 deltas: `three_view - single_medium`.
- Wilcoxon signed-rank test, effect size, and seeded bootstrap 95% confidence
  intervals.
- Confidence-vs-correctness means and reliability tables by confidence bin.
- Cohen's kappa for the double-labelled subset.
- A standalone repeatability metric for repeated-session rows. The current
  experiment runner and database uniqueness constraint do not create repeated
  asset/condition sessions.

The output files are `results.md`, `confusion_matrix.csv`, `paired_deltas.csv`,
and `confidence_reliability.csv`. The report explicitly states that `n` is the
number of physical assets. Photos of one asset are never treated as independent
samples.

## Current Evidence

Automated tests use synthetic images and hand-computed toy data. They verify the
corpus audit behavior, asset selection behavior, paired experiment session
creation/resume behavior, and analysis metrics including F1, Cohen's kappa,
paired deltas, confidence calibration, and repeatability.

## Limitations

No real 1,120-photo corpus manifest is committed. No raw photos are committed.
No human reference labels for a real corpus are committed. No live Azure
experiment output is committed. No statistical conclusion about model
performance is currently supported by repository evidence.

The Azure path is implemented and mock-tested, but the current re-audit did not
call live Azure. The risk score used in the product workflow remains a heuristic
and is not part of a validated scientific outcome model.

## Planned, Not Implemented

- Privacy-cleared real corpus manifest and audit report for the claimed corpus.
- Human reference labels from qualified or defined raters.
- Completed live Azure paired runs.
- Final precision/recall/F1, effect-size, confidence-calibration, repeatability,
  and inter-rater agreement results on the real corpus.
- Provider comparison conclusions, YOLO model work, labelled-dataset release,
  and uncertainty-aware evidence fusion.
