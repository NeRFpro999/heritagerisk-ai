# HeritageRisk AI Description Alignment Audit

Audit date: 2026-07-24 (Australia/Melbourne)  
Audited state: pre-commit working tree based on commit `9c85291`  
Audit mode: independent, read-only verification; no live Azure request

This report preserves the descriptions and repository state as they existed
during the audit. The descriptions were corrected and the implementation was
committed afterward; current status belongs in `competition_baseline.md`.

## Scope and interpretation

The supplied audit brief contained placeholders rather than pasted description
text. This audit therefore treats the repository files
`docs/description-yicte.md` and `docs/description-sts.md` as Input A and Input B.
They are the only files in the working tree named as the two competition
descriptions.

Claims are extracted at sentence or list-item level. A compound list item stays
one claim where its components describe one pipeline, schema, metric family, or
declared set of absent controls. Independent clauses with different evidence or
verdicts are separated.

Verdicts use the requested meanings:

- **TRUE** — verified in current code and/or observed offline behavior.
- **FALSE** — contradicted by current code or observed behavior.
- **PARTIAL** — a material part is true, but the unqualified claim has a false
  or unsupported part.
- **UNVERIFIED** — the repository and permitted checks cannot establish it.
- **TRUE-IN-CODE-ONLY** — apparatus exists and is mock-tested, but the live or
  real-data activity described has not been performed or evidenced here.

## Evidence register

The verdict tables cite these evidence records. Documentation, comments, and
commit messages were not used as proof.

### E01 — Fresh Python 3.12 environment and complete test suite

Commands actually run:

```text
python3.12 -m venv /tmp/heritagerisk-audit-venv
/tmp/heritagerisk-audit-venv/bin/pip install \
  -r backend/requirements.txt -r requirements-research.txt
cd backend
AZURE_OPENAI_ENABLED=false /tmp/heritagerisk-audit-venv/bin/pytest -q
```

Exact final summary:

```text
220 passed, 538 warnings in 742.00s (0:12:21)
```

The claimed passing-test count and warning count match. The claimed historical
elapsed time, `173.13s`, was not reproduced and is not a stable software
property.

### E02 — Real HTTP workflow against isolated SQLite

The app was started with Uvicorn on `127.0.0.1`, with the database, uploads, and
reports all under `/tmp`; Azure was explicitly disabled. Real HTTP requests
produced the following sequence:

```text
public submission:                 200, Pending, 2 images
analysis before approval:          403
review approval:                   303
mock analysis:                     303
reviewer finalization:             303, Risk Case created
post-case Observation edit:        303
case page after edit:              retained final label/equation/score
Markdown report after edit:        byte-identical to pre-edit report
```

The database showed contributor original
`notes="CONTRIBUTOR ORIGINAL NOTE", tags=["crack"], severity=2`; reviewed working
values `graffiti`, severity 3; AI proposal `graffiti`, provider/status `mock`;
and final snapshot `vegetation_growth`, severity 5, equation
`(4) × Severity 5 = 20`, score 20, band Low. After changing the live Observation
to `corrosion`, severity 1, both `contributor_original` and `ai_raw_response`
were byte-identical, the RiskCase row was identical, and neither case nor report
showed the mutated tag.

Relevant implementation:
`backend/app/main.py:363-435,952-1061,1108-1506,1537-1694`;
`backend/app/provenance.py:17-51,83-179,182-297`;
`backend/app/reports.py:147-402`.

Named tests in E01 include
`test_contributor_original_survives_full_review_finalize_cycle`,
`test_reviewer_edits_leave_ai_proposal_byte_identical`, and
`test_post_case_observation_edit_cannot_change_case_or_reports`.

### E03 — Upload content and metadata checks over HTTP

Observed against the real temporary server:

```text
text bytes named fake.png:         400, invalid image message
PNG bytes named renamed.jpg:       400, extension/content mismatch message
JPEG containing synthetic GPS:     200; stored EXIF count 0; no GPS IFD
40×20 JPEG with EXIF orientation 6: 200; stored size 20×40; EXIF count 0
```

The shared implementation is at
`backend/app/main.py:63-71,104-214,831-855,952-997`. All cases in
`backend/tests/test_upload_security.py` passed in E01, including the 10 MiB
limit and public/reviewer upload-path parameterization.

### E04 — Authentication, sessions, CSRF, and unauthenticated route probes

The signed eight-hour session and double-submit CSRF implementation is at
`backend/app/auth.py:20-31,87-157,190-258` and
`backend/app/main.py:79-88,656-711`.

Without a session, real HTTP requests to reviewer-led intake, review queue,
review form, review decision, analysis trigger, AI review, both case-creation
posts, AI rejection, case-status form/update, browser seed, and logout all
returned `303` to `/reviewer/login...`. After login, a state-changing form
without a CSRF field returned:

```json
{"status": 403, "detail": "Invalid or missing CSRF token."}
```

The focused auth probes also passed:

```text
15 passed, 15 warnings in 22.11s
```

Named tests include `test_guarded_get_routes_redirect_logged_out`,
`test_guarded_post_routes_redirect_logged_out`,
`test_logged_out_analysis_never_invokes_analyzer`, and
`test_authenticated_form_without_csrf_is_rejected`.

### E05 — Status transitions and event history

Real HTTP results:

```text
Draft → Routed:                   400; allowed next state listed
Draft → Needs Review:             303
Needs Review → Verified:          303
Verified → Routed, no destination:400
```

