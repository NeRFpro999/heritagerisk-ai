# HeritageRisk AI Competition Baseline Audit

Audit date: 2026-07-14 (Australia/Melbourne, UTC+10)
Repository: `/Users/emmamuhi/Desktop/heritagerisk-ai`
Audit mode: read-first, local-only, no external service calls

This file records the repository state before 2026 Science Talent Search Victoria
and Young ICT Explorers competition work begins. It describes implementation and
test evidence observed in the working tree. Documentation was treated as a claim
to check, not as proof that a feature works.

No photo USB or other external volume was scanned. No uploaded image content was
opened or copied. No credential value is included in this report.

## Post-Audit Maintenance Update — 2026-07-22

The historical Git-state and 154-test evidence below remain the point-in-time
2026-07-14 audit record. Before committing the July working tree, the app gained
a guarded, idempotent SQLite startup migration. It adds the review-status column
only when absent, marks only pre-review legacy rows `ApprovedForAI`, and backfills
legacy image values without duplication. The standalone migration command now
uses the same helper, and two regression tests cover repeat runs and preservation
of an existing `Pending` row.

Current offline verification after that maintenance change is:
`AZURE_OPENAI_ENABLED=false pytest -q` — **156 passed, 133 warnings in 10.40s**.

## Classification Key

| Classification | Meaning in this audit |
|---|---|
| VERIFIED WORKING | Implemented and exercised successfully by the captured local test run or a read-only integrity check. |
| PARTIAL | Some implementation works, but an important control, invariant, audit property, or end-to-end condition is missing. |
| MOCK OR DEMONSTRATION ONLY | Deliberately simulated behavior that must not be represented as real analysis or production operation. |
| DOCUMENTED BUT UNVERIFIED | Described or configured, but not exercised under this audit's no-network/no-private-image restrictions. |
| PLANNED | Explicit future scope with no current implementation. |
| ABSENT | No implementation was found. |

## 1. Executive Factual Summary

HeritageRisk AI is currently a local, server-rendered FastAPI demonstration with
SQLAlchemy, SQLite, Jinja2, vanilla CSS, an optional Azure OpenAI image-analysis
adapter, an offline note-keyword mock, deterministic rule-based scoring, and
Markdown plus HTML report views.

The captured offline test run verifies a functional demonstration path through
public multi-image submission, `Pending` status, reviewer decisions, AI gating,
mock analysis, AI-output review, Risk Case creation, case status updates, and
report rendering. All 154 collected test items passed.

The application is not a production public service. There is no authentication,
reviewer identity, authorization, CSRF protection, private media delivery, EXIF
removal, image-signature verification, rate limiting, or sequential case-state
enforcement. Every reviewer and mutation endpoint is available to any process
that can reach the app.

Five material integrity limitations prevent the strongest current workflow and
audit claims:

1. `POST /sites` with images and the legacy site-observation route create
   `ApprovedForAI` observations directly. They are described as internal paths,
   but no authentication distinguishes a reviewer from another caller.
2. `POST /observations/{id}/create_case` can create a Risk Case after an AI
   summary without recording the explicit post-AI finalization decision used by
   the newer route.
3. Reviewer edits overwrite `Observation.notes`, `damage_tags`, and `severity`.
   The AI-review page therefore labels reviewer-mutated values as "Original
   Evidence," and reports can label reviewed notes as "Contributor notes."
4. An observation can still be edited after its Risk Case exists. The stored
   score/band can then disagree with a breakdown recalculated from the changed
   observation.
5. `Sensitive` suppresses evidence in selected templates only. Uploaded files
   remain directly addressable under the unauthenticated `/uploads` static mount,
   and the reviewer screen is also unauthenticated.

The Azure adapter is implemented and well covered with mocked clients, but live
Azure image analysis was not called and is not verified by this audit. The local
`.env` enables Azure and contains all required settings, but their values,
validity, deployment identity, data-handling configuration, and service response
were intentionally not inspected or tested.

The current persisted database is internally readable and passes SQLite's
integrity check, but it contains 7 sites, 7 observations, 0 `ObservationImage`
rows, and 7 Risk Cases. The repository contains no JPG, PNG, WEBP, GIF, or HEIC
files outside ignored environments. Therefore the current stored demo does not
itself provide multi-image evidence even though multi-image behavior is tested.

## 2. Repository and Git State

### Repository and Instructions

- Repository path exists and resolves to the expected Git worktree.
- Applicable instruction search covered the repository and parent path hierarchy.
- The only applicable instruction file found was root `AGENTS.md`; it was read in
  full before implementation inspection.
- `competition_baseline.md` did not exist before this audit, so this filename was
  safe to create.

### Branch and Latest Commit

- Branch: `day1-mvp-stabilisation`
- HEAD: `d4c6b1e44c00c9bf4a031e74705776d872bc822c`
- Short HEAD: `d4c6b1e`
- Author: `NeRFpro999`
- Commit date: `2026-06-02T14:42:15+10:00`
- Subject: `Stabilise HeritageRisk AI MVP demo workflow`

### Pre-Audit Status Summary

- Tracked files: 49
- Tracked modified, unstaged: 24
- Staged: 0
- Untracked: 29
- Ignored status entries: 13 (Git reports ignored directories as directory entries)
- All pre-existing changes were treated as user-owned.
- No pre-existing file was staged, committed, discarded, overwritten, or deleted.

