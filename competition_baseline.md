# HeritageRisk AI Competition Baseline Re-Audit

Audit date: 2026-07-24 (Australia/Melbourne)
Repository: `/Users/emmamuhi/Desktop/heritagerisk-ai`
Audit mode: local code/test review, no live Azure call, no private-photo audit

This file replaces the historical July baseline with the current verified code
state. Resolution references identify the commit that completed earlier
behavior; a current uncommitted task cites its code and test evidence directly
instead of inventing a commit hash.

Final verification command:

```bash
cd backend && AZURE_OPENAI_ENABLED=false pytest -q
```

Final verification result: **232 passed, 579 warnings in 205.86s (0:03:25)**.

## Current Implemented Product Workflow

HeritageRisk AI is a local FastAPI + SQLAlchemy + SQLite + Jinja2 application.
The public workflow is:

1. A contributor submits one to six JPEG/PNG/WEBP images, notes, selected tags,
   and severity. Public submissions are unauthenticated and enter `Pending`.
2. A reviewer signs in with one configured environment credential. Reviewer
   routes use a signed session and CSRF-protected forms.
3. The reviewer approves, rejects, or marks the observation sensitive. Approved
   observations record `reviewed_by` before analysis.
4. AI analysis runs in mock mode by default or Azure mode when explicitly
   configured. New successful proposals use strict schema v2 with per-indicator
   evidence; malformed Azure payloads are stored as failed validation states.
   Operational Azure failures append a failed attempt with a fixed sanitized
   diagnostic and timestamp before the labelled mock fallback is stored as a
   separate attempt. Reviewer and report views show the ordered history.
   One shared provider-identity classifier recognizes both legacy
   `azure_openai` and current `azure:<deployment>` values across routes,
   reports, templates, and scripts.
5. The primary AI-review page offers accept/edit/reject controls for proposed
   indicators before finalization. The authenticated compatibility finalizer
   and optional indicator fields mean this explicit per-indicator sequence is
   not universally enforced.
6. A Risk Case is created with an application-level write-once final
   evidence/scoring snapshot. Case pages and Markdown/HTML reports render from
   that snapshot, not from the mutable Observation.
7. Normal reviewer status updates follow enforced transitions and write
   `CaseEvent` rows. Built-in seed data can create later statuses directly
   without transition events.

## Current Implemented Research Tooling

- Paired experiment tables and scripts exist for `single_medium` versus
  `three_view` analysis sessions. Experiment sessions are separate from
  Observations and Risk Cases. The runner can create repeated sessions with
  zero-based `run_index` values and resumes on the unique
  `(asset, condition, run_index)` key.
- Each new experiment session records two SHA-256 values. The template hash
  covers the rendered system prompt, deployment, and settings actually used by
  the request builder. The rendered-request hash covers the canonical
  per-session Azure-shaped payload, including dynamic notes and image content,
  without storing that raw payload. In mock mode it fingerprints a would-be
  request; only Azure mode transmits it.
- Corpus audit scripts can build metadata manifests, detect duplicate hashes and
  missing files, summarize asset groups, and select complete cleared asset groups
  for experiment manifests. Raw photos are not committed.
- Research analysis functions compute precision/recall/F1, unsupported-claim
  rate, insufficient-evidence rate, paired deltas, Wilcoxon tests, effect size,
  bootstrap confidence intervals, confidence calibration, Cohen's kappa, and
  repeatability from exported CSVs and human-reference labels. Optional
  redacted site labels flow from experiment manifests through
  `ExperimentAsset` and both CSV row types, allowing site counts and
  largest-site asset share to be calculated once per physical asset.

No real 1,120-photo corpus manifest, live-Azure experiment output, or research
performance conclusion is committed.

## Re-Audit of Previously Listed Limitations

| Previously listed limitation / gap | Current status | Reference | Evidence |
|---|---|---|---|
| Multi-image submission was missing or incomplete. | RESOLVED | `5d538f9` | `ObservationImage` model and multi-image routes/templates were implemented in `5d538f9`; coverage followed in `779596d`. |
| Public submissions did not reliably enter a human review queue. | RESOLVED | `5d538f9` | Public submission sets `Pending`; the queue and workflow were implemented in `5d538f9` and covered in `779596d`. |
| Reviewer-led intake and reviewer actions were unauthenticated. | RESOLVED for reviewer routes | `45431d9` | `app/auth.py`, session middleware, guarded routes in `main.py`, and `tests/test_reviewer_auth.py`. Public contribution remains intentionally unauthenticated. |
| Reviewer-led intake and browser seeding bypass `Pending`. | STILL OPEN (authenticated, by design) | N/A | Authenticated `POST /sites` creates image-backed observations as `ApprovedForAI` and analyzes them directly; authenticated `POST /seed` creates pre-approved records. Public submissions still enter `Pending`. |
| CSRF protection was absent. | RESOLVED | `45431d9` | Shared CSRF helper/template and missing-token rejection tests in `tests/test_reviewer_auth.py`. |
| Legacy single-image upload route bypassed the review design. | RESOLVED | `45431d9` | `/sites/{id}/observations/new`, `/sites/{id}/observations`, and `observation_new.html` are removed; route/tests migrated. |
| Upload validation trusted filename extensions. | RESOLVED | `45431d9` | `image_format_from_signature`, `save_upload_image`, and `tests/test_upload_security.py` reject suffix/signature mismatches. |
| EXIF/GPS metadata was not stripped. | RESOLVED | `45431d9` | `sanitize_image_content` applies `ImageOps.exif_transpose` and re-encodes metadata-free; tests cover GPS removal and orientation. |
| Reviewer edits overwrote contributor-original evidence. | RESOLVED for new rows | `45431d9` | `Observation.contributor_original`, provenance helpers, and `tests/test_provenance.py`. Historical rows can remain `NULL`. |
| AI proposal and reviewer-final values were conflated. | RESOLVED for current proposal | `45431d9` | AI raw/structured fields stay separate from `ai_review_decision`; regression tests prove reviewer edits leave AI bytes unchanged. Prior AI attempts are not retained as full revisions. |
| Explicit AI-output review is bypassable through authenticated finalization paths. | STILL OPEN | N/A | `POST /observations/{id}/create_case` synthesizes a review decision without explicit per-indicator choices, and `POST /observations/{id}/create_risk_case` accepts omitted indicator arrays. |
| RiskCase score/report breakdown could drift after Observation edits. | RESOLVED for snapshotted cases | `45431d9` | `RiskCase.final_snapshot`; case/report rendering from snapshot; provenance/report tests. Legacy cases without snapshots expose limited detail. |
| Reviewer/finalizer identity was inferred rather than recorded. | RESOLVED for new review/finalization events | `45431d9` | `Observation.reviewed_by`, `RiskCase.finalized_by`, snapshot identity fields, auth tests, report tests. One shared credential is not individual identity. |
| Observation pre-AI review has no review timestamp or append-only review event. | STILL OPEN | N/A | Review actions stamp `reviewed_by`, but `Observation` has no `reviewed_at` column and no append-only review-event record; later review edits overwrite the working fields. |
| RiskCase statuses were free labels, not transitions. | RESOLVED for the normal status route | `45431d9` | `app/case_status.py`, status-route enforcement, `CaseEvent`, and `tests/test_case_status_transitions.py`. Direct seed insertion remains a documented exception. |
| Routed status did not require destination. | RESOLVED for the normal status route | `45431d9` | Transition validation rejects Routed without destination; tested in `tests/test_case_status_transitions.py`. |
| Case event history did not exist. | RESOLVED for normal status transitions | `45431d9` | `CaseEvent` table and report rendering. Review edits, AI reruns, seeded statuses, and report generation are not a complete append-only event history. |
| Built-in seeded later statuses have no transition events. | STILL OPEN | N/A | `app.seed` assigns case statuses directly and creates no `CaseEvent` rows. Normal reviewer status updates remain transition-enforced, while `scripts/seed_demo.py` separately exercises evented transitions. |
| Demo database had mock-only, non-image-backed evidence. | RESOLVED as tooling, STILL OPEN as committed data | `e89b79c` | `scripts/seed_demo.py` can rebuild from private `demo_assets/`; tests cover mock seeding. No private demo photos or generated DB are committed. |
| Live Azure behavior was unverified. | STILL OPEN | N/A | `scripts/verify_azure.py` exists and refuses missing env, but no live Azure result is committed or claimed. |
| Azure transport/configuration failures are not preserved as failed attempts. | RESOLVED for new application analyses | Current code: `AIAnalysisRecord`, `tests/test_ai_failure_history.py` | Operational configuration/import/image/transport/API failures store an ordered failed Azure record with a fixed sanitized diagnostic and timestamp, followed by a separate `mock` record. The active proposal remains labelled mock. Malformed JSON remains one failed validation record without fallback. |
| AI output lacked per-indicator evidence and insufficient-evidence outcome. | RESOLVED | `45431d9` | `app/ai_schema.py`, v2 Azure prompt, v2 mock, UI/report rendering, `tests/test_ai_schema_v2.py`. |
| Invalid Azure schema could be silently coerced. | RESOLVED | `45431d9` | Strict v2 validation stores failed validation state with sanitized raw payload; tests cover invalid indicator type. |
| Paired experiment data model did not exist. | RESOLVED | `57f9bd0` | `ExperimentAsset`, `AssessmentSession`, migrations, `scripts/run_experiment.py`, `tests/test_experiment_scripts.py`. |
| `select_assets.py` held-out rows could not be consumed directly by the experiment runner. | RESOLVED | Current code: `scripts/run_experiment.py`, `tests/test_experiment_scripts.py` | `--asset-set pilot` (default), `held_out`, and `all` select the corresponding split rows; each new `AssessmentSession.settings` records the selected set. Tests cover 2 pilot and 3 held-out assets. |
| Experiment export dropped `site_label`, leaving site concentration empty/NaN. | RESOLVED | Current code: `ExperimentAsset.site_label`, `scripts/run_experiment.py`, `scripts/export_results.py`, `research/analysis/metrics.py`, `tests/test_experiment_scripts.py`, `tests/test_research_analysis.py` | The nullable redacted label is migrated and persisted, emitted on session and indicator rows, retained by the loader, and counted once per physical asset. A three-asset/two-site regression verifies `{site-north: 2, site-south: 1}` and a non-NaN Markdown share. |
| The `(asset_id, condition)` constraint blocked native repeatability runs. | RESOLVED | Current code: `AssessmentSession.run_index`, `scripts/run_experiment.py`, `scripts/export_results.py`, `research/analysis/metrics.py`, `tests/test_database_migration.py`, `tests/test_experiment_scripts.py`, `tests/test_research_analysis.py` | SQLite migration preserves legacy sessions at index 0 and replaces the old constraint with `(asset_id, condition, run_index)`. `--repeat-runs 2` creates four sessions for one asset, resumes without duplicates, exports both indices, and feeds hand-computed agreement through the loader. Primary condition metrics use index 0; repeatability uses all runs. |
| E11: Frozen analysis configuration was asserted, not recorded. | RESOLVED | Current code: `analysis_prompt_template_sha256`, `analysis_rendered_request_sha256`, `AssessmentSession.prompt_template_sha256`, `AssessmentSession.rendered_request_sha256`, `scripts/run_experiment.py`, `scripts/export_results.py`, `tests/test_ai.py`, `tests/test_experiment_scripts.py`, `tests/test_database_migration.py` | New sessions store a template/configuration hash and a per-session canonical rendered-request hash. `PROMPT_SETTINGS` contains only transmitted request arguments (`max_completion_tokens`); temperature and schema version are not recorded as request settings because they are not sent. The raw request is not stored. Legacy `prompt_sha256` values migrate without recomputation to the renamed template field while the unreconstructable rendered hash remains `NULL`. |
| Experiment sessions could enter the community workflow. | RESOLVED | `57f9bd0` | Experiment models/scripts are separate from Observation/RiskCase routes; tests assert session behavior only. |
| research/ was empty while corpus audit claims existed. | RESOLVED as tooling/schema | `2d4af01` | `research/corpus/MANIFEST.schema.json`, `scripts/audit_corpus.py`, `scripts/select_assets.py`, `tests/test_corpus_scripts.py`. STILL OPEN for real 1,120-photo corpus output. |
| Statistical analysis code for STS metrics was absent. | RESOLVED as code | `6c30724` | `research/analysis/metrics.py`, `scripts/analyze_experiment.py`, `tests/test_research_analysis.py`. STILL OPEN for real-corpus results. |
| Corpus photos, exact site locations, and sensitive evidence privacy were not access-controlled. | STILL OPEN | N/A | Upload URLs and read-only evidence routes remain public; sensitive content is hidden in selected templates only. Raw research photos must stay outside Git. |
| Reviewer identity was not individual/account-level. | STILL OPEN | N/A | One shared reviewer credential is implemented; no user accounts, roles, recovery, or throttling. |
| Complete append-only audit history did not exist. | STILL OPEN | N/A | Status transitions have `CaseEvent`, and analyses now have ordered attempt metadata. Review edits, every field change, complete prior AI proposal revisions, and report GET writes are not complete append-only events. |
| Working evidence could change after AI analysis without invalidating the current proposal. | STILL OPEN | N/A | Layers remain separate, but no automatic invalidation/rerun requirement exists for post-analysis working edits before finalization. |
| Older rows cannot reconstruct provenance. | STILL OPEN by design | N/A | Additive migrations leave historical unknowns as `NULL`; the app does not fabricate old originals, identities, or snapshots. |
| Risk weights/thresholds lacked validation. | STILL OPEN | N/A | Scoring remains a transparent heuristic with tests, not an empirically validated conservation-risk model. |
| No production deployment/security hardening. | STILL OPEN | N/A | No HTTPS deployment, backups, rate limiting, monitoring, malware scanning, retention workflow, or private media delivery. |
| Public report GET routes mutate files and database state. | STILL OPEN | N/A | Unauthenticated `GET /cases/{id}/report` and `/report.md` regenerate report files, assign `report_path`, and commit the database. |
| Automated tests could be affected by local Azure settings. | PARTLY RESOLVED in documented command | `17c83d9` | The documented verification command explicitly sets `AZURE_OPENAI_ENABLED=false`; unqualified local commands may still read local environment. |