SQLite then contained exactly two CaseEvent rows with the reviewer identity and
notes. Both notes rendered in the case page and Markdown report.

Implementation:
`backend/app/case_status.py:3-24`;
`backend/app/main.py:1537-1640`;
`backend/app/models.py:138-188`;
`backend/app/reports.py:92-114,343-352`.
All tests in `backend/tests/test_case_status_transitions.py` passed in E01.

### E06 — AI failure semantics without contacting Azure

A second temporary server enabled the Azure path but pointed it only at the
closed local address `http://127.0.0.1:9`, with clearly fake credentials. No
external or live Azure endpoint was contacted. The forced connection failure
stored:

```json
{
  "stored_status": "mock",
  "stored_provider": "mock",
  "stored_payload_provider": "mock",
  "stored_schema_version": "2",
  "summary_is_explicit_mock": true,
  "stored_has_failure_diagnostic": false
}
```

Thus transport/configuration failures never fabricate Azure success and the
fallback is labelled mock, but the failed Azure attempt itself is not
preserved. By contrast, malformed response/schema failures are stored as
`failed` with sanitized raw payload.

Code:
`backend/app/services/ai_analysis.py:48-225`;
`backend/app/services/providers/azure_openai_provider.py:155-224,226-333`;
`backend/app/main.py:452-556`.
Named passing tests include
`TestProviderValidation::test_azure_api_exception_uses_mock`,
`TestResponseValidation::test_bad_json_string_returns_failed_validation_result`,
and `test_invalid_indicator_type_becomes_failed_state_with_raw_payload`.

The mock implementation at `backend/app/services/ai_analysis.py:48-164` scans
notes and tests only whether the path exists; it does not read or decode image
pixels.

### E07 — Product data model, scoring, and reports

Relevant code:

- Observation/ObservationImage/RiskCase/CaseEvent:
  `backend/app/models.py:41-188`.
- Scoring weights, equation, cap, and bands:
  `backend/app/risk.py:8-107`.
- Snapshot construction/read without live Observation fallback:
  `backend/app/provenance.py:83-297`.
- Snapshot-only report rendering:
  `backend/app/reports.py:147-402`.
- Snapshot-only case template:
  `backend/app/templates/case_detail.html:6-125,175-267`.

Named passing tests include all tests in `backend/tests/test_provenance.py`,
`backend/tests/test_reports.py`, and `backend/tests/test_risk.py`.

`RiskCase.final_snapshot` is nevertheless a nullable ordinary JSON column
(`backend/app/models.py:151-155`), with no database constraint or event
preventing direct replacement. Image evidence in it consists of mutable URL
references, not content hashes or embedded bytes.

### E08 — Schema-v2 proposal and review controls

Strict schema and image-reference validation:
`backend/app/ai_schema.py:13-86`.
Azure prompt and validation:
`backend/app/services/providers/azure_openai_provider.py:43-86,155-224,312-333`.
Storage behavior:
`backend/app/main.py:452-556`.
Comparison and indicator controls:
`backend/app/templates/review_action.html:20-118`;
`backend/app/templates/ai_review_result.html:20-292`.

All tests in `backend/tests/test_ai_schema_v2.py` passed in E01. The primary UI
offers accept/edit/reject controls. However, the compatibility finalizer
`POST /observations/{id}/create_case` synthesizes a decision without explicit
per-indicator choices (`backend/app/main.py:1469-1506`), and the primary POST's
indicator arrays are optional (`backend/app/main.py:1344-1405`).

### E09 — Sensitive/public boundary and absent production controls

The static upload mount is public:
`backend/app/main.py:90-91`. Observation, case, and report read routes have no
reviewer dependency:
`backend/app/main.py:1239-1262,1509-1558,1643-1694`.
The session cookie is configured with `https_only=False`:
`backend/app/main.py:79-87`.
There is one configured reviewer credential:
`backend/app/config.py:37-45`;
`backend/app/auth.py:112-146`.

Sensitive evidence redaction is implemented in
`backend/app/templates/observation_detail.html:13-24,64-65`,
`backend/app/templates/site_detail.html:96-155`, and
`backend/app/templates/index.html:223-250`;
`test_sensitive_observation_is_hidden_from_general_views` passed. The
Observation record, identifier, status, site, and link can still remain visible,
so the record itself is not wholly hidden.

Route/model/dependency searches found no accounts, roles, recovery, throttling,
malware scanner, retention worker, backup system, monitoring integration, or
HTTPS deployment configuration.

### E10 — Paired experiment dry-run

Focused offline suites actually run:

```text
7 passed in 113.37s (0:01:53)
26 passed in 151.08s (0:02:31)
```

The first line covers `test_experiment_scripts.py`,
`test_research_analysis.py`, and `test_corpus_scripts.py`; the second covers
`test_ai.py`, entirely with mock clients.

An independent one-asset mock run under `/tmp` produced:

```json
{
  "assets": 1,
  "sessions": 2,
  "created_sessions": 2,
  "seed": 314159,
  "mode": "mock",
  "prompt_sha256": "ce0ae2cc4a26407e8cc8ef9257d85e52c078b54f5ce14abe315685d50c9ecf1a"
}
```

Stored conditions were `three_view`, order 1, IDs `[101,102,103]`, and
`single_medium`, order 2, IDs `[102]`. Both stored schema 2, mock
provider/status/deployment, seed/settings/operator, and the same hash. Rerun:
`created_sessions=0`, `skipped_sessions=2`. Export: 2 session rows, 4 indicator
rows, 6 total. SQLite contained zero Observations and zero RiskCases.

