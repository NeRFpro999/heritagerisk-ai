# MVP Demo Evidence Screenshots

Capture these screenshots manually for the 2026-06-06 HeritageRisk AI MVP demo.

Do not add fake screenshots. Each image should show the real app running in the browser.

## Screenshot List

### 01_dashboard.png

- Page/action: The main dashboard at `http://127.0.0.1:8000/` after demo data is loaded.
- Why it matters: Shows the MVP overview, site count, observation count, risk cases, and the demo entry point.
- Invalid or confusing if: The page is blank, demo data is missing, stats are clearly zero after seeding, or browser error messages are visible.

### 02_site_detail.png

- Page/action: A seeded site detail page, such as `Old Stone Church`, with observations visible.
- Why it matters: Shows that a heritage site can hold observations and risk cases.
- Invalid or confusing if: The wrong page is shown, the site has no observations, or key buttons like `+ Add Observation` are missing.

### 03_observation_upload.png

- Page/action: The `Add Observation` form for a site, with photo upload, notes, damage tags, severity, and `Save Observation`.
- Why it matters: Shows how a user adds visible-risk evidence to a heritage site.
- Invalid or confusing if: The form is empty but cropped so fields are missing, the browser is on the wrong site, or required controls are not visible.

### 04_ai_analysis_result.png

- Page/action: Observation detail page after clicking `Run AI Analysis`, showing the `MOCK / FALLBACK` result.
- Why it matters: Shows the MVP mock AI flow and reinforces that AI suggests visible indicators only.
- Invalid or confusing if: AI status still says `Not run`, the result is hidden below the fold, or the screenshot implies a final professional diagnosis.

### 05_risk_case_detail.png

- Page/action: Risk case detail page after clicking `Create Risk Case`.
- Why it matters: Shows the calculated risk score, risk band, status, observation evidence, and case workflow.
- Invalid or confusing if: The case page is missing the score or risk band, shows the wrong case, or displays an app error.

### 06_status_update.png

- Page/action: Case detail page after changing the case status, for example to `Verified` or `Routed`.
- Why it matters: Shows that a human reviewer can update and track the case status.
- Invalid or confusing if: The status did not change after saving, the selected status is unclear, or route text is cut off when it matters.

### 07_evidence_report.png

- Page/action: Evidence report page opened from `View Report` on a risk case.
- Why it matters: Shows that the MVP creates a readable evidence report from the site, observation, AI result, and risk case.
- Invalid or confusing if: The report is blank, the wrong case report is shown, the safety note is missing, or the Markdown content is unreadable.

## Capture Notes

- Browser:
- App URL:
- Demo database state:
- Screenshot date/time:
- Any issues noticed:
