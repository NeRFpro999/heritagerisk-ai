# Research Evidence Staging

This tree is a blank staging area for later competition research. It contains
no participant records, images, annotations, predictions, experimental results,
or claims. Do not populate it until a protocol, privacy rules, and ownership
responsibilities have been approved.

## Directory Purposes

- `protocol/`: versioned research plans, methods, risk controls, and approvals.
- `manifests/`: private source manifests. Contents are ignored by Git.
- `annotations/`: private or licensed annotation data. Contents are ignored by
  Git.
- `prompts/`: redacted, versioned prompts with no personal or secret data.
- `schemas/`: versioned schemas for manifests, annotations, and model outputs.
- `raw_predictions/`: raw provider outputs. Contents are ignored by Git.
- `analysis/`: reproducible analysis code and safe, aggregate result tables.
- `figures/`: publication-ready figures containing no identifying source data.
- `logs/`: redacted experiment logs. The `logs/private/` path is ignored.

Generated datasets and research database files are also ignored. Existing
global ignore rules cover `.env` credential files. Do not weaken those rules.

## Privacy Boundary

Raw photos, contributor details, exact site addresses, GPS or EXIF metadata,
private manifests, database copies, credentials, and unredacted API responses
must stay outside Git in access-controlled storage. Do not use original names or
filenames as identifiers. Assign anonymous IDs such as `IMG-0001` only after the
identifier policy is approved, and keep the private ID mapping outside Git.

A safe derived artifact may be added to a versioned directory only after it is
redacted, checked for licensing and consent, and reviewed by Albert. Index it in
the [shared evidence index](../competition/shared/evidence_index.md), including
a hash and the controlled external location of any private source evidence.