The pre-audit tracked/untracked status listing hash was
`e002b6e4f094153bfae188cf75b18b8cace475d171558685b3e68f839cb1f037`.
It remained identical after the test run. The database SHA-256 was
`5e42d4ccb78f0f8f418516bb383c16a0199725ea27175be196a51aa63b2fcdac`
before and after tests.

### All Tracked Files at Audit Start

```text
.env.example
.gitignore
LICENSE
README.md
backend/README.md
backend/__init__.py
backend/app/__init__.py
backend/app/config.py
backend/app/database.py
backend/app/main.py
backend/app/models.py
backend/app/reports.py
backend/app/risk.py
backend/app/routers/__init__.py
backend/app/seed.py
backend/app/services/__init__.py
backend/app/services/ai_analysis.py
backend/app/services/providers/__init__.py
backend/app/services/providers/azure_openai_provider.py
backend/app/static/style.css
backend/app/templates/_safety_note.html
backend/app/templates/base.html
backend/app/templates/case_detail.html
backend/app/templates/case_report.html
backend/app/templates/cases_list.html
backend/app/templates/index.html
backend/app/templates/observation_detail.html
backend/app/templates/observation_new.html
backend/app/templates/site_detail.html
backend/app/templates/site_new.html
backend/app/templates/sites_list.html
backend/requirements.txt
backend/run.py
backend/tests/__init__.py
backend/tests/test_ai.py
backend/tests/test_mvp_smoke.py
backend/tests/test_reports.py
backend/tests/test_risk.py
backend/tests/test_seed.py
data/heritagerisk.db
data/uploads/.gitkeep
pytest.ini
reports/.gitkeep
reports/BUILD_LOG.md
reports/case_1.md
reports/case_2.md
reports/case_3.md
reports/case_4.md
reports/docs/MULTI_IMAGE_ASSESSMENT_DESIGN.md
```

### All Pre-Existing Modified Tracked Files

All 24 entries were unstaged:

```text
.env.example
README.md
backend/app/config.py
backend/app/main.py
backend/app/models.py
backend/app/reports.py
backend/app/risk.py
backend/app/seed.py
backend/app/services/ai_analysis.py
backend/app/services/providers/azure_openai_provider.py
backend/app/static/style.css
backend/app/templates/base.html
backend/app/templates/case_detail.html
backend/app/templates/case_report.html
backend/app/templates/index.html
backend/app/templates/observation_detail.html
backend/app/templates/observation_new.html
backend/app/templates/site_detail.html
backend/app/templates/site_new.html
backend/tests/test_ai.py
backend/tests/test_mvp_smoke.py
backend/tests/test_reports.py
backend/tests/test_risk.py
data/heritagerisk.db
```

### All Staged Files

None.

### All Pre-Existing Untracked Files

```text
AGENTS.md
PROJECT_CHARTER.md
RESEARCH_LOG.md
TECHNICAL_SCOPE.md
backend/app/templates/ai_review_result.html
backend/app/templates/case_status.html
backend/app/templates/review_action.html
backend/app/templates/review_queue.html
backend/app/templates/submission_received.html
backend/app/templates/submit_observation.html
backend/tests/test_ai_analysis_gate.py
backend/tests/test_ai_review_flow.py
backend/tests/test_dashboard.py
backend/tests/test_multi_image_templates.py
backend/tests/test_review_actions.py
backend/tests/test_review_queue.py
backend/tests/test_site_ai_intake.py
docs/.pytest_baseline_run.txt
docs/BUILD_LOG.md
docs/SMOKE_TEST_CHECKLIST.md
docs/TEST_BASELINE.md
docs/evidence/2026-06-06/README.md
docs/evidence/2026-06-08/README.md
docs/evidence/2026-06-08/SMOKE_TEST_RECORD.md
reports/case_5.md
reports/case_6.md
reports/case_7.md
scripts/migrate_multi_image_schema.py
scripts/test_azure_openai.py
```

### All Ignored Status Entries

```text
.claude/
.env
.pytest_cache/
.venv/
backend/.pytest_cache/
backend/.venv/
backend/__pycache__/
backend/app/__pycache__/
backend/app/routers/__pycache__/
backend/app/services/__pycache__/
backend/app/services/providers/__pycache__/
backend/tests/__pycache__/
scripts/__pycache__/
```

### Internal Storage Snapshot

Only repository-local storage was inspected, using file metadata and aggregate
database queries. Generated report bodies and private image content were not
opened.

| Item | Observed state |
|---|---|
| Internal filesystem | 113 GiB total, 89 GiB used, 3.4 GiB available, 97% capacity |
| SQLite database | `data/heritagerisk.db`, 65,536 logical bytes, integrity check `ok` |
| Database journal mode | `delete` |
| Sites | 7 |
| Observations | 7, all currently `ApprovedForAI` |
| Observation images | 0 rows |
| AI statuses | 7 `mock` |
| Risk Cases | 7: Draft 1, Needs Review 2, Verified 2, Routed 2, Closed 0 |
| Upload files | 0 files other than `.gitkeep` |
| Image-like files in repository | 0 outside Git and Python environments |
| Generated case report names | `case_1.md` through `case_7.md` exist |
| Reports tree | 9 files excluding `.gitkeep`, 13,616 logical bytes total |
| Screenshot evidence | No screenshot files; `docs/evidence` contains three text records only |

## 3. Architecture Map

### Runtime Entry and Routes

- `backend/run.py` launches Uvicorn for `app.main:app` on `127.0.0.1:8000`
  with reload enabled.
