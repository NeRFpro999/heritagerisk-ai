# HeritageRisk AI — Research Log

Log of technical decisions, findings, and direction changes.
Most recent entry first.

Older entries record the state and decisions at their dates. Later entries and
`competition_baseline.md` supersede historical implementation claims.

---

## Entry #27 — 2026-07-24

### Exact Rendered-Request Fingerprints Without Raw Request Storage

Experiment prompt provenance now has two explicit boundaries.
`prompt_template_sha256` hashes the rendered system prompt, deployment, and
request settings, while `rendered_request_sha256` hashes the canonical
per-session Azure-shaped request including dynamic notes and image content. The
raw request is deliberately not stored. In mock mode the latter is a would-be
Azure request fingerprint; in Azure mode it covers the arguments constructed
for transmission.

`PROMPT_SETTINGS` and the session's `request_settings` now contain only values
actually passed to the client, currently `max_completion_tokens = 600`.
Temperature and schema version are absent rather than recorded as unsent
settings. The guarded SQLite compatibility migration renames legacy
`prompt_sha256` in place and adds the rendered-request column, leaving that
unreconstructable historical hash `NULL`. Tests cover both hash boundaries,
request-setting alignment, exports, and legacy migration. Experiment blinding
remains external and is not recorded.

---

## Entry #26 — 2026-07-24

### Native Repeated Assessment Sessions

`AssessmentSession` now has a zero-based `run_index` and is unique on
`(asset_id, condition, run_index)`. The SQLite startup helper transactionally
rebuilds only the legacy assessment-session table because SQLite cannot drop
its old two-column table constraint; existing rows and ids are preserved at
index 0. The migration is idempotent.

`scripts/run_experiment.py --repeat-runs N` creates indices `0` through `N - 1`
for both conditions with the same images, prompt hash, deployment, and settings
within the invocation. Resume checks include the run index. CSV exports carry
the index on session and indicator rows, and legacy exports default to index 0
when loaded.

Primary precision/recall/F1, paired-delta, insufficient-evidence, and confidence
metrics use run index 0 so repeats do not inflate the paired comparison.
Repeatability uses every exported run and includes empty indicator sets.
Synthetic mock tests cover two repeats producing four sessions for one asset,
a no-op resume, and hand-computed exact/Jaccard agreement. No real repeated
Azure experiment result is committed.

---

## Entry #25 — 2026-07-24

### Site Labels in Experiment Exports and Concentration Analysis

`ExperimentAsset` now stores the optional redacted `site_label` emitted by the
corpus asset selector. The experiment runner persists it without erasing an
existing label when a legacy manifest omits the field. The startup migration
adds the nullable column to existing SQLite experiment databases and leaves
historical labels unknown rather than reconstructing them.

Both session- and indicator-level CSV rows now include the asset label, and the
analysis loader keeps the optional field while remaining compatible with older
exports. Site concentration excludes blank labels and counts each physical
asset once across its paired sessions. Synthetic tests cover three assets across
two labels, a largest-site share of two-thirds, and the rendered non-NaN value.
No real site distribution or experiment result is committed.

---

## Entry #24 — 2026-07-24

### Direct Pilot and Held-Out Experiment Selection

`scripts/run_experiment.py` now accepts `--asset-set pilot|held_out|all`.
`pilot` remains the default and reads the existing `assets` list,
`held_out` reads `held_out_assets`, and `all` combines them. Every newly
created `AssessmentSession` stores the selected set in its settings JSON, so
exports can distinguish which split initiated the session. Resume behavior
keeps the original setting on existing sessions rather than relabelling them.

Synthetic mock-mode tests cover two pilot assets producing four paired sessions,
three held-out assets producing six, and all five assets producing ten. No real
held-out experiment result is committed.

---

## Entry #23 — 2026-07-24

### Preserved Azure Failure Attempts Before Mock Fallback

Added `AIAnalysisRecord` as an append-only application record for analysis
status, provider identity, sanitized diagnostic, and timestamp. Operational
Azure configuration, import, image-preparation, transport, API, and unexpected
provider failures now produce an ordered pair: a failed
`azure:<deployment>`/`azure:unconfigured` record followed by a separate
labelled `mock` result. Diagnostics are fixed categories and never contain
exception text, credentials, endpoints, response bodies, or file paths.