## Remaining Limitations That Must Be Disclosed

1. The app is a local student competition demonstration, not a production
   service.
2. Public contributors are unauthenticated by design. Reviewer actions use one
   shared credential, not individual accounts or roles.
3. Reviewer-led intake and browser seeding are authenticated but intentionally
   bypass the public `Pending` queue.
4. Observation review records `reviewed_by` but has no review timestamp or
   append-only review-event row.
5. The compatibility finalizer and optional indicator fields do not universally
   enforce explicit per-indicator accept/edit/reject decisions.
6. Uploaded media and read-only case/report pages remain publicly reachable to
   anyone who knows the URL.
7. Sensitive observations are suppressed in selected UI/report locations, but
   files are not access-controlled.
8. Normal status transitions and AI attempt outcomes are evented, but built-in
   seeded later statuses have no events; review edits, complete prior AI
   proposal revisions, and report generation are not a complete append-only
   audit log.
9. Live Azure operation is implemented and mock-tested, but no live Azure
   response is committed as evidence.
10. Public report GET routes regenerate files and commit `report_path`.
11. No real corpus manifest, raw image dataset, human labels, completed paired
   experiment output, or statistical conclusion is committed.
12. Experiment blinding is managed externally and is not recorded. Legacy
    experiment rows retain their earlier hash under the renamed template field
    without recomputation and have
    `rendered_request_sha256 = NULL`.
13. Risk scoring weights and thresholds are unvalidated heuristics.
14. Historical database rows can have `NULL` provenance and identity fields.
15. There is no production deployment, HTTPS, backup, malware scanning, rate
    limit, retention, or recovery procedure.

## Statements That Must Not Be Claimed

- Do not claim the app has individual reviewer accounts or production-grade
  authentication.
- Do not claim every observation path enters `Pending` or every Risk Case
  finalizer requires explicit per-indicator decisions.
- Do not claim sensitive or uploaded files are private.
- Do not claim every review has a timestamp/event, every seeded status has a
  transition event, or report GET routes are read-only.
- Do not claim Azure has been live-verified in the committed evidence.
- Do not claim AI attempt metadata is a complete immutable copy of every prior
  AI response or exception body.
- Do not claim a 1,120-photo corpus or real statistical results exist in Git.
- Do not claim the raw rendered request is stored, that a mock fingerprint was
  transmitted to Azure, that legacy sessions have a rendered-request hash, or
  that experiment blinding is recorded.
- Do not claim the score is a validated probability, urgency, structural-safety
  diagnosis, or professional recommendation.
- Do not claim the audit trail captures every edit and every complete prior AI
  proposal.
- Do not claim historical rows have reconstructed provenance.