- `backend/app/main.py` contains one FastAPI app and all 27 routes. The
  `backend/app/routers/` package is empty by design.
- Importing `app.main` creates upload/report directories, calls
  `Base.metadata.create_all(bind=engine)`, and then runs the guarded SQLite
  startup migration.

Route groups:

| Group | Routes |
|---|---|
| Health/demo | `GET /health`, `POST /seed`, `GET /` |
| Sites | `GET /sites`, `GET /sites/new`, `POST /sites`, `GET /sites/{id}` |
| Legacy site observation | `GET /sites/{id}/observations/new`, `POST /sites/{id}/observations` |
| Public submission | `GET /observations/submit`, `POST /observations/submit`, `GET /observations/{id}/submitted` |
| Submission review | `GET /observations/review`, `GET/POST /observations/{id}/review` |
| Observation/AI | `GET /observations/{id}`, `POST /observations/{id}/analyze`, `GET /observations/{id}/ai_review`, `POST /observations/{id}/reject_ai_analysis` |
| Case creation | `POST /observations/{id}/create_risk_case`, legacy `POST /observations/{id}/create_case` |
| Cases/reports | `GET /cases`, `GET /cases/{id}`, `GET/POST /cases/{id}/status`, `GET /cases/{id}/report`, `GET /cases/{id}/report.md` |

### Database and Models

`backend/app/database.py` uses one file-backed SQLite engine with
`check_same_thread=False` and session-per-request dependency injection. There is
no Alembic migration system. A small idempotent startup helper covers the July
review-status and legacy-image upgrade, and `scripts/migrate_multi_image_schema.py`
provides a command-line wrapper around the same helper.

| Model | Principal fields and relationships |
|---|---|
| `Site` | name, location, description, created time; one-to-many observations |
| `Observation` | mutable notes/tags/severity, review enum, AI fields/raw JSON, images, one Risk Case |
| `ObservationImage` | observation foreign key, image URL, created time |
| `RiskCase` | unique observation foreign key, stored score/band, mutable status/destination/report path, timestamps |

The current SQLite schema has a check constraint for the four human-review enum
values, but no database check constraints for severity, AI status, Risk Case
score/band, or Risk Case status. The engine code does not enable SQLite foreign
keys explicitly; the audit connection reported `PRAGMA foreign_keys = 0`.

### Templates and Assets

- 17 Jinja2 templates are in `backend/app/templates/`.
- One 1,014-line stylesheet is in `backend/app/static/style.css`.
- The UI is server-rendered. There is a small inline vanilla JavaScript block for
  public tag checkbox serialization and inline range-slider behavior.
- No React, CSS framework, JavaScript bundle, or external visual asset was found.
- Jinja2 renders the dashboard, submission, review queue/action, observation,
  AI review, site, case, status, and structured HTML report pages.

### File and Image Storage

- Uploaded bytes are written to `data/uploads/` and publicly mounted at
  `/uploads` with `StaticFiles`.
- The server accepts extensions `.jpg`, `.jpeg`, `.png`, and `.webp`, reads each
  whole file into memory, rejects empty files and files larger than 10 MiB, and
  permits at most six files in the multi-image routes.
- Stored names are random UUID hex strings plus the supplied extension.
- Reports are written as `reports/case_<id>.md`; report paths are stored as
  absolute filesystem paths in `RiskCase.report_path`.

### AI Adapters

- `backend/app/services/ai_analysis.py` provides `AIAnalysisResult`, single-image
  and multi-image entry points, and the mock fallback.
- The mock scans context/notes keywords. It does not inspect image pixels. It is
  correctly labelled with low confidence and an explicit high-uncertainty note.
- `backend/app/services/providers/azure_openai_provider.py` base64-encodes all
  supplied images, submits one chat-completions request through an Azure-style
  OpenAI v1 base URL, requests JSON, validates taxonomy/ranges, and returns the
  shared result type.
- Missing configuration, missing files, import failures, API failures, malformed
  JSON, and most unexpected service-level exceptions fall back to mock.
- Live Azure connectivity and deployment behavior were not tested.

### Risk and Reports

- `backend/app/risk.py` implements deterministic arithmetic and breakdown data.
- `backend/app/reports.py` writes Markdown with all linked image URLs, review and
  AI sections, score arithmetic, routing text, limitations, and a final safety
  blockquote.
- `case_report.html` independently renders a structured HTML report and exposes
  the Markdown source in an escaped `<pre>` block.
- Report GET routes regenerate the Markdown file and update the database, so GET
  is not side-effect-free.

### Test Architecture

- `pytest.ini` sets `pythonpath = backend` and `testpaths = backend/tests`.
- There are 13 test modules and no shared `conftest.py`.
- Route tests repeatedly create in-memory SQLite engines, override `get_db`, and
  patch upload/report directories to pytest temporary directories.
- Provider tests use fake credentials and mocked OpenAI clients.
- `test_mvp_smoke.py` is a stateful, ordered integration sequence rather than a
  set of fully independent tests.

## 4. Verified End-to-End Workflow

The following local/offline path is supported by implementation and the passing
tests:

1. A contributor opens `/observations/submit`, selects or describes a site, and
   submits one to six files with optional notes/tags and a required severity.
2. The public handler ignores an injected review-status field and writes the
   observation as `Pending`.
3. The review queue defaults to `Pending` and filters by all four enum statuses.
4. The review form can set `ApprovedForAI`, `Rejected`, or `Sensitive`, replace
   notes/tags/severity, and optionally run analysis after approval.
