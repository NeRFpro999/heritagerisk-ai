# HeritageRisk AI — Project Charter

## Purpose

HeritageRisk AI helps document visible deterioration evidence at heritage sites and turn it into a human-reviewed Risk Case.

The project is designed for a student competition context. Its primary public workflow reviews evidence before AI analysis and reviews AI output before a Risk Case is created. Legacy compatibility routes do not enforce every gate; [competition_baseline.md](competition_baseline.md) records the limitations.

## Primary Implemented Workflow

```text
Site
  -> Observation with multiple images, notes, tags, and severity
  -> Human Review Queue
  -> AI Analysis after approval
  -> Human AI Review and finalization
  -> Risk Case with explainable score
  -> Evidence Report
  -> Manual status/routing update
```

## What the System Does

- Stores heritage sites and observations.
- Supports multiple images for one observation.
- Holds public submissions in a `Pending` human review state.
- Lets a reviewer mark an observation as `ApprovedForAI`, `Rejected`, or `Sensitive`.
- Blocks AI analysis unless a human reviewer has approved the observation.
- Uses Azure OpenAI Vision when configured, with a mock fallback that works offline.
- Sends all approved observation images plus reviewed site context to the analyzer.
- Keeps current human-reviewed values separate from AI-suggested tags and severity; original contributor values are not immutable.
- Lets a reviewer compare, edit, accept, or reject AI output before creating a Risk Case.
- Hides observations marked `Sensitive` from general evidence views, without access-controlling the underlying upload URL.
- Calculates risk with a transparent rule-based score: `sum(tag weights) * severity`, capped at 100.
- Generates Markdown and HTML evidence reports with images, audit trails, risk breakdown, routing destination, and safety notice.

## What the System Does Not Do

HeritageRisk AI does **not** auto-route official reports.

The app may record a human-entered routing destination, such as `Local Council`, in the Risk Case and evidence report. That is a documentation field, not an automated dispatch system. No email, notification, external submission, or official escalation is triggered by the app.

HeritageRisk AI also does **not** diagnose structural failure.

The AI is used strictly to draft visible-risk triage evidence. It must not decide whether a site is safe, confirm structural damage, replace a conservator or engineer, or make an emergency, legal, cultural heritage, or conservation authority decision.

## Responsible AI Principles

1. **Human review before AI**
   Public observations start as `Pending`. AI analysis can run only after a reviewer marks the observation `ApprovedForAI`.

2. **Human finalization on the primary Risk Case route**
   AI output is not final. The primary route lets the reviewer edit or reject the draft and confirm final tags, severity, summary, next step, and any recorded routing destination. The legacy case route remains a documented compatibility bypass.

3. **Rule-based scoring**
   The risk score is explainable and deterministic. It is calculated from finalized tags and reviewer-selected severity, not from hidden AI reasoning.

4. **No safety decisions**
   The app records visible-risk evidence only. It does not advise entry, repair, cleaning, emergency action, or professional safety conclusions.

5. **Offline demonstrability**
   The mock analyzer remains available so the project can be demonstrated and tested without credentials or network access.

## In Scope

- FastAPI web app with server-rendered Jinja2 pages.
- SQLite persistence for local demo and judging.
- Multi-image observations.
- Human review queue.
- Azure OpenAI Vision integration with mock fallback.
- AI review result page and human finalization form.
- Explicit AI-draft rejection and rerun path.
- Manual case status update page.
- Rule-based explainable scoring.
- Markdown and HTML evidence reports.
- pytest coverage for routes, workflow gates, reports, scoring, and seed data.

## Out of Scope

- Automatic routing of official reports.
- Structural safety diagnosis.
- Emergency, legal, engineering, or conservation authority decisions.
- User accounts or authentication.
- Public campaign management.
- Cloud deployment.
- Email, SMS, or external notification integrations.
- A mobile app.
- A frontend framework or second database engine.

Because authentication is out of scope, the current build is a local competition demonstration, not a production public reporting service.

## Technical Principles

- Keep the app readable for a student project team.
- Preserve the working MVP workflow at every step.
- Use the existing stack: FastAPI, SQLAlchemy, SQLite, Jinja2, vanilla CSS.
- Keep Azure optional and the mock fallback working.
- Never hardcode secrets.
- Add tests for new workflow logic.
- Keep official claims aligned with implemented behavior.
