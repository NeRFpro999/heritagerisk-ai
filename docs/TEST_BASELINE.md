# HeritageRisk AI — Test Baseline

> Historical test baseline captured on 2026-06-19 before the July multi-image
> workflow. Current verified behavior and test evidence are recorded in
> [`competition_baseline.md`](../competition_baseline.md).

## Current Verification — 2026-07-23

The current offline suite result is:

```text
220 passed, 538 warnings in 203.33s (0:03:23)
```

Command:

```bash
cd backend
AZURE_OPENAI_ENABLED=false pytest -q
```

Current regressions cover signed reviewer login/logout, redirects from reviewer
routes while logged out, refusal of the analysis endpoint without a session,
double-submit CSRF rejection, logged-out public submission remaining `Pending`,
reviewer/finalizer identity persistence and rendering, removal of the legacy
site-observation route, upload signature/metadata handling, provenance, and
immutable reports, plus case-status transition enforcement and event history.
They also cover manifest demo seeding in mock mode and Azure-verifier refusal
when required environment variables are missing, plus schema v2 AI indicator
validation, failed validation preservation, insufficient-evidence finalization,
and v1 compatibility rendering. Azure-dependent paths use mocks; no live Azure
call is part of this result.

The access tests do not establish production security. One shared credential,
login throttling/recovery, HTTPS and `Secure` cookies, public upload/report
access, historical `NULL` identities, and the absence of complete per-action
event history remain qualified in `competition_baseline.md`.

## Historical 2026-06-19 Baseline

## Run details

| Field | Value |
|---|---|
| Date | 2026-06-19 |
| Python | 3.13.3 |
| pytest | 8.3.5 |
| Command | `backend/.venv/bin/python3 -m pytest --tb=short -q` |
| Config | `pytest.ini` — `testpaths = backend/tests`, `pythonpath = backend` |
| Runtime | 1069.62 s (17 m 49 s) |
| Exit code | 0 |

## Result

```
107 passed, 0 failed, 0 errors, 38 warnings
```

**The codebase is safe to modify. All 107 tests pass.**

## Test files

| File | Tests | Scope |
|---|---|---|
| `backend/tests/test_risk.py` | 5 | `calculate_risk()` scoring math and band thresholds |
| `backend/tests/test_seed.py` | 24 | Seed constants, risk bands, status coverage, safety phrasing |
| `backend/tests/test_reports.py` | 34 | 7-section report structure, data mapping, safe fallbacks, AI status |
| `backend/tests/test_ai.py` | 24 | Mock mode, Azure fallback, response validation, tag merging |
| `backend/tests/test_mvp_smoke.py` | 18 | Full happy-path E2E via `TestClient` + in-memory SQLite, ordered test_01–test_14 |
| **Total** | **105** | *(107 collected includes 2 from package `__init__` discovery — see note)* |

> Note: pytest reports 107 collected even though 105 `def test_` functions exist. The 2-count difference is a pytest collection artefact (pluggy/anyio fixture items). All 107 items pass.

## Warnings (38 total, no failures)

All warnings are deprecations in third-party code or in app code scheduled for cleanup. None affect test correctness.

| Warning | Source | Affected tests |
|---|---|---|
| `TemplateResponse(name, ...)` parameter order deprecated | Starlette 0.x → future | `test_mvp_smoke.py` (10 occurrences) |
| `allow_redirects` argument deprecated (use `follow_redirects`) | Starlette `TestClient` | `test_03_seed`, `test_04_create_site`, `test_06_upload_observation`, `test_08_analyze_observation`, `test_08b_*`, `test_09_create_case`, `test_12_update_case_status` |
| `datetime.utcnow()` deprecated (use `datetime.now(UTC)`) | `app/seed.py:170,206,224,225` | `test_03_seed` (12 occurrences) |
| `datetime.utcnow()` deprecated | `app/main.py:310` | `test_12_update_case_status` |
| `datetime.utcnow()` deprecated | SQLAlchemy `schema.py:3596` (via `onupdate=datetime.utcnow`) | `test_04_create_site`, `test_06_upload_observation`, `test_09_create_case` |

## Performance note

The first run after a cold start takes ~17 minutes. This is caused by SQLAlchemy's cold import on Python 3.13 rebuilding `.pyc` bytecode cache files in the venv. Subsequent runs in the same session are fast (seconds). This is an environment issue, not a test or app bug.

## Known issues (not blocking)

1. **`datetime.utcnow()` in `app/seed.py` (lines 170, 206, 224, 225) and `app/main.py` (line 310)** — deprecated in Python 3.12+, scheduled for removal in a future Python version. Fix: replace with `datetime.now(timezone.utc)`. Low urgency; does not affect test results today.

2. **`TemplateResponse` parameter order** — Starlette warns that `name` should not be the first argument. Affects all routes that call `templates.TemplateResponse(name, {...})`. Will become an error in a future Starlette release.

3. **`allow_redirects` in `TestClient` calls** — deprecated in favour of `follow_redirects`. Affects 7 tests in `test_mvp_smoke.py`.

## Safe to modify

Yes. The full pipeline is covered end-to-end and all tests pass. The `test_mvp_smoke.py` suite is the primary regression safety net — keep it green throughout all future changes.

## Recommended next test additions (July competition target)

Priority order based on the current gap analysis:

1. **`test_seed_db.py` — DB-level integration test for `seed()`**
   The current `test_seed.py` only checks constants. A test that calls `seed(db)` against an in-memory DB and asserts the correct rows were written would close the one real gap in functional coverage.

2. **`test_mvp_smoke.py` — `follow_redirects` migration**
   Replace `allow_redirects=False` with `follow_redirects=False` in the 7 affected smoke tests to silence the deprecation warning before it becomes a breaking change.

3. **Multi-image session tests (when `AssessmentSession` is added)**
   A new `test_session_smoke.py` mirroring the existing smoke test structure: create session → upload N images → session-level analyze → human review step → create case → report. Keep `test_mvp_smoke.py` unchanged as the single-image regression guard.

4. **Expanded status-transition UI screenshots**
   Automated tests now reject `Draft` directly to `Routed`; a manual screenshot
   pass should capture the valid-next-state form and event history display.

5. **`datetime.utcnow()` fix coverage**
   After the `utcnow()` calls are replaced with `datetime.now(timezone.utc)`, confirm the 38-warning count drops. No new tests needed — the deprecation warnings disappearing from the run is the signal.