5. `/observations/{id}/analyze` checks for `ApprovedForAI` before invoking either
   analyzer. A tested Pending observation receives HTTP 403.
6. Offline mode returns a clearly labelled mock result. AI-suggested tags and
   severity are stored in raw JSON and do not overwrite observation tags or
   severity at analysis-application time.
7. `/observations/{id}/ai_review` requires approval, a `complete` or `mock`
   analysis summary, and no existing Risk Case. It displays images alongside AI
   output and offers final tags, severity, summary, next step, notes, and routing.
8. The new finalization route creates one Risk Case, calculates its score/band,
   writes a Markdown report, and redirects to the case page. Rejected AI status
   blocks case creation until analysis is rerun.
9. Case status can be manually assigned to one of Draft, Needs Review, Verified,
   Routed, or Closed. Routed requires a nonempty destination.
10. Structured HTML and downloadable Markdown report routes return successfully
    in tests.

This is a demonstration workflow, not an enforced reviewer-identity workflow.
The unauthenticated alternate intake paths, legacy case route, mutable records,
and nonsequential statuses materially limit claims of a strict end-to-end gate.

## 5. Feature-Status Table

| Material feature | Status | Evidence and qualification |
|---|---|---|
| FastAPI application and 27 routes | VERIFIED WORKING | Imports and the current 156-test suite pass; route map is in `backend/app/main.py`. |
| Dashboard metrics and empty state | VERIFIED WORKING | Empty and populated database route tests pass. |
| SQLAlchemy/SQLite persistence | PARTIAL | CRUD works and DB integrity is `ok`; startup covers the tested July additive migration, but there is no general migration system and foreign keys are not explicitly enabled. |
| Public one-to-six-image submission | VERIFIED WORKING | Tests persist multiple `ObservationImage` rows and enforce count/missing-image behavior. Actual image content is not verified. |
| Current persisted multi-image demo evidence | ABSENT | Current DB has zero image rows and repository has no image files. |
| Public `Pending` hardcoding/status injection resistance | VERIFIED WORKING | Handler assigns `Pending`; injection test passes. |
| Universal Pending-before-AI workflow | PARTIAL | Public route is strict, but `/sites` with images and `/sites/{id}/observations` create approved observations directly without authenticated reviewer context. |
| Review queue and enum filters | VERIFIED WORKING | Pending default, all filters, counts, and invalid filter tests pass. |
| Reviewer approve/reject/Sensitive actions | PARTIAL | Mutations and validation work, but there is no reviewer identity/timestamp for this stage and original values are overwritten. |
| Backend AI status gate | PARTIAL | The equality check and 403 are tested, but callers can reach unauthenticated routes that manufacture approval. |
| Multi-image analyzer request assembly | VERIFIED WORKING | Mocked Azure test confirms multiple image content blocks in one request. |
| Live Azure image analysis | DOCUMENTED BUT UNVERIFIED | Configuration is locally present/enabled; no network/service call was permitted. |
| Azure response validation/fallback | PARTIAL | Mocked success, API failure, missing settings/files, malformed JSON, clamps, and taxonomy filtering pass; real-service contract is unverified. |
| Offline keyword analyzer | MOCK OR DEMONSTRATION ONLY | It scans notes/context, not image pixels, and must never be described as image analysis. |
| AI suggestions separate at analysis time | VERIFIED WORKING | `apply_ai_analysis_result` leaves observation tags/severity unchanged and writes suggestions to raw JSON. |
| Immutable original contributor evidence | ABSENT | Reviewer action overwrites notes/tags/severity; there is no contributor snapshot or revision table. |
| AI-output comparison/finalization UI | PARTIAL | Page and form work, but "Original Evidence" may already be reviewer-mutated and finalization overwrites shared fields. |
| AI-draft rejection and case block | VERIFIED WORKING | Rejection records a decision, marks status rejected, and blocks case creation. |
| Rejected-draft rerun history | PARTIAL | The analysis route can be called again after rejection, but the full reject-then-rerun path is not directly tested and prior AI payloads are not retained as complete revisions. |
| Human finalization required for every Risk Case | PARTIAL | New route records finalization; legacy `/create_case` creates a case without that explicit decision. |
| One Risk Case per observation | VERIFIED WORKING | ORM/DB unique relation and route checks enforce one in normal tested use. Concurrency handling is untested. |
| Explainable scoring implementation | VERIFIED WORKING | Formula, weights, cap, thresholds, and breakdown tests pass. It is an unvalidated heuristic, not a scientific probability. |
| Score/report immutability after case creation | ABSENT | Observation review remains mutable after case creation; stored score and recalculated breakdown can diverge. |
| Draft/Needs Review/Verified/Routed/Closed values | VERIFIED WORKING | Values render and valid assignments persist. |
| Sequential lifecycle transitions | ABSENT | Any valid status can be assigned from any other status; no transition history is stored. |
| Manual routing destination record | VERIFIED WORKING | Routed requires destination and reports show it. It is only a database field. |
| Email/council/authority dispatch | ABSENT | No delivery integration exists; UI correctly states that it does not send. |
| Markdown report generation | VERIFIED WORKING | Section, mapping, multi-image, equation, and safety-clause tests pass. |
| Structured HTML report | VERIFIED WORKING | Route/template tests pass. |
| Truthful review audit proof | PARTIAL | Reports show audit sections, but HTML hardcodes `True` and Markdown derives it from current status rather than timestamped events. |
| Sensitive-evidence display suppression | PARTIAL | General templates hide content; direct static URL and reviewer page remain unauthenticated. |
| Authentication and role authorization | ABSENT | No user/session/security dependency or middleware exists. |
| CSRF protection | ABSENT | All POST forms lack tokens and no CSRF middleware exists. |
| Upload file-signature validation | ABSENT | Extension is trusted; a test explicitly accepts fake JPEG bytes named `.jpg`. |
| Safe stored filenames | VERIFIED WORKING | UUID-generated basename prevents contributor filename traversal/collision in normal use. |
| EXIF/GPS removal | ABSENT | Original bytes are written unchanged and sent unchanged to Azure when enabled. |
| Demo seeding | MOCK OR DEMONSTRATION ONLY | Fixed text and hardcoded mock analyses are useful offline, but contain no images and do not generate real AI evidence. |
| YOLO provider/model | PLANNED | Mentioned as later AUSSEF/ISEF scope; no implementation exists. |
| Labelled heritage image dataset | ABSENT | No dataset or evaluation artifacts were found. |
| Production/cloud deployment | ABSENT | Current launcher binds local loopback; no production access/security configuration exists. |

