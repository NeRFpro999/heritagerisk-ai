# Shared Competition Evidence

This directory contains reusable records for evidence submitted to the 2026
competitions. Templates start blank; durable logs may contain verified entries.
Recording an item here does not prove a claim by itself. Every claim must point
to inspectable evidence and be checked by the student.

## Files

- [Decision register](decision_register.md): records important project choices.
- [Contribution statement](contribution_statement.md): separates student, AI,
  adult, expert, library, and model contributions.
- [Feature status matrix](feature_status_matrix.csv): records implementation
  status and supporting tests or limitations.
- [AI assistance log](ai_assistance_log.csv): records each material AI-assisted
  interaction and the student's decisions and verification.
- [Ownership matrix](ownership_matrix.csv): records who conceived, designed,
  implemented, and verified each component.
- [Evidence index](evidence_index.md): indexes evidence without storing private
  source material in Git.
- [Claim register](claim_register.csv): checks proposed competition wording
  against available evidence.

## Controlled Values

Feature status must use one of:

- `VERIFIED WORKING`
- `PARTIAL`
- `MOCK OR DEMONSTRATION ONLY`
- `DOCUMENTED BUT UNVERIFIED`
- `PLANNED`
- `ABSENT`

Ownership status must use one of:

- `STUDENT_AUTHORED`
- `AI_ASSISTED`
- `AI_GENERATED_SUPPORT`
- `UNVERIFIED`

## Evidence Handling

Use anonymous evidence identifiers instead of contributor names, addresses,
coordinates, image filenames, or other personal data. Private source material,
raw images, detailed manifests, database copies, and raw model responses stay
outside Git. Record a hash and a controlled external location in the
[evidence index](evidence_index.md) when an artifact must be referenced.

The research staging rules are documented in
[research/README.md](../../research/README.md). The factual starting point is
[competition_baseline.md](../../competition_baseline.md).