Code:
`backend/app/models.py:19-21,191-244`;
`scripts/run_experiment.py:35-86,136-255`;
`scripts/export_results.py:20-128`.

### E11 — Prompt-hash boundary

`analysis_prompt_sha256()` hashes `_SYSTEM_PROMPT`, `PROMPT_SETTINGS`, and
deployment (`backend/app/services/providers/azure_openai_provider.py:88-110`).
It does not hash the dynamically rendered notes/image-id content generated at
lines 113-121 and sent at lines 290-305. `temperature: None` is included in the
hash but is not passed in the actual request call. The stored hash therefore
does not prove the exact rendered request prompt and settings.

### E12 — Corpus fixture dry-run

The independent temporary corpus produced:

```text
photos: 8
roles WIDE/MEDIUM/CLOSE: 3/3/2
complete groups: 2
candidate incomplete groups: 1
excluded items: 3
duplicate-hash groups: 1
missing prior files: 1
selected complete cleared groups: 1
split seed: 2718
```

The previous private status was preserved, expected dimensions/hashes were
written, and the report contained the counts. The focused tests
`test_audit_corpus_hashes_duplicates_groups_and_missing_files` and
`test_select_assets_excludes_uncleared_and_splits_deterministically` passed.

Code:
`scripts/audit_corpus.py:30-35,92-239`;
`scripts/select_assets.py:33-106`.

The selector default is six but stores
`pilot_size=min(pilot_size, eligible_count)` (`scripts/select_assets.py:89-101`).
It writes `held_out_assets`, while the runner reads only `payload["assets"]`
(`scripts/run_experiment.py:42-43`); a temporary pilot-plus-held-out manifest
loaded only the pilot.

### E13 — Analysis functions and outputs

Code:
`research/analysis/metrics.py:31-460`;
`research/analysis/reporting.py:10-83`;
`scripts/analyze_experiment.py:20-53`.

The hand-computed tests
`test_condition_metrics_match_hand_computed_values`,
`test_paired_delta_kappa_confidence_and_repeatability_known_answers`, and
`test_loaders_and_report_outputs` passed. The independent CLI run created
`results.md`, `confusion_matrix.csv`, `paired_deltas.csv`, and
`confidence_reliability.csv`, and stated `n = 1 physical assets`.

Reviewer IDs and overlapping labels are accepted, but there is no assignment or
blinding mechanism. `repeatability()` accepts repeated session rows
(`research/analysis/metrics.py:384-413`), but the schema enforces unique
`(asset_id, condition)` and the runner skips an existing pair
(`backend/app/models.py:208-212`;
`scripts/run_experiment.py:197-207`). A duplicate insertion failed with SQLite
constraint error 19.

The normal export has no `site_label` field
(`scripts/export_results.py:20-44`), so `site_concentration()` receives no site
labels and returns `{}` / `NaN`
(`research/analysis/metrics.py:416-420`).

### E14 — Repository evidence inventory

`git ls-files` and filesystem inspection found no committed raw corpus photos,
real 1,120-photo manifest, real human-reference CSV, live-Azure experiment
export, results file, model-performance conclusion, YOLO model, or released
labelled dataset. `research/corpus/` currently contains only
`MANIFEST.schema.json` and `README.md`. No live Azure command was run in this
audit.

### E15 — Baseline history

Command:

```text
git log --follow --format='%h %ad %s' --date=iso -- competition_baseline.md
```

Output:

```text
9c85291 2026-07-22 19:20:13 +1000 docs(competition): add evidence and research scaffolding
```

At audit time, the baseline explicitly labelled resolutions `WT@9c85291`; that
notation meant the uncommitted working tree, not a commit containing the
resolution.
`git show 9c85291:backend/app/main.py` still has the unauthenticated legacy
single-image routes and lacks the current auth, provenance, CaseEvent, and
experiment implementation. The corresponding audited working-tree code was
identifiable, but no resolution had a new commit reference at that time.

## Claim verdicts — YICTE description