## 6. Evidence Separation Audit

| Evidence layer | Actual storage | Finding |
|---|---|---|
| Original contributor site data | `Site` fields | Stored, but no immutable submission snapshot or change history exists. |
| Original contributor images | `ObservationImage` rows/files | Separate rows and no edit UI; raw files retain metadata and are publicly mounted. |
| Original contributor notes/tags/severity | `Observation.notes`, `damage_tags`, `severity` | Not preserved after reviewer edits. |
| Reviewer-edited submission data | Same three `Observation` fields | Overwrites contributor values; no reviewer identity, review time, before/after diff, or revision object. |
| AI-suggested tags/severity | `Observation.ai_raw_response` JSON | Separate from human fields at analysis time and used by comparison/report views. |
| AI summary/confidence/provider/action | Structured `Observation` fields plus raw JSON | Initial AI summary is in raw JSON; reviewer finalization overwrites the structured summary/action. |
| Human AI-review decision | `human_ai_review` object inside raw JSON | Has decision, optional notes, and timestamp; no reviewer identity or relational audit record. |
| Human-finalized tags/severity | Same mutable `Observation` fields | Not snapshotted into `RiskCase`; later edits can change the displayed equation without changing stored score/band. |
| Prior analysis attempts | Mostly replaced on rerun | Previous human review objects can move to a JSON history list, but complete prior AI payloads/provider attempts are not retained. |

Direct answer to silent-overwrite risk: applying an AI result does **not** silently
overwrite contributor/reviewer tags or severity; that separation has a passing
unit test. However, the reviewer submission step deliberately overwrites original
contributor notes/tags/severity, and finalization overwrites the shared final
tags/severity and structured AI summary/action. The repository therefore cannot
currently reconstruct a complete original -> reviewer-edited -> AI-suggested ->
human-finalized chain.

Two report/UI labels are not supported by durable evidence:

- `ai_review_result.html` calls current mutable fields "Original Evidence."
- `case_report.html` hardcodes `Reviewed before AI analysis: True`;
  `reports.py` infers the same claim from current `ApprovedForAI` status.

## 7. Risk or Priority Calculation

### Exact Implementation

```text
normalized severity = clamp(severity, 1, 5)
tag sum = sum(weight for every supplied tag occurrence)
raw score = tag sum * normalized severity
final score = min(raw score, 100)
```

Weights in `backend/app/risk.py`:

| Tag | Weight |
|---|---:|
| `crack` | 8 |
| `erosion` | 7 |
| `graffiti` | 3 |
| `corrosion` | 7 |
| `water_staining` | 6 |
| `vegetation_growth` | 4 |
| `surface_loss` | 7 |
| `fire_damage` | 7 |
| `other` | 2 |
| unknown tag passed directly to scorer | 0 |

Bands:

- Low: 0-29
- Medium: 30-59
- High: 60-100

The cap, score-60 boundary, empty-tag score, unknown-tag behavior, and breakdown
fields are directly tested. Route handlers validate severity 1-5 and known tags,
but repeated tags are not deduplicated. A crafted repeated form value or direct
function call counts the same weight repeatedly; the cap test itself uses repeated
tags.

The equation and thresholds appear in `case_detail.html`, `case_report.html`, and
generated Markdown. The implementation and reports say the score is rule-based
and not decided by AI. No code or document presents it as a probability, and no
validation/calibration evidence was found. The UI nevertheless labels it "Risk
Assessment," "Risk score," and Low/Medium/High "Risk," rather than explicitly
calling it an unvalidated prioritization heuristic. It must not be represented as
validated conservation risk, failure probability, urgency, or structural safety.

## 8. Exact Test Evidence

The local `.env` has Azure enabled and all required settings present. One smoke
test assumes the default is disabled and calls the analysis route without patching
settings. Running bare `pytest` under this local configuration could therefore
call the real service, contradicting the repository's offline-test claim.

To obey the no-network requirement, the captured evidence command was:

```bash
cd /Users/emmamuhi/Desktop/heritagerisk-ai/backend
AZURE_OPENAI_ENABLED=false pytest
```

Environment and result:

| Field | Captured value |
|---|---|
| Pytest executable | `/Library/Frameworks/Python.framework/Versions/3.13/bin/pytest` |
| Python | 3.13.3 |
| pytest | 8.3.5 |
| Config root | repository root, `pytest.ini` |
| Start | `2026-07-14T11:31:49+1000` |
| End | `2026-07-14T11:31:56+1000` |
| Shell wall time | 7 seconds |
| Pytest-reported duration | 5.60 seconds |
| Collected | 154 |
| Passed | 154 |
| Failed | 0 |
| Skipped | 0 |
| Warnings | 133 |
| Exit code | 0 |

Warnings are deprecations for `datetime.utcnow()`, Starlette's old
`TemplateResponse` argument order, and TestClient's `allow_redirects` argument.

An earlier output-capture attempt used the same offline override but did not
return a complete summary to the audit harness. Its process was allowed to finish
and is excluded from the reported evidence. The table above is the subsequent,
fully captured run.

### What the Suite Does Cover

- Mock behavior and wording.
- Mocked Azure success, multiple-image payloads, API failure, missing settings,
  malformed JSON, taxonomy filtering, and range clamps.
- Public multi-image persistence, Pending enforcement, count limit, missing
  image, invalid extension, and safe randomized paths.
- Review queue filters and action validation.
- Pending AI and Risk Case gates.
- AI-review acceptance, edits, rejection, reports, and routing destination.
- Rule arithmetic, cap, thresholds, and report breakdown.
- Dashboard empty/populated states and seed-data constants/integration path.

### Material Untested Failure Paths

- Real Azure connectivity, deployment compatibility, latency, quotas, and image
  policy behavior.
- Bare-suite network isolation when a developer's `.env` enables Azure.
- Actual image signatures/decoding, decompression bombs, malware, EXIF/GPS, 10
  MiB rejection, aggregate request memory, and MIME/content mismatch.
- Authentication, authorization, CSRF, direct sensitive-file access, rate limits,
  and hostile cross-origin requests to localhost.
- Reviewer edits after AI analysis and after Risk Case creation.
- Score/band/breakdown consistency after mutable observation changes.
- Sequential status transitions and status/routing audit history.
- Report filesystem failures after database commit, report injection, read-only
  filesystem behavior, and rollback consistency.
- Migration failures outside the tested legacy status/image upgrade shapes.
- Valid JSON with a non-object top level, unexpected response content types, and
  duplicate AI/final tags.
- Concurrent duplicate case creation and SQLite locking.
- Browser accessibility, mobile layout, multiple browsers, and current manual
  end-to-end use.

## 9. Security and Privacy Boundary Table

| Boundary | Status | Actual control and consequence |
|---|---|---|
| Authentication | ABSENT | No login, session, account, password, API key guard, or reviewer identity. |
| Authorization | ABSENT | Review, analysis, case, report, seed, and routing endpoints have no role check. |
| Server-side AI status check | PARTIAL | Approved enum is checked, but approval can be created through unauthenticated alternate routes. |
| Risk Case gate | PARTIAL | New route checks approval/summary; legacy route bypasses explicit AI finalization. |
| CSRF protection | ABSENT | Mutation forms and endpoints have no token or same-origin verification. External pages may be able to target a running localhost app. |
| Upload extension/type | PARTIAL | Extension allowlist only; declared MIME and bytes are not validated. |
| File signature/decoder verification | ABSENT | Fake `.jpg` bytes are accepted in a passing test. Pillow is installed but unused. |
| Size/count limits | PARTIAL | 10 MiB per file and six-file count exist; whole files are read before size check and there is no total request/rate limit. |
| Filename/path safety | VERIFIED WORKING | UUID basenames prevent normal filename traversal and collisions. |
| EXIF/GPS handling | ABSENT | Metadata is neither inspected nor stripped before disk storage or Azure transfer. |
| Sensitive evidence | PARTIAL | Selected templates hide fields; static file URLs and reviewer pages are not protected. |
| Upload confidentiality | ABSENT | `/uploads` is a public static mount to every app visitor who knows/obtains a URL. |
| Data retention/deletion | ABSENT | No retention policy, expiry, secure deletion, or contributor deletion route exists. |
| Secret handling | PARTIAL | `.env` is ignored and application source reads environment values; no non-fake hardcoded source credential was found. There is no production secret manager, and local Azure is enabled. |
| Output escaping | PARTIAL | Jinja HTML autoescaping applies; Markdown generator interpolates user text without Markdown escaping or report-integrity controls. |
| Transport security | ABSENT | Local launcher is plain HTTP; no TLS or proxy/security headers are configured. |
| Host/deployment boundary | PARTIAL | `run.py` binds loopback, reducing LAN exposure; starting Uvicorn differently can expose the entirely unauthenticated app. |
| Database constraints | PARTIAL | Review enum and one-case uniqueness exist; most workflow/range invariants are application-only. Foreign keys are not explicitly enabled. |

Until these boundaries change, only nonprivate demonstration images should be
used, `Sensitive` must not be represented as access-controlled storage, and the
app should remain on a trusted local machine.

## 10. Reliability Findings

### Azure and Structured Output

- Service-level Azure failures broadly fall back to mock and do not crash the
  normal route. This is verified with mocked failures.
- Failure diagnostics are not retained in the observation, which helps avoid
  secret leakage but makes operational diagnosis difficult.
- Malformed JSON falls back to mock. Known tags and numeric ranges are filtered.
- An empty Azure tag list is converted to `other`, even though the prompt says an
  empty list represents no visible deterioration. That can create a nonzero tag
  weight if accepted by the reviewer.
