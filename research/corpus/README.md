# Research Corpus Metadata

This directory stores the versioned metadata contract and safe audit outputs for
the HeritageRisk research photo corpus.

Raw photographs are **not committed to Git**. They must stay in approved
access-controlled storage. Only these derived artifacts belong here:

- `MANIFEST.schema.json`: the schema for per-photo manifest records.
- `manifest.json`: generated local audit metadata with hashes and redacted
  grouping fields.
- `audit_report.md`: generated aggregate audit counts.
- Experiment manifests produced by `scripts/select_assets.py`, if they contain
  only relative paths and no private site details.

The manifest records hashes, dimensions, capture role (`WIDE`, `MEDIUM`, or
`CLOSE`), anonymous asset grouping, redacted site label, privacy clearance
status, cultural-sensitivity clearance status, and a short provenance note.

Newly discovered photos default to `needs_review` for privacy and cultural
sensitivity. A previous reviewed manifest can be supplied to preserve `cleared`,
`excluded`, or `sensitive` decisions across repeated audits. Do not manually mark
items `cleared` until consent, privacy, and cultural-sensitivity checks are
complete.

Typical local workflow:

```bash
python3 scripts/audit_corpus.py /path/to/private/photos
python3 scripts/select_assets.py research/corpus/manifest.json \
  --output research/corpus/experiment_manifest.json
```

The selected experiment manifest is intended for:

```bash
python3 scripts/run_experiment.py research/corpus/experiment_manifest.json --mock
```