| # | Claim text (verbatim) | Source | Verdict | Evidence |
|---|---|---|---|---|
| Y01 | “Current verification: `220 passed, 538 warnings in 173.13s (0:02:53)` from `cd backend && AZURE_OPENAI_ENABLED=false pytest -q`.” | YICTE | PARTIAL | E01: 220/538 match; fresh elapsed time was 742.00s. |
| Y02 | “HeritageRisk AI is a local web app for visible heritage-site risk triage.” | YICTE | TRUE | E02; FastAPI entry at `backend/app/main.py:79-93`. |
| Y03 | “It is built with FastAPI, SQLAlchemy, SQLite, Jinja2, vanilla CSS, Pillow, and pytest.” | YICTE | TRUE | E01; imports/dependencies at `backend/app/main.py:8-14`, `backend/requirements.txt:1-11`. |
| Y04 | “It is designed as a student competition prototype, not as a production public service.” | YICTE | TRUE | E09 verifies local/demo controls and missing production controls. |
| Y05 | “A public contributor submits one to six photos, notes, visible-damage tags, and severity.” | YICTE | TRUE | E02; limits and fields at `backend/app/main.py:952-1031`; public submission limit tests passed. |
| Y06 | “Public submissions enter the human review queue as `Pending`.” | YICTE | TRUE | E02; `backend/app/main.py:1008-1018`; `test_public_submission_works_logged_out_and_stays_pending`. |
| Y07 | “Every uploaded JPEG, PNG, or WEBP file is checked by file signature and size, decoded with Pillow, orientation-corrected, and re-encoded without EXIF/GPS metadata before storage.” | YICTE | TRUE | E03, including runtime GPS/orientation inspection and all upload-security tests. |
| Y08 | “An authenticated reviewer signs in with the configured reviewer credential, opens the review queue, and approves, rejects, or marks submissions sensitive.” | YICTE | TRUE | E04; routes at `backend/app/main.py:656-692,1108-1236`. |
| Y09 | “Approved observations can be analyzed by mock AI by default” | YICTE | TRUE | E02/E06; `backend/app/services/ai_analysis.py:177-225`. |
| Y10 | “or Azure OpenAI when explicitly enabled and configured.” | YICTE | TRUE-IN-CODE-ONLY | E06/E08; mocked Azure request tests pass, but no live Azure run was made. |
| Y11 | “The AI proposal uses schema v2 for per-indicator evidence, image references, confidence, and evidence sufficiency.” | YICTE | TRUE | E08; all schema-v2 tests passed. |
| Y12 | “Invalid Azure v2 payloads are preserved as failed validation states rather than being treated as successful results.” | YICTE | TRUE | E06/E08; failed payload preservation tests passed. |
| Y13 | “A reviewer compares contributor-original, current reviewed, and AI-proposed values” | YICTE | TRUE | E08; comparison template lines and `test_ai_review_page_shows_original_current_and_ai_values`. |
| Y14 | “then accepts, edits, or rejects the AI proposal.” | YICTE | PARTIAL | E08: UI supports all three; compatibility/crafted POST paths do not require explicit per-indicator decisions. |
| Y15 | “Finalized Risk Cases store an immutable evidence and scoring snapshot.” | YICTE | PARTIAL | E02/E07: application views are stable, but JSON and image URLs have no DB/content immutability guarantee. |
| Y16 | “Case pages and Markdown/HTML reports render from that snapshot so later edits to the live Observation do not change the displayed final score breakdown.” | YICTE | TRUE | E02/E07; runtime and provenance regression test verified invariance. |
| Y17 | “Case statuses follow enforced transitions: Draft → Needs Review; Needs Review → Verified or Draft; Verified → Routed or Needs Review; Routed → Closed.” | YICTE | PARTIAL | E05: reviewer status route enforces the graph; `/seed` inserts later statuses directly without transition events (`backend/app/seed.py:184-284`). |
| Y18 | “`Routed` requires a destination, and accepted transitions create `CaseEvent` history rows.” | YICTE | TRUE | E05; observed two events and missing-destination rejection. |
| Y19 | “Multi-image submissions are represented by `ObservationImage` rows.” | YICTE | TRUE | E02/E07; `backend/app/models.py:120-135`. |
| Y20 | “The legacy single-image site upload route and template were removed.” | YICTE | TRUE | E04 route inventory; neither legacy route exists and `observation_new.html` is absent. |
| Y21 | “Reviewer actions use signed sessions and CSRF-protected forms.” | YICTE | TRUE | E04; real missing-token request returned 403. |
| Y22 | “Public submission remains unauthenticated by design.” | YICTE | TRUE | E02/E04; logged-out public submission succeeded. |
| Y23 | “Reviewer and finalizer identities are recorded as the configured reviewer identity, copied into the Risk Case snapshot, and rendered in case/report views.” | YICTE | TRUE | E02/E07; `test_reviewer_identity_is_persisted_and_rendered`. |
| Y24 | “Mock analysis remains available offline and is always labelled `mock`.” | YICTE | TRUE | E02/E06; runtime DB stored both status/provider as mock. |
| Y25 | “Generated reports include the required visible-risk triage safety statement.” | YICTE | TRUE | `backend/app/reports.py:15-24,364-397`; report safety tests passed in E01. |
| Y26 | “The app does not provide production security.” | YICTE | TRUE | E09. |
| Y27 | “It has one shared reviewer credential, not individual accounts or roles.” | YICTE | TRUE | E09; `backend/app/config.py:37-45`, `backend/app/auth.py:112-146`. |
| Y28 | “There is no login throttling, password recovery, HTTPS deployment, private media delivery, malware scanning, retention policy, or backup/recovery process.” | YICTE | TRUE for repository implementation | E09; route/model/dependency inventory found none of the listed controls. |
| Y29 | “Sensitive observations are hidden in selected views” | YICTE | PARTIAL | E09: selected evidence is redacted, but record metadata/link can remain visible. |
| Y30 | “uploaded file URLs and read-only case/report pages remain public to anyone who knows the URL.” | YICTE | TRUE | E09; public mount and unguarded read routes. |
| Y31 | “The audit trail is partial.” | YICTE | TRUE | E05/E08; status events exist, but mutable edits and AI replacement remain. |
| Y32 | “Status transitions are evented, and new review and finalization identities are recorded” | YICTE | TRUE | E02/E05/E07. |
| Y33 | “there is no complete append-only log for every edit, every AI rerun, or every report regeneration.” | YICTE | TRUE | Direct mutations at `backend/app/main.py:452-556,1198-1227`; report overwrite at `backend/app/reports.py:400-402`. |
| Y34 | “Live Azure behavior is implemented and mock-tested” | YICTE | TRUE-IN-CODE-ONLY | E06/E08; mocked provider suite passed, but live behavior is not observed. |
| Y35 | “no live Azure analysis result is committed as evidence.” | YICTE | TRUE | E14. |
| Y36 | “Risk scoring is an explainable heuristic.” | YICTE | TRUE | E07; explicit weights, multiplier, equation, cap, and bands. |
| Y37 | “It is not a validated conservation risk model, probability, structural-safety assessment, or professional recommendation.” | YICTE | TRUE for repository scope | E07/E14; deterministic heuristic and safety limits, with no validation artifact. |
| Y38 | “Individual reviewer accounts and roles.” under “Planned, Not Implemented” | YICTE | TRUE | E09. |
| Y39 | “Private media delivery for sensitive uploads.” under “Planned, Not Implemented” | YICTE | TRUE | E09. |
| Y40 | “Full append-only audit history for every edit and AI attempt.” under “Planned, Not Implemented” | YICTE | TRUE | E05/E08; no complete edit/AI-attempt event model exists. |
| Y41 | “Production deployment, HTTPS, backups, rate limiting, monitoring, malware scanning, and retention workflows.” under “Planned, Not Implemented” | YICTE | TRUE for repository implementation | E09. |
| Y42 | “Validated risk weights and thresholds based on expert or outcome evidence.” under “Planned, Not Implemented” | YICTE | TRUE | E07/E14; no validation input/output artifact exists. |