- The service relies on prompt-requested JSON rather than a strict response
  schema. Valid non-object JSON and several unusual response shapes are not
  directly handled in the provider's final parsing block, although the outer
  service wrapper catches many resulting exceptions and falls back.
- There is no retry/backoff. Synchronous Azure work runs inside a synchronous
  request path and can occupy the server until timeout.
- `apply_ai_analysis_result` checks for failed provider name `azure_openai`, while
  successful provider values are `azure:<deployment>` and provider failures
  normally return `mock`; the explicit failed branch is effectively inconsistent
  with the provider contract.

### Database, Reports, and State

- Empty dashboard behavior is tested and passes.
- SQLite file integrity is `ok`. `create_all` still cannot perform general schema
  evolution, but the tested startup helper handles the July status column and
  legacy image backfill idempotently without changing existing `Pending` rows.
- Risk Case creation commits the case before report generation and commits the
  report path afterward. A report-write failure can leave a case without a report
  while returning an error.
- Status update also commits before regenerating the report. A write failure can
  persist state while the request fails.
- Report GET endpoints write files and commit database changes.
- No optimistic locking or transaction strategy protects concurrent review,
  analysis, case creation, or status updates.
- Current free disk space is only about 3.4 GiB, and uploads/reports have no
  retention limit.

### Demonstration Data

- Seed constants are stable and idempotency is based on site name and observation
  notes.
- Timestamps are relative to run time, IDs depend on existing data, and reports
  are regenerated, so the full artifact set is not byte-for-byte deterministic.
- Seed analysis is hardcoded mock text; it does not invoke Azure or inspect
  images.
- Seed data contains no `ObservationImage` records and covers Needs Review,
  Verified, and Routed, but not every case stage despite its module description.

## 11. Current Limitations

1. Local single-reviewer demonstration only; no trustworthy reviewer identity.
2. No live Azure evidence from this audit and no guarantee of a particular model
   deployment.
3. No current image-backed demo data or captured browser screenshots.
4. Original contributor text/tags/severity are not immutable or reconstructable.
5. Review-before-AI is a status value, not a timestamped identity-backed event.
6. Explicit AI finalization is bypassable through the legacy case endpoint.
7. Sensitive uploads are obscured in UI, not access controlled.
8. Case state changes are assignments, not enforced transitions, and have no
   event history.
9. Final case inputs are not snapshotted; reports can drift from stored scores.
10. Upload validation trusts file extensions and retains EXIF/GPS metadata.
11. Risk weights and thresholds have no source, calibration, or outcome
    validation in the repository.
12. Unqualified tests are not guaranteed offline when local Azure is enabled.
13. No production deployment, HTTPS, backups, rate limiting, monitoring, or
    recovery procedure exists.
14. Documentation contains stale or overstrong statements, including unchanged
    contributor evidence and universally offline tests.

## 12. STS Evidence Gaps

For a science/research judging claim, the repository currently lacks:

- A precise research question and falsifiable hypothesis tied to the implemented
  system.
- A labelled, consented, provenance-recorded heritage image dataset.
- Ground-truth annotations from qualified or clearly defined human raters.
- Inter-rater agreement and a documented annotation protocol.
- Experiments comparing Azure, mock, human-only, and rule-only baselines.
- Accuracy, precision/recall, calibration, false-positive/false-negative, and
  subgroup/site-condition analysis.
- Evidence that confidence values correlate with correctness.
- A justified source and sensitivity analysis for tag weights, severity scale,
  cap, and band thresholds.
- A protocol for repeated trials, model/deployment version capture, prompt
  versioning, and reproducible results.
- Ethics/privacy evidence for photographing sites, cultural sensitivity, EXIF/GPS,
  consent, retention, and cloud transfer.
- Real current multi-image examples and before/after reviewer disagreement data.
- Completed manual records or screenshots proving the current browser workflow.

The present automated tests establish software behavior, not scientific validity
or conservation accuracy.

## 13. YICTE Evidence Gaps

For a working-product/innovation demonstration, the repository currently lacks:

- A completed, current, screenshot-backed end-to-end demonstration record.
- A current demo database with multi-image observations.
- Verified live Azure browser evidence and a clearly captured fallback demo.
- Evidence from representative users that submission and reviewer workflows are
  understandable.
- Accessibility checks, keyboard testing, mobile screenshots, and cross-browser
  verification.
- A credible access model separating contributors from reviewers.
- Safe handling of sensitive images and location metadata.
- A consistent immutable audit trail that judges can inspect.
- Enforced case transitions or a defensible explanation that statuses are labels
  only.
- Backup/reset/recovery instructions that avoid accidental loss of competition
  evidence.
- A reliable offline test command independent of `.env`.
- Reconciled documentation: the current evidence folders contain checklists but
  no screenshots, and several README claims exceed the data model's guarantees.

The no-email/no-auto-routing boundary is clear and should remain explicit rather
than being treated as a missing core implementation.

## 14. Unrelated User Changes That Must Be Preserved

Every path listed under "All Pre-Existing Modified Tracked Files" and "All
Pre-Existing Untracked Files" predates this audit and is user-owned. This includes
the modified SQLite database, all new templates/tests/docs/scripts, root project
documents, and generated case reports. None may be reverted, staged, reformatted,
or folded into a later change without Albert's explicit approval and a fresh
status review.

The audit file is the only new repository path created by this audit. It must not
be confused with the 29 pre-existing untracked paths.