The AI review page shows the ordered attempts. Risk Case creation copies them
into the immutable snapshot, and both report formats render only that snapshot.
Malformed JSON and strict schema-validation failures remain one failed result
with no mock fallback. Attempt records preserve failure/outcome metadata, not
complete immutable revisions of every earlier proposal.

---

## Entry #22 — 2026-07-23

### Paired Experiment Statistical Analysis Functions

Added `research/analysis/` for pure metric calculations over paired experiment
exports and human reference labels. The package loads Task 7 AI export CSVs and
a documented human-reference CSV with `asset_id`, `indicator_type`, `present`,
and `reviewer_id`. It computes micro/macro precision, recall, F1, unsupported
claims, insufficient-evidence rate, paired per-asset recall/F1 deltas, Wilcoxon
signed-rank tests, effect size, seeded bootstrap confidence intervals,
confidence calibration, Cohen's kappa, and repeatability.

`scripts/analyze_experiment.py` writes `results.md`, `confusion_matrix.csv`,
`paired_deltas.csv`, and `confidence_reliability.csv`. The report states that
`n` is the number of physical assets and that photos of one asset are not
independent samples. Tests use a four-asset hand-computed toy fixture; no
real-corpus performance results or conclusions are committed.

---

## Entry #21 — 2026-07-23

### Corpus Manifest Audit and Asset Selection Tooling

Added `research/corpus/` as a metadata-only corpus audit area. It now defines
the per-photo manifest schema for anonymous photo ids, SHA-256 hashes, relative
paths, dimensions, capture role, asset group, redacted site label, privacy
status, cultural-sensitivity status, and provenance notes. Raw photographs
remain outside Git; common local raw-photo folders under `research/corpus/` are
ignored.

`scripts/audit_corpus.py` builds the manifest and audit report from a private
photo directory, detects duplicate hashes and files missing from a previous
manifest, preserves prior clearance decisions, and summarizes role/group
counts. `scripts/select_assets.py` selects only complete cleared
WIDE/MEDIUM/CLOSE groups and emits the experiment manifest consumed by
`scripts/run_experiment.py`, with a seeded pilot/held-out split. Synthetic tests
cover the behavior; no real corpus or 1,120-photo audit output is committed.

---

## Entry #20 — 2026-07-23

### Paired Single-Medium vs Three-View Experiment Sessions

Added a research-only data path for paired image-context experiments. One
`ExperimentAsset` represents a physical asset, and each `AssessmentSession`
stores one `single_medium` or `three_view` run with condition image ids,
structured analysis payload, schema/model/settings metadata, prompt SHA-256,
seeded run order, run timestamp, and operator.

The experiment runner keeps these sessions outside the public/community
workflow: they are not Observations, do not enter the review queue, and do not
create Risk Cases. The single-medium condition uses the same medium role image
id as the three-view condition, and resumable runs avoid duplicate
asset/condition sessions. Export now produces session-level rows and
per-indicator rows for later analysis. Mock-mode behavior is tested; live Azure
experiment results remain unverified until privacy-cleared assets and
credentials are used.

---

## Entry #19 — 2026-07-23

### AI Schema v2 Indicator Findings

Added a strict Pydantic `schema_version = "2"` AI response contract with
per-indicator findings, evidence locations, ObservationImage id references,
per-indicator confidence, supporting visible evidence, severity contribution,
and explicit evidence sufficiency. `insufficient` with zero indicators is a
valid outcome and can be finalized as no visible indicators confirmed.

Azure prompts now request the v2 JSON directly and state that the model must not
diagnose causes, hidden damage, structural safety, or safe/unsafe access. Invalid
indicator types, out-of-range values, malformed payloads, and image references
outside the Observation fail the whole result and preserve a sanitized raw
payload for audit. The app continues to render existing v1 aggregate rows.

---

## Entry #18 — 2026-07-23

### Manifest Demo Seeding and Live Azure Verification

Added `scripts/seed_demo.py` to rebuild a local demo SQLite database from
privacy-cleared files in ignored `demo_assets/`. The seed runs through the real
FastAPI routes with `TestClient`, so upload validation, CSRF, reviewer login,
review decisions, mock or Azure analysis, AI finalization, immutable snapshots,
reports, and status-transition events are exercised instead of raw inserts.

Added `scripts/verify_azure.py` for an opt-in live Azure check. It refuses to run
unless the required Azure environment variables are present and
`AZURE_OPENAI_ENABLED=true`. It sends one observation through the application
workflow, prints latency, deployment id, persisted structured result, and
validation status, and exits nonzero with the preserved app state if Azure falls
back to mock or validation fails. Automated tests cover mock seeding and the
missing-environment refusal path; they do not call live Azure.

This entry described the behavior at implementation time. Entry #23 supersedes
its failure-preservation limitation: operational Azure failures now retain a
sanitized failed-attempt record before the labelled mock fallback.

---

## Entry #17 — 2026-07-22

### Minimal Reviewer Access, CSRF, and Recorded Identity

Reviewer actions now require one credential supplied through
`REVIEWER_USERNAME` and a salted scrypt `REVIEWER_PASSWORD_HASH`. Successful
login creates an eight-hour Starlette signed session; logout clears it. A stable
`SESSION_SECRET_KEY` keeps sessions valid across restarts, while an omitted key
deliberately falls back to a process-ephemeral secret. Reviewer-led intake, the
review queue and decisions, analysis, AI-output review/finalization, case-status
updates, and browser seeding are guarded. Public multi-image submission remains
logged out by design and is still forced to `Pending`.

Every state-changing form POST, including login and public submission, now uses
a double-submit CSRF token. The submission reviewer is stored in
`Observation.reviewed_by`; the finalizer is stored in
`RiskCase.finalized_by`. Both identities are copied into the immutable case
snapshot and rendered by the case page and both report formats. The additive
SQLite migration leaves identity fields `NULL` for historical records rather
than inventing a reviewer.

The legacy `/sites/{site_id}/observations/new` and
`/sites/{site_id}/observations` routes and their single-image template were
removed. The compatibility `/observations/{id}/create_case` POST remains, but it
is authenticated, CSRF-protected, and writes the same finalizer identity and
snapshot as the primary route.

This is a competition-scale access boundary, not production identity
management. One shared credential cannot distinguish multiple people; there is
no role model, login throttling, password recovery, per-status updater identity,
or append-only action log. Local HTTP does not set the session cookie's `Secure`
flag. Uploaded media and read-only case/report routes remain public, and report
GET routes still regenerate files and update `report_path`.

---

## Entry #16 — 2026-07-22

### Content-Validated, Metadata-Free Image Storage

Both remaining image-intake paths use one shared upload helper. It keeps the
existing 10 MiB per-file limit and UUID filenames, but no longer trusts the
filename alone: `.jpg`/`.jpeg`, `.png`, and `.webp` uploads must have matching
JPEG, PNG, or RIFF/WEBP leading signatures and must decode successfully with
Pillow.

Before storage, the helper applies `ImageOps.exif_transpose` and rebuilds a fresh
pixel-only image for re-encoding in the validated format. This preserves the
intended visual orientation while omitting EXIF, GPS, XMP, embedded thumbnails,
and other source metadata. Any Azure request therefore uses the sanitized stored
file rather than the contributor's original bytes. Regression tests cover
suffix/signature mismatches, text masquerading as an image, synthetic GPS EXIF,
orientation preservation, and oversized files.

This is an upload-integrity and metadata-minimization control, not a complete
media-security or privacy boundary. Stored files remain available through the
public `/uploads` mount, and the app still has no malware scanner, aggregate
request limit, rate limit, consent workflow, retention policy, or verified live
Azure data-governance evidence.

---

## Entry #15 — 2026-07-22

### Three-Layer Evidence Provenance