## Claim verdicts — STS description

| # | Claim text (verbatim) | Source | Verdict | Evidence |
|---|---|---|---|---|
| S01 | “Current verification: `220 passed, 538 warnings in 173.13s (0:02:53)` from `cd backend && AZURE_OPENAI_ENABLED=false pytest -q`.” | STS | PARTIAL | E01: 220/538 match; fresh elapsed time was 742.00s. |
| S02 | “The implemented research tooling supports a paired comparison of AI analysis conditions on the same physical asset” | STS | TRUE | E10; one asset produced both separate condition sessions. Physical identity depends on manifest preparation. |
| S03 | “`single_medium`: analysis of the medium-distance photo only.” | STS | TRUE | E10; runtime IDs `[102]`; `scripts/run_experiment.py:72-86`. |
| S04 | “`three_view`: analysis of the wide, medium, and close photos together.” | STS | TRUE | E10; runtime IDs `[101,102,103]`. |
| S05 | “The data model keeps experiment sessions separate from the community/demo workflow.” | STS | TRUE | E10; dry-run DB had 0 Observations and 0 RiskCases. |
| S06 | “`ExperimentAsset` represents one physical asset” | STS | TRUE as a data-model representation | `backend/app/models.py:191-205`; real-world identity is manifest-supplied. |
| S07 | “`AssessmentSession` stores one condition run with image ids, structured result payload, schema version, model deployment, run settings, run order, operator” | STS | TRUE | E10; `backend/app/models.py:208-244`; all fields observed in SQLite. |
| S08 | “and a frozen prompt/settings SHA-256 hash.” | STS | PARTIAL | E11: hashes system prompt/settings/deployment, not exact dynamic user content; one hashed setting is not sent. |
| S09 | “The experiment runner accepts a CSV or JSON manifest with: `asset_id, wide_path, medium_path, close_path`” | STS | TRUE | `scripts/run_experiment.py:35-52`; independent JSON and CSV dry-runs succeeded. |
| S10 | “It creates both conditions per asset in seeded randomized order.” | STS | TRUE | E10; seed-based order at `scripts/run_experiment.py:170,194-196`; focused test passed. |
| S11 | “The `single_medium` condition uses the identical medium image id as the `three_view` condition.” | STS | TRUE | E10; `[102]` appeared in both. |
| S12 | “The runner writes incrementally and can resume without duplicating existing asset/condition sessions.” | STS | TRUE | E10; per-session commit and rerun skip; partial-resume test passed. |
| S13 | “`--mock` is the tested offline mode” | STS | TRUE | E10; independent and automated mock runs passed. |
| S14 | “`--azure` is opt-in and requires live credentials.” | STS | TRUE-IN-CODE-ONLY | Guard at `scripts/run_experiment.py:22-26,145-152,264-267`; missing-env run refused, but credential validity/live execution was not tested. |
| S15 | “`research/corpus/` contains a manifest schema and metadata-only workflow for a private photo corpus.” | STS | TRUE-IN-CODE-ONLY | E12/E14; schema/tooling exists and synthetic fixture passed, but no real corpus run is evidenced. |
| S16 | “Raw photographs are not committed.” | STS | TRUE | E14. |
| S17 | “`scripts/audit_corpus.py` can scan a private photo directory, compute SHA-256 hashes, read dimensions, detect duplicate hashes, detect files missing since a previous manifest” | STS | TRUE | E12; all behaviors observed on the temporary fixture. |
| S18 | “preserve previous privacy/cultural-sensitivity statuses, and summarize counts by role and asset group.” | STS | TRUE | E12; prior status and exact counts observed. |
| S19 | “`scripts/select_assets.py` keeps only complete WIDE/MEDIUM/CLOSE asset groups whose privacy status and cultural-sensitivity status are both `cleared`” | STS | TRUE | E12; incomplete/private group exclusion observed. |
| S20 | “writes a seeded six-asset pilot split” | STS | PARTIAL | E12: six is the default/max; fewer eligible assets produce fewer than six. |
| S21 | “and a held-out test set for `scripts/run_experiment.py`.” | STS | PARTIAL | E12: held-out list is written, but runner ignores `held_out_assets`. |
| S22 | “`research/analysis/` contains pure analysis functions and a CLI for exported AI results and human reference labels.” | STS | TRUE | E13; functions and independent CLI execution verified. |
| S23 | “The human reference CSV format is: `asset_id, indicator_type, present, reviewer_id`” | STS | TRUE | `research/analysis/metrics.py:59-70`; loader test passed. |
| S24 | “`present` is `true`, `false`, or `uncertain`.” | STS | TRUE | `research/analysis/metrics.py:31-39`; hand fixture uses all three. |
| S25 | “Two reviewers can label a blinded subset for inter-rater agreement.” | STS | PARTIAL | E13: overlapping reviewer IDs and agreement work; blinding is not implemented or recorded. |
| S26 | “Indicator-level precision, recall, and F1, micro and macro, per condition.” | STS | TRUE | E13; `research/analysis/metrics.py:121-189`; hand-computed test passed. |
| S27 | “False-positive and missed-indicator counts.” | STS | TRUE | E13; expected counts asserted in the known-answer test. |
| S28 | “Unsupported-claim rate.” | STS | TRUE | `research/analysis/metrics.py:185`; expected `2/3` test passed. |
| S29 | “Insufficient-evidence rate per condition.” | STS | TRUE | `research/analysis/metrics.py:162-168,186`; expected `1/4` test passed. |
| S30 | “Paired per-asset recall and F1 deltas: `three_view - single_medium`.” | STS | TRUE | E13; known deltas `[0,1,1,0]` passed. |
| S31 | “Wilcoxon signed-rank test, effect size, and seeded bootstrap 95% confidence intervals.” | STS | TRUE | `research/analysis/metrics.py:222-289`; reporting at `research/analysis/reporting.py:44-59`. |
| S32 | “Confidence-vs-correctness means and reliability tables by confidence bin.” | STS | TRUE | `research/analysis/metrics.py:292-340`; known-answer test and CLI output passed. |
| S33 | “Cohen's kappa for the double-labelled subset.” | STS | TRUE | `research/analysis/metrics.py:343-381`; hand-computed kappa `0.5` passed. |
| S34 | “Repeatability agreement across repeated runs of a fixed subset.” | STS | PARTIAL | E13: standalone metric/test exists, but schema/runner prohibit repeated asset-condition sessions. |
| S35 | “The output files are `results.md`, `confusion_matrix.csv`, `paired_deltas.csv`, and `confidence_reliability.csv`.” | STS | TRUE | E13; all four appeared in independent output. |
| S36 | “The report explicitly states that `n` is the number of physical assets.” | STS | TRUE | E13; independent result stated `n = 1 physical assets`. |
| S37 | “Photos of one asset are never treated as independent samples.” | STS | TRUE for implemented metrics | Asset/type sets and paired asset scores at `research/analysis/metrics.py:97-119,192-289`. |
| S38 | “Automated tests use synthetic images and hand-computed toy data.” | STS | TRUE | `backend/tests/test_experiment_scripts.py:17-41`, `test_corpus_scripts.py:14-41`, `test_research_analysis.py:74-120`; E10/E13. |
| S39 | “They verify the corpus audit behavior, asset selection behavior, paired experiment session creation/resume behavior, and analysis metrics including F1, Cohen's kappa, paired deltas, confidence calibration, and repeatability.” | STS | TRUE as test coverage | E10-E13; all seven focused tests passed. Repeatability integration limit remains S34. |
| S40 | “No real 1,120-photo corpus manifest is committed.” | STS | TRUE | E14. |
| S41 | “No raw photos are committed.” | STS | TRUE | E14. |
| S42 | “No human reference labels for a real corpus are committed.” | STS | TRUE | E14. |
| S43 | “No live Azure experiment output is committed.” | STS | TRUE | E14. |
| S44 | “No statistical conclusion about model performance is currently supported by repository evidence.” | STS | TRUE | E14; no real inputs/results exist. |
| S45 | “The Azure path is implemented and mock-tested” | STS | TRUE-IN-CODE-ONLY | E06/E10; provider/mock tests pass, no live run. |
| S46 | “the current re-audit did not call live Azure.” | STS | UNVERIFIED | This audit made no live call, but repository state cannot prove what the earlier document-writing re-audit did. |
| S47 | “The risk score used in the product workflow remains a heuristic and is not part of a validated scientific outcome model.” | STS | TRUE for repository scope | E07/E14. |
| S48 | “Privacy-cleared real corpus manifest and audit report for the claimed corpus.” under “Planned, Not Implemented” | STS | TRUE | E14. |
| S49 | “Human reference labels from qualified or defined raters.” under “Planned, Not Implemented” | STS | TRUE | E14. |
| S50 | “Completed live Azure paired runs.” under “Planned, Not Implemented” | STS | TRUE | E14. |
| S51 | “Final precision/recall/F1, effect-size, confidence-calibration, repeatability, and inter-rater agreement results on the real corpus.” under “Planned, Not Implemented” | STS | TRUE | E14. |
| S52 | “Provider comparison conclusions, YOLO model work, labelled-dataset release, and uncertainty-aware evidence fusion.” under “Planned, Not Implemented” | STS | TRUE | E14; no implementation/artifact found. |

