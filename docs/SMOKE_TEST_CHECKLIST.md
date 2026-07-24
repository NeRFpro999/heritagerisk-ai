# HeritageRisk AI Legacy MVP Smoke-Test Checklist

> Historical record from the June 2026 single-image MVP. It does not describe
> the current July multi-image review workflow. See
> [`competition_baseline.md`](../competition_baseline.md) for current verified
> behavior and limitations.

## Current July Reviewer-Access Smoke Path — 2026-07-22

Before a current demo, configure `REVIEWER_USERNAME`, a generated scrypt
`REVIEWER_PASSWORD_HASH`, and a stable `SESSION_SECRET_KEY` in the ignored
`.env`. Keep `AZURE_OPENAI_ENABLED=false` for an offline smoke test.

1. While logged out, submit one to six genuine, signature-matched images at
   `/observations/submit`. Confirm the response is accepted and the Observation
   is `Pending`.
2. Open `/observations/review` while logged out. Confirm it redirects to
   `/reviewer/login`.
3. Sign in with the configured reviewer credential. Confirm the queue opens.
4. Review the pending Observation, edit working evidence if needed, approve it,
   and run mock analysis. Successful form posts also exercise the shared CSRF
   token; a missing token is expected to return `403` in automated tests.
5. Compare contributor-original, current working, and AI-proposed values, then
   finalize a Risk Case. Confirm the case page shows the configured identity for
   both `Reviewed by` and `Finalized by`.
6. Update the case status and, for `Routed`, enter a destination. Confirm the
   HTML and Markdown reports show the same immutable reviewer identities and
   scoring breakdown.
7. Log out. Confirm the review queue, Add Site page, analysis trigger,
   AI-finalization pages, and status form redirect to login.
8. Confirm read-only case/report pages and `/uploads` remain public; this is a
   documented current boundary, not a smoke-test failure.

The browser Seed Demo Data action also requires reviewer login and CSRF. The old
`/sites/{id}/observations/new` and `/sites/{id}/observations` steps no longer
exist; use public multi-image submission or authenticated Add Site intake.

## Historical June Checklist

The preserved checklist below was the manual browser smoke test for the June
golden path:

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
| 7 | Upload a genuine `.jpg`, `.jpeg`, `.png`, or `.webp` image whose content matches its suffix and is under 10 MiB. Add notes such as `New crack and water staining visible on lower wall`. Tick `Crack` and `Water staining`. Set severity to `4` or `5`. Click `Save Observation`. | Browser returns to the site detail page. The new observation appears near the top with `AI: Not run`, the notes, tags, severity, and a `View Details` link. | Upload fails for a valid image, observation is not visible, notes/tags are lost, or the site page crashes. | |
| 8 | On the new observation card, click `View Details`. | Observation detail page opens. Uploaded image or `No image uploaded` placeholder appears. AI Analysis panel shows `Not run` and a `Run AI Analysis` button. | Observation detail is 404/500, image display is broken, or AI button is missing. | |
| 9 | Click `Run AI Analysis`. | Page reloads. AI panel shows `MOCK / FALLBACK`, provider `Mock`, confidence, summary, recommended action, and suggested damage tags. | Status stays `Not run`, shows unexpected Azure failure in mock mode, or page errors. | |
| 10 | Click `Create Risk Case`. | Case detail page opens. It shows case number, risk band, score out of 100, status badge, observation details, and AI summary. | Case is not created, duplicate button loops, risk score is missing, or case page crashes. | |
| 11 | In `Update Status`, move through the valid next states shown by the form: `Needs Review`, then `Verified`, then `Routed` with `Local council heritage team` as the destination. | Case page reloads after each step. Status badges advance sequentially, `Routed to` shows the entered organisation, and Status Event History lists the reviewer transitions. | A direct invalid jump is offered, status does not change, route text is lost unexpectedly, or event history is missing. | |
| 12 | Click `View Report`. | Evidence Report page opens for the case. It shows report content, the safety note, and a `Download .md` link. If AI is mock, a mock-analysis notice appears. | Report page is blank, returns 404/500, or generated report content is missing. | |
| 13 | Click `Download .md`. | Browser opens or downloads the Markdown evidence report for the same case. | Link is broken, report is missing, or it downloads the wrong case report. | |
| 14 | Return to the dashboard at `http://127.0.0.1:8000/`. | Stats reflect the new observation and risk case. Recent Cases and Recent Observations include the new workflow item. | Dashboard counts do not update, recent lists omit the new records, or dashboard crashes after the workflow. | |

## What Counts as a Smoke-Test Failure

- Any page in the golden path returns 404 or 500.
- A visible button or link in the checklist is missing.
- A valid, signature-matched observation image under 10 MiB cannot be uploaded,
  or a mismatched/text masquerading file is accepted.
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
