# Claims Traceability

Cross-check date: 2026-07-24

Documents checked:

- `docs/description-yicte.md`
- `docs/description-sts.md`

Required terms checked: `immutable`, `signature`, `review queue`, `frozen`,
`authenticated`, `audit`, `removed`.

| Term | Claim in derived descriptions | Implemented behavior | Test evidence |
|---|---|---|---|
| immutable | Risk Cases use an application-level write-once evidence/scoring snapshot, while the descriptions state that the database does not enforce JSON or image-file immutability. | `RiskCase.final_snapshot` in `backend/app/models.py`; snapshot builders in `backend/app/provenance.py`; case/report rendering in `backend/app/main.py`, `backend/app/reports.py`, `backend/app/templates/case_detail.html`, and `backend/app/templates/case_report.html`. No route updates the stored snapshot after creation. | `backend/tests/test_provenance.py`; stable report assertions in `backend/tests/test_reports.py`. |
| signature | Uploaded JPEG/PNG/WEBP files are checked by file signature and size before metadata-stripped storage. | `image_format_from_signature`, `sanitize_image_content`, and `save_upload_image` in `backend/app/main.py`. | `backend/tests/test_upload_security.py` covers PNG-as-JPG rejection, text-as-PNG rejection, oversize rejection, EXIF/GPS removal, and orientation preservation. |
| review queue | Public submissions enter the human review queue as `Pending`; reviewers approve/reject/sensitive-mark before AI. | `HumanReviewStatus` in `backend/app/models.py`; public submission and review routes in `backend/app/main.py`; review templates in `backend/app/templates/`. | `backend/tests/test_review_queue.py`, `backend/tests/test_review_actions.py`, and smoke coverage in `backend/tests/test_mvp_smoke.py`. |
| frozen | The STS description explicitly says the stored hash does not prove the exact rendered request was frozen because dynamic notes and image-id content are excluded. | `analysis_prompt_configuration` and `analysis_prompt_sha256` in `backend/app/services/providers/azure_openai_provider.py`; `AssessmentSession.prompt_sha256` in `backend/app/models.py`; `scripts/run_experiment.py`. | `backend/tests/test_experiment_scripts.py` proves hash consistency for the recorded static configuration, not coverage of dynamic request content. |
| authenticated | Reviewer actions use an authenticated signed session; public submission remains unauthenticated by design. | Auth helpers in `backend/app/auth.py`; session middleware and guarded reviewer routes in `backend/app/main.py`; login template in `backend/app/templates/reviewer_login.html`. | `backend/tests/test_reviewer_auth.py`; route-gate coverage in `backend/tests/test_ai_analysis_gate.py`, `backend/tests/test_site_ai_intake.py`, and `backend/tests/test_mvp_smoke.py`. |
| audit | The audit trail is partial: status transitions are evented; corpus audit tooling computes metadata/hashes; re-audit did not call live Azure. | `CaseEvent` in `backend/app/models.py` and status route in `backend/app/main.py`; corpus audit script in `scripts/audit_corpus.py`; Azure verifier in `scripts/verify_azure.py`. | `backend/tests/test_case_status_transitions.py`; `backend/tests/test_corpus_scripts.py`; `backend/tests/test_verify_azure_script.py`. |
| removed | The legacy single-image site upload route and template were removed. | No active `/sites/{id}/observations/new` or `/sites/{id}/observations` route remains in `backend/app/main.py`; `backend/app/templates/observation_new.html` is deleted. | `backend/tests/test_reviewer_auth.py` and smoke/route tests use public multi-image submission or authenticated reviewer-led intake instead. |
| audit | Research analysis reports state asset independence and provide metrics tables; they are analysis outputs, not completed real-corpus results. | Pure functions in `research/analysis/metrics.py`; Markdown rendering in `research/analysis/reporting.py`; CLI in `scripts/analyze_experiment.py`. | `backend/tests/test_research_analysis.py` verifies hand-computed F1, Cohen's kappa, paired deltas, confidence calibration, repeatability, and generated output files. |

The checked descriptions also list remaining limitations where implementation is
partial: one shared reviewer credential, public upload/report URLs, no complete
append-only review log or review timestamp, compatibility finalization without
mandatory per-indicator decisions, authenticated intake/seed paths that bypass
`Pending`, unpreserved Azure transport/configuration failures, seeded later
statuses without transition events, report GET writes, no committed live-Azure
results, no committed real corpus or human labels, and no validated risk model.