## Sentences that must change

There are no wholly FALSE claims, but every PARTIAL claim contains wording a
well-informed judge could challenge.

1. **Both descriptions — stale exact timing**

   Current:

   > Current verification: `220 passed, 538 warnings in 173.13s (0:02:53)` from `cd backend && AZURE_OPENAI_ENABLED=false pytest -q`.

   Minimal replacement:

   > A fresh Python 3.12 audit on 24 July 2026 verified `220 passed, 538 warnings`; elapsed time varies by host and load.

2. **YICTE — explicit review sequence**

   Current:

   > A reviewer compares contributor-original, current reviewed, and AI-proposed values, then accepts, edits, or rejects the AI proposal.

   Minimal replacement:

   > The primary AI-review page displays contributor-original, current reviewed, and AI-proposed values and offers accept, edit, and reject controls; not every authenticated finalization POST requires explicit per-indicator decisions.

3. **YICTE — immutable snapshot**

   Current:

   > Finalized Risk Cases store an immutable evidence and scoring snapshot.

   Minimal replacement:

   > Finalized Risk Cases store an application-level write-once scoring and evidence-reference snapshot; the database does not enforce immutability of the JSON column or image files.

4. **YICTE — universal transition enforcement**

   Current:

   > Case statuses follow enforced transitions: Draft → Needs Review; Needs Review → Verified or Draft; Verified → Routed or Needs Review; Routed → Closed.

   Minimal replacement:

   > Reviewer status changes through the normal status-update route follow the enforced transition graph; demo seeding can create cases directly in later statuses without transition events.

