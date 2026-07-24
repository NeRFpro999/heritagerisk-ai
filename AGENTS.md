# HeritageRisk AI — Agent Instructions

HeritageRisk AI is a student competition project (YICTE/STS Victoria July 2026, then AUSSEF/ISEF).
Future coding agents must keep the repository consistent, safe, and readable by a student project team.

---

## Current Project Direction

**Current July 2026 build (working and tested)**
The preserved pipeline now supports one Risk Case per Observation with one to six `ObservationImage` records. The primary public flow is: Site selection or creation → multi-image Observation submission (`Pending`) → submission review → multi-image AI analysis (mock or Azure) → human AI-output review and finalization → immutable Risk Case evidence/scoring snapshot → Markdown/HTML evidence report → manual status and routing. New observations preserve contributor-original notes, tags, severity, and submission time separately from the reviewer working copy and AI proposal.

Reviewer actions use one environment-configured credential, an eight-hour signed
session, and CSRF-protected forms. The legacy site-observation upload route has
been removed. The compatibility case-creation route remains, but it requires a
reviewer session and records the same identity and immutable snapshot as the
primary finalization route. See [competition_baseline.md](competition_baseline.md)
for verified behavior and known limitations.

The research experiment path is separate from the community workflow. It uses
`ExperimentAsset` and `AssessmentSession` rows to run paired `single_medium`
and `three_view` AI analyses against the same physical asset, with prompt
configuration hashes, run metadata, and CSV export for later statistical
analysis. These sessions do not enter the review queue and do not create
`RiskCase` rows.

`research/corpus/` contains metadata-only corpus audit tooling. Raw photographs
must stay outside Git; only schemas, manifests, hashes, and aggregate audit
reports may be committed after privacy/cultural-sensitivity review.
`research/analysis/` contains pure metric functions and a CLI for paired
experiment CSV analysis. Do not present toy-fixture tests as real performance
evidence.

**AUSSEF/ISEF research scope (planned)**
YOLO provider/model work, a completed labelled heritage image dataset, uncertainty-aware evidence fusion, completed live-Azure experiment runs, and provider-comparison conclusions remain unimplemented research targets.

---

## 1. Preserve the Working MVP

The current pipeline (`Site → Observation → RiskCase → Report`) must keep working at every stage of development. New features are additive — built alongside the existing workflow, not replacing it.

Before landing any change that touches `models.py`, `main.py`, `risk.py`, `reports.py`, or `database.py`, confirm that `pytest` still passes. The smoke test file (`tests/test_mvp_smoke.py`) is the regression safety net — treat it as a canary, not something to weaken.

If a schema change is unavoidable: add new tables; do not modify existing columns on `Site`, `Observation`, or `RiskCase` unless there is no other way.

## 2. Keep the App Lean

The stack is FastAPI + SQLAlchemy + SQLite + Jinja2 + vanilla CSS. Do not add:

- A CSS framework (Bootstrap, Tailwind, etc.) unless explicitly requested
- A JS framework or bundler
- A second database engine
- An ORM other than SQLAlchemy
- Redis, Celery, background task queues, or async workers
- A new major Python dependency

unless the user explicitly asks for it and explains why the existing stack cannot do the job.

Code should be readable and maintainable by a student project team. Avoid abstractions that only make sense to the person who wrote them. Three similar lines is better than a premature helper. No multi-layer service classes for single-method objects.

## 3. Avoid Major Rewrites

Do not restructure the whole app to introduce routers, sub-applications, layered architecture, or a different project layout unless the user explicitly asks. Incremental, targeted changes only.

The `app/routers/` package exists and is empty — leave it empty until there is a genuine need to split routes. All routes live in `app/main.py` for now and that is intentional.

## 4. No Hardcoded Secrets

- Never hardcode API keys, Azure endpoints, deployment names, or any credential.
- Never hardcode `REVIEWER_USERNAME`, `REVIEWER_PASSWORD_HASH`, or
  `SESSION_SECRET_KEY`. Reviewer passwords are stored only as supported scrypt
  hashes.
- Never commit `.env`. Add to `.gitignore` if it is ever missing.
- Use `.env.example` for placeholder documentation only.
- Do not print, log, or echo secrets in responses, test output, or documentation.
- If a test needs fake credentials, use clearly fake strings (`"fake-key"`, `"https://fake.openai.azure.com/"`).

## 5. Keep Azure Optional — Mock/Offline Mode Must Always Work

`AZURE_OPENAI_ENABLED` defaults to `false`. The mock keyword scanner (`_mock_analyze` in `services/ai_analysis.py`) is the default AI path and must continue to work with zero credentials and zero network access.

Every Azure error path must fall back to mock — never crash a route. New AI providers follow the same rule: if the provider fails or is unconfigured, fall back to mock and set `ai_analysis_status = "mock"` or `"failed"` accordingly.

When adding a new AI provider, preserve the existing `AIAnalysisResult` return
type and both `analyze_observation_image` (service-level single-image
compatibility) and `analyze_observation_images` (multi-image) entry points. The
single-image upload route itself has been removed.