## 15. Recommended Bounded Scope for Codex Prompt 2

Prompt 2 should be limited to **workflow and evidence-integrity hardening**. It
should not add a new frontend stack, production deployment, email, YOLO, a
dataset, or live-service experimentation.

Recommended acceptance scope:

1. Remove or redirect the legacy `/create_case` bypass so every Risk Case has an
   explicit, timestamped AI-finalization decision.
2. Prevent review edits after a Risk Case exists, or introduce an immutable final
   case snapshot so score, band, breakdown, and reports always use the same data.
3. Preserve original contributor notes/tags/severity separately from reviewer
   edits and human-finalized values, using a small additive audit model compatible
   with the repository's schema constraints.
4. Invalidate prior AI output whenever reviewed evidence changes; require a rerun
   before finalization.
5. Replace hardcoded/inferred audit claims with recorded events and derive report
   statements from those events.
6. Deduplicate final tags and add invariant tests for all alternate routes,
   post-case mutation, score/report consistency, and audit-history truthfulness.

Sensitive-media access control and reviewer authentication should be scoped as a
separate security prompt after Albert decides whether the application will ever
be reachable beyond a trusted local machine. Until then, competition data should
be demonstrative and nonprivate.

## 16. Statements That Must Not Currently Be Claimed

Do not currently claim that:

- HeritageRisk AI is production-ready, publicly deployable, secure, or suitable
  for real sensitive submissions.
- Azure OpenAI, GPT-5-mini, or any named deployment is currently connected and
  successfully analyzing images.
- The automated suite can never call Azure under arbitrary local `.env` settings.
- Every observation passes through a human review queue before AI access.
- Every Risk Case has completed the explicit post-AI human-finalization form.
- Contributor evidence remains unchanged or fully auditable.
- `Sensitive` makes files private or inaccessible.
- The report proves a person reviewed the observation before AI analysis.
- Draft -> Needs Review -> Verified -> Routed -> Closed is an enforced transition
  sequence.
- Entering a routing destination sends, emails, forwards, submits, or escalates a
  report to a council or heritage organization.
- The score is validated heritage risk, probability, urgency, structural safety,
  diagnosis, or a professional recommendation.
- Uploaded files are verified images, free of malware, or stripped of EXIF/GPS.
- The current demo database demonstrates multi-image analysis.
- YOLO, a trained heritage model, a labelled dataset, or model-comparison research
  is implemented.
- Automated tests establish scientific accuracy or conservation validity.

## 17. Audit Close-Out

### Files Created

- `competition_baseline.md` only.

### Application Code

Application code, templates, styles, tests, configuration, reports, and database
files were unchanged by this audit. No Git stage, commit, branch, reset, checkout,
or other history operation was performed.

### Test Result

`AZURE_OPENAI_ENABLED=false pytest` from `backend/`: **154 passed, 0 failed,
0 skipped, 133 warnings in 5.60 seconds**; process exit code 0.

### Unresolved Uncertainties

- Whether the configured Azure endpoint/key/deployment are valid and which model
  is deployed.
- Whether a real multi-image browser run succeeds against live Azure under
  current service limits and policies.
- Whether the reviewer-led bypass routes are intentionally trusted or should be
  subject to the same queue.
- Whether current database records are purely demo data; record content was not
  inspected beyond aggregate counts/statuses.
- Whether image evidence exists only on an external photo USB; that device was
  explicitly not scanned.
- Whether competition judges require a local-only demo or a remotely accessible
  application.

### Five Technical Questions Albert Must Answer

1. Will the competition app remain strictly on Albert's trusted local machine, or
   will any contributor, judge, school network, tunnel, or hosted service reach it?
2. What must count as auditable human review: reviewer identity, timestamp,
   immutable before/after values, and an append-only decision history?
3. Should reviewer-led auto-approval and the legacy case endpoint be removed, or
   is there a separately authenticated trusted-reviewer workflow they must serve?
4. Who defined the tag weights, severity scale, cap, and band thresholds, and what
   experiment or expert evidence will validate them for STS claims?
5. What consent, Azure region/retention policy, cultural-sensitivity rule, and
   EXIF/GPS policy governs sending heritage photos and location text to Azure?

### Draft AI-Assistance-Log Entry

```text
Date: 2026-07-14
Tool: OpenAI Codex
Task: Read-only HeritageRisk AI competition baseline audit
Human request: Inspect the actual repository, classify implemented features,
record Git/storage/test evidence, and identify competition gaps without making
application changes.
AI actions: Read repository instructions; inventoried branch, commit, tracked,
modified, staged, untracked, and ignored state; inspected source, templates,
tests, documentation, aggregate local storage, and read-only SQLite metadata;
ran the existing pytest suite with AZURE_OPENAI_ENABLED=false to enforce the
no-network restriction; wrote competition_baseline.md.
External services: None called. Azure/OpenAI connectivity was not tested.
Private images: None opened or copied. External photo USB was not scanned.
Result: 154 tests passed, 0 failed, 0 skipped; live Azure remains unverified.
Repository changes: competition_baseline.md only; all pre-existing changes were
preserved and application code was unchanged.
Human verification required: Confirm feature classifications, test evidence,
workflow/security conclusions, and the bounded scope before Prompt 2.
```

## Human Approval Required

- Confirm the baseline accurately describes the application.
- Correct any false working/partial/mock classification.
- Confirm the recorded test result.
- Confirm that no user changes were overwritten.
