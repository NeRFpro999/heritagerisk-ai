# HeritageRisk AI Build Log

## Day 1: MVP Stabilisation

Date: 1 June 2026

Goal:
Turn the current FastAPI prototype into a reliable MVP demo flow.

What already works:
- Sites
- Observations
- Image uploads
- Rule-based risk scoring
- AI/mock analysis service
- Risk cases
- Markdown evidence reports
- Demo seed data

Today's focus:
- Test the full workflow
- Fix demo-breaking issues
- Add basic tests
- Improve report and judge-facing explanation

## Technical Debt

- **`datetime.utcnow()` in `reports.py`** — Python 3.12+ deprecates this in favour of
  `datetime.now(timezone.utc)`. The generated report timestamps are UTC strings so the
  change is low-risk, but it should be done before any deployment on Python 3.12+.
  Tracked here so it doesn't get forgotten.

## Smoke Test Checklist

- [ ] Dashboard loads
- [ ] Seed data loads without duplicating badly
- [ ] Site list loads
- [ ] Can create a new site
- [ ] Site detail page loads
- [ ] Can upload JPG/PNG/WEBP image
- [ ] File size limit works
- [ ] Observation detail page loads
- [ ] Mock AI analysis works without Azure key
- [ ] Create case button works
- [ ] Case list loads
- [ ] Case status can be updated
- [ ] Markdown report is generated
- [ ] HTML report renders
- [ ] Raw Markdown download works

---

## 2 June 2026 Manual Smoke Test

Run this checklist in a real browser against `python backend/run.py` before any demo or release.

- [ ] Dashboard loads
- [ ] Seed data loads without bad duplication
- [ ] Site list loads
- [ ] New site can be created
- [ ] Site detail page loads
- [ ] Observation image can be uploaded
- [ ] Observation detail page loads
- [ ] Mock AI analysis works without Azure credentials
- [ ] Risk case can be created
- [ ] Case list loads
- [ ] Case detail loads
- [ ] Case status can be updated
- [ ] HTML evidence report opens
- [ ] Raw Markdown report opens
- [ ] Safety note appears on observation/case/report pages
- [ ] Mock AI is clearly labelled as mock/fallback

## Issues Found

1.
2.
3.
4.
5.

---

## 2026-06-06 — MVP seed data and screenshot evidence

### Goal

Strengthen the MVP demo evidence for the golden path:
Seed -> Dashboard -> Site -> Observation -> AI/mock analysis -> Risk case -> Report.

### Completed

- [x] Confirm duplicate `backend/app/test_risk.py` cleanup.
- [x] Run `pytest`.
- [x] Improve seed data for clear Low, Medium, and High risk examples.
- [x] Create screenshot evidence folder and checklist at `docs/evidence/2026-06-06/README.md`.
- [ ] Run browser smoke test.
- [ ] Capture screenshots in `docs/evidence/2026-06-06/`.
- [ ] Confirm evidence report opens correctly in the browser.

### Test result

- `pytest` was run by Codex.
- Final result: `96 passed, 35 warnings`.

### Issues found

- `backend/app/test_risk.py` did not exist, so no deletion was needed.
- The first seed-data update gave two examples the same severity score; `test_seed.py` caught this. The seed data was adjusted and tests then passed.
- No route/template problems were found while preparing the smoke-test checklist.
- Screenshots have not been captured yet.

### Evidence captured

- [x] Manual smoke-test checklist created: `docs/SMOKE_TEST_CHECKLIST.md`.
- [x] Screenshot capture README created: `docs/evidence/2026-06-06/README.md`.
- [ ] `01_dashboard.png`
- [ ] `02_site_detail.png`
- [ ] `03_observation_upload.png`
- [ ] `04_ai_analysis_result.png`
- [ ] `05_risk_case_detail.png`
- [ ] `06_status_update.png`
- [ ] `07_evidence_report.png`

### Next step

Run the manual browser smoke test, capture the seven screenshots, and confirm the evidence report opens correctly from a generated risk case.

---

## 2026-06-11 — Submission dashboard polish

### Goal

Make the dashboard clearer for YICTE and STS Victoria review by showing the complete MVP workflow, key case counts, safe AI boundaries, and direct navigation actions.

### Completed

- [x] Added dashboard summary cards for sites, observations, risk cases, cases needing review, and priority review cases.
- [x] Added direct dashboard actions for adding sites, viewing sites, uploading an observation when a site exists, viewing risk cases, and seeding demo data.
- [x] Added a visible safety boundary note with human-review wording.
- [x] Added safe AI provider labels without exposing endpoint values, keys, or secrets.
- [x] Added smoke-test assertions for the new dashboard signals.

### Verification

- `pytest` was run by Codex.
- Final result: `104 passed, 36 warnings`.

---

## 2026-06-11 — Site detail hub polish

### Goal

Make each site detail page work as the central hub for a heritage place, showing the route from site evidence to observation, risk case, and report.

### Completed

- [x] Added latest risk band and latest case status to the site summary.
- [x] Added a visible safety reminder for visible-risk triage evidence and human review.
- [x] Improved observation cards with image filename, notes preview, tags, severity, AI status/provider, and case/report actions.
- [x] Added a dedicated risk-case section with score, band, status, routed-to field, report link, and observation link.
- [x] Added smoke-test assertions for the site hub content.

### Verification

- `pytest` was run by Codex.
- Final result: `105 passed, 37 warnings`.

---

## 2026-06-11 — Observation upload safety polish

### Goal

Make the observation upload form clearer and safer for YICTE and STS Victoria review, without adding multi-image upload or professional diagnosis language.

### Completed

- [x] Added safe photo-taking guidance for public or permitted areas.
- [x] Clarified accepted image types and the 10 MB image-size limit.
- [x] Reworded notes, visible indicators, and severity as visible-risk triage only.
- [x] Added severity guidance from 1 to 5.
- [x] Added surface loss and fire damage to the visible-indicator taxonomy.
- [x] Improved unsupported image-type validation text.
- [x] Added smoke-test assertions for upload guidance and validation copy.

### Verification

- `pytest` was run by Codex.
- Final result: `107 passed, 38 warnings`.
- `pytest backend/tests/test_mvp_smoke.py` was run by Codex.
- Final MVP smoke result: `18 passed, 38 warnings`.