Separated the evidence lifecycle into contributor original, AI proposal, and
reviewer-accepted final records. Every new Observation now writes
`contributor_original` once with notes, tags, severity, and submission time.
Reviewer edits continue to update the working Observation fields but cannot
change that original. Human accept/reject metadata moved into
`ai_review_decision`, so review actions no longer rewrite the AI raw response or
structured proposal fields.

Every new Risk Case now stores `final_snapshot`, including final tags/severity,
the per-tag weights used, multiplier, raw equation, cap result, score, band,
final reviewed wording, contributor original, AI proposal, and evidence image
references, plus site details used by case/report views. The case page and
Markdown/HTML reports use this snapshot rather than recalculating from the live
Observation. Later Observation edits therefore cannot make the displayed
breakdown disagree with the stored case score. Contributor-original note text
is limited to reviewer comparison pages so a privacy redaction is not reversed
by a case view or exported report.

The additive startup migration creates the three nullable JSON columns when
needed. Pre-provenance rows remain explicitly unavailable where their original
or final values cannot be reconstructed truthfully. The implementation is
covered by full-cycle, byte-identical AI proposal, post-case mutation, report,
and idempotent migration regressions.

---

## Entry #14 — 2026-07-22

### Audited Workflow Claims and SQLite Startup Migration

Aligned the project documentation with the verified July workflow. The public
submission and primary Risk Case routes contain the intended human review gates,
but legacy intake and case routes bypass parts of that flow. Original contributor
notes, tags, and severity are also not immutable, and sensitive upload URLs are
not access controlled. These limitations now link to `competition_baseline.md`
instead of being hidden by universal workflow claims.

Added a small idempotent SQLite startup migration for existing June databases.
It checks `PRAGMA table_info`, adds `human_review_status` only when missing,
marks only those pre-review legacy rows `ApprovedForAI`, and backfills legacy
single-image values into `ObservationImage` without duplication. The standalone
migration script now calls the same tested helper. The project still has no
general migration framework.

---

## Entry #13 — 2026-07-10

### Description Compliance and Evidence Separation

Audited the working app against the current HeritageRisk AI competition description and completed the missing workflow behavior.

Approved public observations now send every attached image plus reviewed site context to the analyzer. Applying AI output leaves the current human-reviewed tags and severity unchanged while suggestions are stored separately in the raw AI payload. The earlier submission-review step can overwrite original contributor values, so this is not an immutable original-evidence record. The provider now returns an explicit uncertainty statement.

The final reviewer can edit the summary and recommended next step, confirm final tags and severity, or reject the AI draft. Rejected drafts cannot create a Risk Case until rerun. Sensitive observations are hidden from general evidence views, browser submissions receive a Pending confirmation page, and case routing remains a manual recorded action.

Evidence reports now have a structured HTML view as well as Markdown, include the reviewed recommendation and limitations, and regenerate after status/routing changes. The current build remains a local single-reviewer demo; authentication and production public deployment are still out of scope.

---

## Entry #12 — 2026-07-09

### AI-Assisted Site Intake

Updated the internal Add Site flow so a reviewer can attach multiple photos during site creation and run AI analysis immediately.

When images are attached, the app creates the Site and an `ApprovedForAI` Observation, sends all uploaded image files plus site name, location, description, and optional intake notes to the analyzer, stores the AI output, and redirects to the AI review/finalization page.

This does not change the public submission queue: public observations still default to `Pending`, and the primary Risk Case route requires human finalization before reports are created or routed manually. The legacy case route remains a compatibility bypass.

---

## Entry #11 — 2026-07-09

### Dashboard System Overview

Updated the main dashboard to summarize the human-in-the-loop workflow at a glance.

The dashboard now reports total observations, observations awaiting human review, generated Risk Cases, high-priority cases, and a combined recent activity feed for observations and Risk Cases.

This makes the July workflow clearer for judges: public evidence enters a review queue, approved evidence can become AI-assisted analysis, and official Risk Cases are tracked separately from raw submissions.

---

## Entry #10 — 2026-07-09

### Judge-Ready Evidence Reports

Upgraded generated Markdown evidence reports for the final human-reviewed workflow.

