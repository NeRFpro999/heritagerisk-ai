# HeritageRisk AI Legacy MVP Smoke-Test Checklist

> Historical record from the June 2026 single-image MVP. It does not describe
> the current July multi-image review workflow. See
> [`competition_baseline.md`](../competition_baseline.md) for current verified
> behavior and limitations.

Use this checklist before a demo or MVP stabilisation session. It is a manual browser smoke test for the current golden path:

Seed data -> dashboard -> site page -> observation upload -> mock AI analysis -> create risk case -> update case status -> open evidence report.

## Setup

Run from the repo root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Mock AI mode is the default. For this smoke test, leave `AZURE_OPENAI_ENABLED` unset or set it to `false`.

## Start the app

From the repo root:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
```

Open the app in a browser:

```text
http://127.0.0.1:8000
```

## Test Notes

- Browser:
- Date/time:
- Tester:
- Database state before test:
- Any setup issues:

## Manual Golden Path

| Step | Page / action | Expected result | Failure if | Pass / fail notes |
| --- | --- | --- | --- | --- |
| 1 | Open `http://127.0.0.1:8000/health`. | Page shows `{"status":"ok"}`. | Health page does not load, returns an error, or does not show `ok`. | |
| 2 | Open `http://127.0.0.1:8000/`. | Dashboard loads with title `Heritage Risk Dashboard`. Stats cards are visible. | Dashboard crashes, styles are missing, or page is blank. | |
| 3 | If the dashboard shows `Load Demo Data`, click it. If it does not show, open `http://127.0.0.1:8000/docs` and use `POST /seed`, or run `curl -X POST http://127.0.0.1:8000/seed` in another terminal. | Browser returns to the dashboard. If loaded from the button, a success banner appears. Demo sites/cases are visible. | Seed action errors, duplicates obvious demo records repeatedly, or dashboard still has no demo content. | |
| 4 | On the dashboard, click `View All Sites`. | `/sites` loads and shows seeded sites such as `Old Stone Church`, `Historic Iron Bridge`, and `Memorial Statue`. | Sites list is empty after seeding, links are broken, or seeded names are missing. | |
| 5 | Click a site name, for example `Old Stone Church`. | Site detail page loads. It shows location, observation count, risk case count, and an `+ Add Observation` button. | Site page returns 404/500, counts are missing, or observation controls are missing. | |
| 6 | Click `+ Add Observation`. | Add Observation form opens for the selected site. It has photo upload, notes, damage type checkboxes, severity slider, and `Save Observation`. | Form does not open, posts to the wrong site, or key fields are missing. | |
| 7 | Upload a small `.jpg`, `.jpeg`, `.png`, or `.webp` image under 10 MB. Add notes such as `New crack and water staining visible on lower wall`. Tick `Crack` and `Water staining`. Set severity to `4` or `5`. Click `Save Observation`. | Browser returns to the site detail page. The new observation appears near the top with `AI: Not run`, the notes, tags, severity, and a `View Details` link. | Upload fails for a valid image, observation is not visible, notes/tags are lost, or the site page crashes. | |
| 8 | On the new observation card, click `View Details`. | Observation detail page opens. Uploaded image or `No image uploaded` placeholder appears. AI Analysis panel shows `Not run` and a `Run AI Analysis` button. | Observation detail is 404/500, image display is broken, or AI button is missing. | |
| 9 | Click `Run AI Analysis`. | Page reloads. AI panel shows `MOCK / FALLBACK`, provider `Mock`, confidence, summary, recommended action, and suggested damage tags. | Status stays `Not run`, shows unexpected Azure failure in mock mode, or page errors. | |
| 10 | Click `Create Risk Case`. | Case detail page opens. It shows case number, risk band, score out of 100, status badge, observation details, and AI summary. | Case is not created, duplicate button loops, risk score is missing, or case page crashes. | |
| 11 | In `Update Status`, change `Case Status` to `Verified`. Optionally enter `Local council heritage team` in `Route to`. Click `Save Status`. | Case page reloads. Status badge shows `Verified`. If route text was entered, `Routed to` shows the entered organisation. | Status does not change, route text is lost unexpectedly, or invalid error appears for a valid status. | |
| 12 | Click `View Report`. | Evidence Report page opens for the case. It shows report content, the safety note, and a `Download .md` link. If AI is mock, a mock-analysis notice appears. | Report page is blank, returns 404/500, or generated report content is missing. | |
| 13 | Click `Download .md`. | Browser opens or downloads the Markdown evidence report for the same case. | Link is broken, report is missing, or it downloads the wrong case report. | |
| 14 | Return to the dashboard at `http://127.0.0.1:8000/`. | Stats reflect the new observation and risk case. Recent Cases and Recent Observations include the new workflow item. | Dashboard counts do not update, recent lists omit the new records, or dashboard crashes after the workflow. | |

## What Counts as a Smoke-Test Failure

- Any page in the golden path returns 404 or 500.
- A visible button or link in the checklist is missing.
- A valid observation image under 10 MB cannot be uploaded.
- Mock AI analysis does not complete when Azure AI is disabled.
- Risk case creation fails or opens the wrong case.
- Status updates do not persist after saving.
- Evidence report page or Markdown download is unavailable.
- The app needs manual database edits to complete the flow.

## Final Result

- Overall result: Pass / Fail
- Blocking failures:
- Non-blocking issues or demo rough edges:
- Follow-up tickets needed:
