# HeritageRisk AI — Research Log

Log of technical decisions, findings, and direction changes.
Most recent entry first.

Older entries record the state and decisions at their dates. Later entries and
`competition_baseline.md` supersede historical implementation claims.

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

The script creates `observation_images`, backfills existing single-image values from `observations.image_path` or the current `observations.image_filename`, adds `human_review_status`, and removes the old single-image column through a shadow-table rebuild when needed.

Existing observations are marked `ApprovedForAI` during migration so historical records do not enter the new human review queue. New records default to `Pending`.

The live database was not migrated as part of this entry; the script was checked with a dry run and a committed migration against a temporary database copy.

---

## Entry #1 — 2026-06-17

### Current MVP Summary

The MVP is working and all 105 tests pass. The full pipeline runs:

- Site creation → observation upload (single image + notes) → AI analysis (mock or Azure)
- Rule-based risk scorer: tag weights × severity, capped at 100, banded Low/Medium/High
- Evidence report: 7-section Markdown file generated on disk, viewable as HTML, downloadable
- Case status workflow: Draft → Needs Review → Verified → Routed → Closed
- Azure OpenAI Vision is implemented and falls back safely to mock when credentials are absent

The stack is FastAPI + SQLAlchemy 2.0 + SQLite + Jinja2 + custom CSS. Dependencies are pinned. No Alembic migrations — schema is created with `Base.metadata.create_all()` and DB is recreated when models change.

### Competition Goal

Submit HeritageRisk AI to YICTE / STS Victoria in July 2026. The project demonstrates:
1. A practical AI-assisted triage tool for a real problem (heritage site deterioration)
2. Responsible AI design: human-in-the-loop, no final decisions, safe failure modes
3. A working software pipeline with tests and evidence reports

After July, develop further for AUSSEF / ISEF with a YOLO-based vision component and a labelled dataset.

### Known Gaps

1. **Single image per observation.** The data model (`Observation.image_filename` is a single column; `damage_tags` is a CSV string) does not support multi-image sessions. This is the biggest schema gap for the July target.

2. **No schema migrations.** Adding or changing model columns requires recreating and reseeding the database. There is no Alembic configuration. This is acceptable for a demo but must be handled deliberately when schema changes happen.

3. **No explicit human review step in the UI.** The status workflow exists but there is no dedicated review UI that separates "AI proposed" from "human confirmed". The July target needs this for multi-image sessions.

4. **`routers/` is empty.** All 340 lines of routes are in `main.py`. This is fine now but will become hard to maintain as features grow.

5. **No dataset yet.** The YOLO path and AUSSEF submission need a labelled heritage image dataset. This does not exist yet.

6. **`datetime.utcnow()` deprecation warnings** in 38 test runs. Not breaking, but will need updating.

7. **Pillow is installed but not used** by the app code. It was added for potential image preprocessing and is available for future use.

8. **Test coverage has one gap:** `seed()` as a DB-level integration function is not directly tested. `test_seed.py` tests the constants and scoring logic, but not the actual DB writes. The smoke test exercises seed via the route.

### Immediate Next Steps

1. Write `PROJECT_CHARTER.md`, `RESEARCH_LOG.md`, `TECHNICAL_SCOPE.md` (today)
2. Add `test_seed_db.py` integration test for the `seed()` function before touching the schema
3. Design the `AssessmentSession` + `Image` schema additively (new tables, do not modify `Observation`)
4. Implement multi-image upload and storage with no AI changes yet
5. Extend AI layer for session-level analysis as a new function
6. Add human review step to the workflow and UI
7. Update evidence reports for multi-image sessions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Schema changes break existing tests | Medium | High | Add integration tests first; add new tables only, don't modify `Observation` |
| Azure OpenAI credentials unavailable for demo | Low | Low | Mock fallback always works |
| Scope creep before July | Medium | High | Stay in scope per `PROJECT_CHARTER.md`; no YOLO, no accounts, no public upload |
| YOLO dataset not ready for AUSSEF | Medium | Medium | Design the provider interface now so YOLO slots in later |
| `datetime.utcnow()` breaks on Python upgrade | Low | Low | Batch-fix after July |

### Decisions Made (2026-06-17)

- **Confirmed: add new tables, do not mutate `Observation`.** The existing single-image path should keep working unchanged throughout the multi-image build. New `AssessmentSession` and `Image` tables sit alongside, not replacing, the current model.

- **Confirmed: no Alembic for now.** Schema changes are handled by deliberate DB recreate + reseed, documented clearly. Alembic adds complexity that is not worth it at this stage.

- **Confirmed: YOLO is AUSSEF scope, not July scope.** Do not start YOLO work before the July multi-image MVP is complete and tested.

- **Confirmed: no user accounts, no cloud deployment, no major framework change** before July. The app is a local demo tool.

- **Confirmed: mock AI fallback must remain the default** and must pass all safety checks regardless of whether Azure or YOLO is connected.