## 6. All AI Outputs Are Triage Only

Every AI-generated summary, tag list, confidence score, and recommended action is a **visible-risk triage signal for human review only**.

AI output must never claim:
- Structural safety or structural failure
- That a site is safe or unsafe to enter
- That professional inspection is or is not needed
- Legal, emergency, or conservation authority
- A final conservation decision

The required safety statement (used verbatim in tests and reports) is:

> "HeritageRisk AI is for visible risk triage only. It does not replace professional conservation, engineering, emergency, legal, or cultural heritage advice."

This wording appears in `services/ai_analysis.py`, `services/providers/azure_openai_provider.py`, `reports.py`, and the `_safety_note.html` template. Do not change it without updating all locations and the test assertions that check it verbatim.

## 7. Preserve Human Review Gates

The public submission workflow records new observations as `Pending`. The review queue lets a reviewer approve, reject, or mark an observation sensitive and adjust notes, tags, and severity before AI analysis. The analysis route requires `ApprovedForAI`. After analysis, the primary Risk Case route provides a second human review step for final tags, severity, summary, and action before calculating the score.

Public submission remains intentionally unauthenticated. Reviewer-led site
intake, the review queue and decisions, analysis, AI-output review/finalization,
case status changes, and browser seeding require the configured reviewer
session. Every POST form, including public submission and login, carries a
double-submit CSRF token. Do not remove these guards or add a state-changing
POST without the shared CSRF field.

Keep the three provenance layers separate:

- `Observation.contributor_original` is written once when an Observation is created. No review, analysis, finalization, or status route may change it.
- The structured AI fields and `ai_raw_response` are the AI proposal. Reviewer edit, accept, and reject actions must not rewrite them; only an explicit analysis/rerun may replace the current proposal.
- New AI proposals should use `schema_version = "2"` with strict Pydantic
  validation, evidence sufficiency, and per-indicator findings. Invalid v2
  payloads must be stored as failed validation states with sanitized raw payloads
  preserved; do not silently coerce, drop, or clamp model output. Existing v1
  rows remain readable through the legacy aggregate fields.
- `RiskCase.final_snapshot` is the reviewer-accepted evidence and exact scoring record. For snapshotted cases, case pages and both report formats must read final evidence, weights, multiplier, equation, capped score, and band from that snapshot, never recalculate from the live Observation. Legacy cases without a snapshot may show their stored scalar score and band, but detailed provenance must remain unavailable.
- `Observation.reviewed_by` records the configured reviewer identity required
  before analysis. `RiskCase.finalized_by` records the finalizer. Both are copied
  into the immutable case snapshot and rendered from that snapshot in case and
  report views.

Rows created before the provenance columns were introduced can have `NULL` originals or snapshots. Show those values as unavailable; do not fabricate historical provenance from mutable fields. See [competition_baseline.md](competition_baseline.md) for the tested guarantees and legacy limitation.

Contributor-original note text can contain details removed during privacy review. Show it on reviewer comparison pages only; case pages and exported reports must use the reviewed-at-finalization notes and state that original note text is withheld.

Do not add automatic routing, closing, or action. The implemented reviewer
control is deliberately minimal: one shared credential, not individual user
accounts or roles. There is no login throttling or recovery flow. Case status
changes must follow the `app.case_status.ALLOWED_TRANSITIONS` state machine, and
each accepted transition writes a `CaseEvent` with the configured reviewer
identity, timestamp, and optional note. This is a status-transition history only,
not a complete append-only event log for every edit. See
[competition_baseline.md](competition_baseline.md), especially
“Verified End-to-End Workflow,” “Current Limitations,” and “Statements That Must
Not Currently Be Claimed.”

## 8. Add Tests for New Workflow Logic

All new route handlers, risk-scoring changes, AI paths, and report sections need tests before the feature is considered complete.

Test structure to follow:
- Route-level tests: use `TestClient` with an in-memory SQLite DB and patched `UPLOADS_DIR`/`REPORTS_DIR` (see `tests/test_mvp_smoke.py` for the pattern).
- AI service tests: mock settings and OpenAI client; never hit real Azure (see `tests/test_ai.py`).
- Report tests: use `SimpleNamespace` fakes and `patch("app.reports.REPORTS_DIR", tmp_path)` (see `tests/test_reports.py`).
- Pure logic tests: call the function directly with known inputs (see `tests/test_risk.py`).

Run the full suite:

```bash
cd backend && pytest
```

Run the Azure connectivity script only when real credentials are available in `.env`:

```bash
python3 scripts/test_azure_openai.py
```

If a change only updates documentation and touches no app code, state that clearly and skip pytest.

## 9. Prefer Small, Reviewable Changes

One logical change per commit. A change that adds a new table, a change that adds the route, and a change that adds the tests are three commits — not one.

Avoid bundling unrelated fixes, formatting changes, or doc updates with functional changes. It makes review and rollback harder.

## 10. Document Design Changes in RESEARCH_LOG.md

When a change affects project direction, schema design, AI approach, competition scope, or a decision that future sessions need to know about, add a dated entry to `RESEARCH_LOG.md`. Most recent entry first.