5. **YICTE — sensitive records**

   Current:

   > Sensitive observations are hidden in selected views, but uploaded file URLs and read-only case/report pages remain public to anyone who knows the URL.

   Minimal replacement:

   > Sensitive image, note, and tag evidence is redacted in selected views, although observation metadata can remain visible and uploaded file URLs plus read-only case/report pages are public to anyone who knows the URL.

6. **STS — prompt hash**

   Current:

   > `AssessmentSession` stores one condition run with image ids, structured result payload, schema version, model deployment, run settings, run order, operator, and a frozen prompt/settings SHA-256 hash.

   Minimal replacement:

   > `AssessmentSession` stores one condition run and a SHA-256 hash of the system prompt, model deployment, and configured prompt settings; dynamic notes and image-id user content are not included in the hash.

7. **STS — pilot size**

   Current:

   > `scripts/select_assets.py` keeps only complete WIDE/MEDIUM/CLOSE asset groups whose privacy status and cultural-sensitivity status are both `cleared`, then writes a seeded six-asset pilot split and a held-out test set for `scripts/run_experiment.py`.

   Minimal replacement:

   > `scripts/select_assets.py` selects complete cleared groups, writes a seeded pilot of up to six eligible assets, and writes a held-out list.

8. **STS — held-out runner input**

   Add immediately after the replacement above:

   > To run the held-out list, it must first be copied or transformed into a separate manifest's `assets` array because `run_experiment.py` does not read `held_out_assets`.

9. **STS — blinding**

   Current:

   > Two reviewers can label a blinded subset for inter-rater agreement.

   Minimal replacement:

   > The CSV supports overlapping labels from two reviewer IDs for inter-rater agreement; blinding is managed outside the software and is not recorded.

10. **STS — repeatability**

    Current:

    > Repeatability agreement across repeated runs of a fixed subset.

    Minimal replacement:

    > A standalone repeatability metric accepts repeated-session rows, but the current experiment runner and database schema do not create repeated asset/condition sessions.

## Bypass and integrity findings

### Complete application route inventory

The runtime route table contains 28 application routes, not 27. Framework docs
add four routes, and static/uploads add two public mounts.

| Method and path | Access / behavior |
|---|---|
| `GET /health` | Public |
| `GET /reviewer/login` | Public |
| `POST /reviewer/login` | Public; CSRF required |
| `POST /reviewer/logout` | Reviewer session + CSRF |
| `POST /seed` | Reviewer session + CSRF |
| `GET /` | Public |
| `GET /sites` | Public |
| `GET /sites/new` | Reviewer session |
| `POST /sites` | Reviewer session + CSRF |
| `GET /sites/{site_id}` | Public |
| `POST /observations/submit` | Public; CSRF required |
| `GET /observations/{obs_id}/submitted` | Public |
| `GET /observations/submit` | Public |
| `GET /observations/review` | Reviewer session |
| `GET /observations/{observation_id}/review` | Reviewer session |
| `POST /observations/{observation_id}/review` | Reviewer session + CSRF |
| `GET /observations/{obs_id}` | Public |
| `POST /observations/{obs_id}/analyze` | Reviewer session + CSRF + approval/reviewer gate |
| `GET /observations/{obs_id}/ai_review` | Reviewer session + readiness gate |
| `POST /observations/{obs_id}/create_risk_case` | Reviewer session + CSRF + readiness gate |
| `POST /observations/{obs_id}/reject_ai_analysis` | Reviewer session + CSRF + readiness gate |
| `POST /observations/{obs_id}/create_case` | Reviewer session + CSRF + readiness gate |
| `GET /cases` | Public |
| `GET /cases/{case_id}` | Public |
| `GET /cases/{case_id}/status` | Reviewer session |
| `POST /cases/{case_id}/status` | Reviewer session + CSRF + transition validation |
| `GET /cases/{case_id}/report` | Public; regenerates file and commits `report_path` |
| `GET /cases/{case_id}/report.md` | Public; regenerates file and commits `report_path` |

Framework routes: `GET /openapi.json`, `GET /docs`,
`GET /docs/oauth2-redirect`, and `GET /redoc`. Public mounts:
`/static` and `/uploads`.

### Creation and analysis paths relative to the Pending queue

