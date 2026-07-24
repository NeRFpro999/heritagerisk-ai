# HeritageRisk AI — STS Experiment Description

A fresh Python 3.12 audit on 25 July 2026 verified
`232 passed, 579 warnings`; elapsed time varies by host and load.

## Implemented Experiment Framing

The implemented research tooling supports a paired comparison of AI analysis
conditions on the same physical asset:

- `single_medium`: analysis of the medium-distance photo only.
- `three_view`: analysis of the wide, medium, and close photos together.

The data model keeps experiment sessions separate from the community/demo
workflow. `ExperimentAsset` represents one physical asset, and
stores its optional redacted `site_label`.
`AssessmentSession` stores one condition run with image ids, structured result
payload, zero-based `run_index`, schema version, model deployment, run settings,
run order, operator, and two SHA-256 values. `prompt_template_sha256` covers the
rendered system prompt, deployment, and request settings.
`rendered_request_sha256` covers the canonical fully rendered per-session
Azure-shaped request, including dynamic notes and image content. The raw request
is not stored. In Azure mode the second hash covers the arguments built for
transmission; in mock mode it is only the fingerprint of the request that would
have been built for Azure. Legacy sessions retain their earlier
`prompt_sha256` value under the renamed template field without recomputation and
show the rendered-request hash as unavailable (`NULL`).

The experiment runner accepts a CSV or JSON manifest with:

```text
asset_id, wide_path, medium_path, close_path, site_label (optional)
```

It creates both conditions per asset in seeded randomized order. The
`single_medium` condition uses the identical medium image id as the `three_view`
condition. `--repeat-runs N` repeats each selected asset/condition under indices
`0` through `N - 1`; the default is one run at index 0. Repeats use the same
images, template hash, model deployment, and request settings within an
invocation, while each condition retains its own rendered-request hash. The
runner writes incrementally and resumes on
`(asset_id, condition, run_index)` without duplicating completed runs. For a
split JSON manifest, `--asset-set pilot` is the default, `--asset-set held_out`
runs the held-out rows, and `--asset-set all` combines both lists. The selected
set is stored in every new session's settings. The recorded `request_settings`
match the request-builder arguments: currently `max_completion_tokens = 600`.
No temperature or schema-version value is recorded there because neither is
passed as a generation setting. `--mock` is the tested offline mode; `--azure`
is opt-in and requires live credentials.

Experiment result JSON includes ordered analysis-attempt metadata. An
operational Azure failure is represented as a failed Azure attempt followed by
the labelled mock result; this preserves the failure without treating it as a
successful Azure output.

## Corpus Metadata Tooling

`research/corpus/` contains a manifest schema and metadata-only workflow for a
private photo corpus. Raw photographs are not committed.

`scripts/audit_corpus.py` can scan a private photo directory, compute SHA-256
hashes, read dimensions, detect duplicate hashes, detect files missing since a
previous manifest, preserve previous privacy/cultural-sensitivity statuses, and
summarize counts by role and asset group.

`scripts/select_assets.py` selects complete cleared groups, writes a seeded
pilot of up to six eligible assets, and writes a held-out list.
`scripts/run_experiment.py` consumes either split directly through
`--asset-set`, or both through `--asset-set all`.

## Analysis Code

`research/analysis/` contains pure analysis functions and a CLI for exported AI
results and human reference labels.

The human reference CSV format is:

```text
asset_id, indicator_type, present, reviewer_id
```

`present` is `true`, `false`, or `uncertain`. The CSV supports overlapping
labels from two reviewer IDs for inter-rater agreement; blinding is managed
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
- Exact and per-indicator repeatability across native repeated sessions,
  including runs that return no indicators.

The output files are `results.md`, `confusion_matrix.csv`, `paired_deltas.csv`,
and `confidence_reliability.csv`. The report explicitly states that `n` is the
number of physical assets. Photos of one asset are never treated as independent
samples. Primary condition metrics use `run_index = 0`, while repeatability uses
all exported runs so repeats do not inflate precision/recall/F1 or confidence
statistics. Session- and indicator-level export rows retain `run_index` and the
optional `site_label`; the loader carries both into analysis, where `results.md`
reports site counts and the largest-site asset share after counting each
labelled physical asset once.

## Current Evidence

Automated tests use synthetic images and hand-computed toy data. They verify the
corpus audit behavior, asset selection behavior, paired experiment session
creation/resume behavior, pilot/held-out/all selection and stored set metadata,
two native repeats per condition with resume safety, site-label persistence and
both export row types, distinct template/rendered request hashes, request
settings restricted to Azure-transmitted arguments, legacy rendered-hash
`NULL` migration, and analysis metrics including F1, Cohen's kappa, paired
deltas, confidence calibration, and hand-computed repeatability. A three-asset
fixture across two sites verifies the concentration counts and a non-NaN
largest-site share in `results.md`.

## Limitations

No real 1,120-photo corpus manifest is committed. No raw photos are committed.
No human reference labels for a real corpus are committed. No live Azure
experiment output is committed. No statistical conclusion about model
performance is currently supported by repository evidence.

The Azure path is implemented and mock-tested, but the current re-audit did not
call live Azure. Rendered request hashes are fingerprints, not stored copies of
the request, and blinding remains external and unrecorded. The risk score used
in the product workflow remains a heuristic and is not part of a validated
scientific outcome model.

## Planned, Not Implemented

- Privacy-cleared real corpus manifest and audit report for the claimed corpus.
- Human reference labels from qualified or defined raters.
- Completed live Azure paired runs.
- Final precision/recall/F1, effect-size, confidence-calibration, repeatability,
  and inter-rater agreement results on the real corpus.
- Provider comparison conclusions, YOLO model work, labelled-dataset release,
  and uncertainty-aware evidence fusion.