An entry should include: what changed, why, and what is now decided. It does not need to describe every line of code changed — that belongs in the commit message.

Changes that do **not** need a log entry: bug fixes, test additions for existing behaviour, formatting, wording corrections, dependency version bumps.

## 11. Do Not Claim Unimplemented Features

Do not add UI text, report sections, seed data descriptions, or documentation that claims a feature works if it is not implemented.

Implemented and tested in the July 2026 build:

- Public submission of one to six images using `ObservationImage` rows attached to one `Observation`
- JPEG/PNG/WEBP suffix-signature validation and orientation-preserving,
  metadata-free Pillow re-encoding on every upload route
- A `Pending` review queue with status filters and approve/reject/sensitive actions
- Multi-image AI request assembly with correctly labelled mock fallback
- Schema v2 AI proposals with per-indicator evidence, strict validation failure
  storage, insufficient-evidence support, and v1 render compatibility
- Human AI-output review before the primary Risk Case creation route
- Contributor-original, AI-proposal, and reviewer-final provenance separation
- Immutable Risk Case scoring snapshots used by case and report views
- Explainable score breakdowns and multi-image evidence reports
- One scrypt-hashed reviewer credential with signed-session login/logout and
  guards on reviewer/admin routes
- Double-submit CSRF validation on every state-changing form POST
- Recorded reviewer/finalizer identity in database fields, immutable case
  snapshots, case pages, and reports
- Enforced Risk Case status transitions with `CaseEvent` history rendered on
  case pages and reports
- Separate paired-experiment tables and scripts for `single_medium` vs
  `three_view` mock/Azure runs, including prompt hashes and CSV export
- Metadata-only corpus audit and cleared-asset selection scripts under
  `research/corpus/`; raw photos remain excluded from Git
- Research analysis functions for precision/recall/F1, unsupported claims,
  insufficient evidence, paired deltas, Wilcoxon/effect size/bootstrap CIs,
  confidence calibration, Cohen's kappa, and repeatability
- Removal of the legacy `/sites/{id}/observations/new` and
  `/sites/{id}/observations` upload routes and their template

Community workflow multi-image evidence still belongs directly to one
`Observation`. Experiment sessions are separate research records and must not be
presented as reviewed community observations or Risk Cases. YOLO detection, an
aggregated site-level risk view, a completed labelled dataset, evidence fusion,
completed live-Azure experiment results, and model-comparison conclusions remain
unimplemented.

Do not overstate the implemented workflow. The Observation working copy remains
editable, prior AI attempts are not retained as complete revisions, and older
database rows can have `NULL` provenance or reviewer identities. The single
credential does not provide individual accounts, roles, recovery, throttling, or
an append-only action history. Local HTTP does not set the session cookie's
`Secure` flag, and upload URLs plus read-only case/report pages remain public.
[competition_baseline.md](competition_baseline.md) records these and the other
limitations, including unverified live Azure behavior.

If a feature is planned but not built, it may appear in `PROJECT_CHARTER.md` and `TECHNICAL_SCOPE.md` as a future target. It must not appear in the app UI, evidence reports, or seed data as if it were working.

## 12. Keep Code Readable for a Student Competition Project

Style rules (these are also enforced by `feedback_refactor_decisions.md` in the project memory):

- No ASCII banner comments (`# ── Section ──────────`). Use blank lines to separate sections.
- No duplicate implementations of the same logic.
- No class with a single method and two private helpers — extract as module-level functions instead.
- Module docstrings: 1–4 lines. State purpose or routing logic only.
- Comments explain *why*, not *what*. A good comment: "# Lazy import — keeps app working without openai installed". A bad comment: `# Create risk case` above three obvious lines.
- No marketing words in UI text: seamless, cutting-edge, revolutionary, leveraging, robust, empowering, platform (as buzzword).
- No multi-paragraph docstrings or 14-line docstring blocks.

---

## Tag Taxonomy

The damage tag set is shared across three files and must stay consistent:

`crack, erosion, graffiti, corrosion, water_staining, vegetation_growth, surface_loss, fire_damage, other`

Files that define or reference this list:
- `app/risk.py` — `TAG_WEIGHTS` (source of truth for scoring)
- `app/services/ai_analysis.py` — `ALLOWED_TAGS`
- `app/services/providers/azure_openai_provider.py` — `ALLOWED_TAGS`

If a tag is added or removed, update all three locations and update the relevant tests.

---

## Quick Reference

| Task | Command |
|------|---------|
| Run the app | `cd backend && python3 run.py` → http://127.0.0.1:8000 |
| Reviewer login | http://127.0.0.1:8000/reviewer/login |
| Seed demo data | Sign in and POST `/seed` from the UI, or `cd backend && python3 -m app.seed` for local CLI seeding |
| Run tests | `cd backend && pytest` |
| Reset database | Delete `data/heritagerisk.db`, then reseed |
| Azure smoke test | `cd backend && python3 ../scripts/test_azure_openai.py` (needs `.env`) |