Reports now embed all submitted images, show human review and AI audit trails, include the explainable rule-based risk equation, print final routing destination, and end with the required safety blockquote.

This keeps the report aligned with the human-in-the-loop claim: AI helps summarize visible evidence, but a human-reviewed rule-based score and routing decision are recorded before the Risk Case report is used.

---

## Entry #9 — 2026-07-08

### Explainable Risk Scoring Breakdown

Added an explainable scoring breakdown to Risk Case detail pages.

The scorer remains strictly rule-based: `sum(tag weights) × severity`, capped at 100. Risk bands are now documented and applied as Low `0-29`, Medium `30-59`, and High `60-100`, making the 60-point boundary clearly high priority.

The case page now shows finalized tags, weights, severity multiplier, equation, cap status, and band thresholds so judges can see that AI output does not decide the final risk score.

---

## Entry #8 — 2026-07-08

### AI Review Result and Case Finalization

Added a human review page between AI analysis and Risk Case creation.

`GET /observations/{obs_id}/ai_review` compares the current human-reviewed values with AI output, and `POST /observations/{obs_id}/create_risk_case` creates the Risk Case only after the reviewer confirms final tags, severity, and optional routing destination.

Risk Case creation now requires a completed or mock AI summary. The legacy `/observations/{obs_id}/create_case` route remains available for compatibility but uses the same AI-summary guard.

---

## Entry #7 — 2026-07-08

### Multi-Image Observation Display

Updated observation and site detail pages to display multi-image submissions.

Observation detail now shows a responsive image grid when an observation has more than one image. Site detail keeps the list compact by showing the first image as the thumbnail and adding a `+X more` badge for additional images.

No schema changes were made. This completes the UI display layer for the existing `ObservationImage` table while preserving the single-image MVP view.

---

## Entry #6 — 2026-07-08

### AI Analysis Human-Review Lock

Added a hard gate to `POST /observations/{obs_id}/analyze`.

AI analysis now runs only when `human_review_status` is `ApprovedForAI`. Pending, rejected, and sensitive observations return `403 Forbidden` before mock or Azure analysis can run.

Demo seed observations remain marked `ApprovedForAI`, so the seeded MVP demo cases continue to generate without bypassing safety status rules.

---

## Entry #5 — 2026-07-08

### Reviewer Gatekeeper Actions

Added reviewer action handling for observations before AI analysis.

`POST /observations/{observation_id}/review` lets a reviewer mark an observation as `ApprovedForAI`, `Rejected`, or `Sensitive` while overriding damage tags and severity. Public submissions remain hardcoded to `Pending` regardless of submitted form fields.

This makes the human review gate explicit before AI analysis and case creation. No schema changes were made.

---

## Entry #4 — 2026-07-08

### Observation Review Queue

Added a dedicated `/observations/review` page for human review triage.

The queue defaults to `Pending` public submissions and can filter observations by `Pending`, `ApprovedForAI`, `Rejected`, `Sensitive`, or all statuses. It shows site context, image count, notes, tags, severity, submission age, and links to inspect the observation or site.

No schema changes were made. This keeps the existing single-observation MVP pipeline working while making the planned human review step visible before AI analysis and risk-case creation.

---

## Entry #3 — 2026-07-03

### Public Multi-Image Submission Route

Added the backend model and route path for public multi-image observation submission.

`Observation` now has `human_review_status`, `ObservationImage` stores one or more uploaded image URLs, and `POST /observations/submit` creates a pending human-review observation from multipart form data.

The old single-image MVP upload route still works, but it now writes its uploaded file as the first `ObservationImage` instead of relying on a single image column. Existing observation/detail/report pages read the first linked image as the primary display image.

New public submissions are marked `Pending`. Existing internal/demo observations are marked `ApprovedForAI` so they preserve the current MVP flow.

---

## Entry #2 — 2026-07-03

### Multi-Image Migration Script

Added `scripts/migrate_multi_image_schema.py` as a raw SQLite migration helper for the planned multi-image observation schema.

The script creates `observation_images`, backfills existing single-image values from `observations.image_path` or the current `observations.image_filen