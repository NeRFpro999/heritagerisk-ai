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