| Path | Finding |
|---|---|
| `POST /observations/submit` | Not a bypass. It is public, creates `Pending`, leaves `reviewed_by` unset, and does not analyze. |
| `POST /sites` | Intentional authenticated bypass of Pending. With images it creates `ApprovedForAI`, stamps the reviewer, and immediately analyzes (`backend/app/main.py:865-913`). |
| `POST /observations/{id}/review` with `analyze_after_approval=true` | Approval and analysis occur in the same authenticated request. It still records the reviewer and passes the approval gate. |
| `POST /observations/{id}/analyze` | Not a data-gate bypass. It requires reviewer session/CSRF plus `ApprovedForAI` and nonempty `reviewed_by`. |
| `POST /seed` | Authenticated workflow bypass. `app.seed` inserts Approved observations, hard-coded mock proposals, finalized cases, and later statuses directly; it creates no corresponding CaseEvent history (`backend/app/seed.py:184-284`). |

No unauthenticated route can analyze an observation or create a RiskCase.
Public submission is the only unauthenticated observation-creation path and it
lands in Pending. Reviewer-led intake does bypass Pending, but it is
authenticated and explicitly human-led.

### AI finalization bypass

The primary AI-review UI is real and useful, but it is not an enforced universal
sequence:

- `POST /observations/{id}/create_case` accepts no per-indicator decisions or
  final values. It derives values from the mutable Observation and
  automatically records `Accepted` or `Edited and accepted`
  (`backend/app/main.py:1469-1506`).
- The primary `create_risk_case` POST makes all indicator decision arrays
  optional (`backend/app/main.py:1344-1405`).
- Reviewer working values remain editable after case creation unless the
  request also asks to rerun analysis (`backend/app/main.py:1216-1227`). The
  snapshot keeps case output stable, but the live Observation can then
  contradict it.

### AI provider-failure integrity

Malformed Azure JSON/schema is truthfully retained as a failed validation state.
Transport, missing-file, import, API, and unexpected provider failures instead
become generic mock output. That mock output is correctly labelled, but the
failed attempt and diagnostic are lost. Any claim that every Azure failure is
preserved would be false.

There is also a stale provider-contract condition:
`apply_ai_analysis_result` checks provider exactly `"azure_openai"`
(`backend/app/main.py:495-503`), while successful provider results use
`"azure:<deployment>"` (`backend/app/services/providers/azure_openai_provider.py:204-224`).

### Baseline-history integrity

At audit time, `competition_baseline.md` was candid that its resolution
references meant `WT@9c85291`, but these were not commit references. The only
historical commit for that file was `9c85291`, whose application code did not
contain most of the claimed resolutions. The audited working tree did contain
identifiable code/tests for most of them, but all were still uncommitted at
that point.

The baseline rewrite deleted or compressed several limitations that are not
fully resolved:

1. Pre-AI review has `reviewed_by`, but no review timestamp or append-only
   review event on Observation.
2. Explicit AI-output review remains bypassable through the compatibility
   finalizer and optional indicator fields.
3. Authenticated reviewer intake and browser seed do not pass through Pending.
4. Azure transport/configuration failures are replaced by generic mock output
   without preserving the failed attempt.
5. Seeded later statuses have no transition events.
6. Public report GET routes still write report files and commit database state.

The re-audit also describes multi-image Pending submission as a newly resolved
absence, although commit `9c85291` already contained a public multi-image
Pending path. The historical gap was the alternate bypass routes and lack of
image-backed demo evidence, not complete absence of multi-image submission.

### Additional STS apparatus integrity findings

- The prompt hash is not a hash of the exact rendered request.
- `held_out_assets` is not consumed by the runner.
- The normal experiment export drops `site_label`, so site-concentration output
  is always unavailable (`{}` / `NaN`).
- The unique session constraint prevents the experiment runner from generating
  data for its own repeatability metric.
- The analysis code supports multiple reviewer IDs but does not implement or
  record blinding.

## Summary

### Verdict counts

| Description | TRUE | PARTIAL | FALSE | UNVERIFIED | TRUE-IN-CODE-ONLY | Total |
|---|---:|---:|---:|---:|---:|---:|
| YICTE | 35 | 5 | 0 | 0 | 2 | 42 |
| STS | 42 | 6 | 0 | 1 | 3 | 52 |
| **Combined** | **77** | **11** | **0** | **1** | **5** | **94** |

Full-suite summary:

```text
220 passed, 538 warnings in 742.00s (0:12:21)
```

### YICTE bottom line

**Could a well-informed judge find a false statement in the YICTE document
today? Yes, in the unqualified parts of five sentences.** The implemented
public/reviewer workflow, upload sanitization, auth gates, schema-v2 proposal,
snapshot rendering, and status route are all strongly evidenced. The document
overstates DB/content immutability, implies every finalization follows explicit
AI review, implies every status originates through the transition route, and
says sensitive observations are hidden when selected evidence—not the entire
record—is redacted. The claimed test count is correct, but the embedded elapsed
time is stale/non-portable.

### STS bottom line

**Could a well-informed judge find a false statement in the STS document today?
Yes, in the unqualified parts of six sentences.** The paired mock apparatus,
resume/export path, corpus fixture tooling, and metric functions are real and
tested. However, the hash does not cover the exact rendered prompt, a pilot can
contain fewer than six assets, held-out assets are not accepted by the runner,
blinding is external, and the native schema cannot create repeat runs for the
repeatability metric. No live Azure result, real corpus, real labels, or
scientific result is evidenced, and the description otherwise discloses that
accurately.
