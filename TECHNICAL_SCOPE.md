# HeritageRisk AI — Technical Scope

This document describes only the current implemented architecture.

## Current Stack

| Layer | Technology | Notes |
|---|---|---|
| Web framework | FastAPI | Routes live in `backend/app/main.py` |
| ORM | SQLAlchemy | Declarative models in `backend/app/models.py` |
| Database | SQLite | Local database at `data/heritagerisk.db` |
| Templates | Jinja2 | Server-rendered HTML |
| Styling | Vanilla CSS | `backend/app/static/style.css` |
| AI provider | Azure OpenAI Vision | Optional, enabled by environment flag |
| AI fallback | Mock analyzer | Default path; works offline |
| Reports | Markdown and structured HTML | Markdown generator plus Jinja2 report view |
| Tests | pytest | Run from `backend/` |
| Server | uvicorn | Started by `backend/run.py` |

## Data Model

Core models:

- `Site`: heritage place metadata.
- `Observation`: submitted notes, selected tags, severity, human review status, and AI analysis fields.
- `ObservationImage`: one or more uploaded images linked to an observation.
- `RiskCase`: case linked one-to-one with an observation; the primary creation route records human AI-output finalization.

The application uses `Base.metadata.create_all()` plus a small idempotent SQLite startup helper. The helper checks `PRAGMA table_info`, adds the July review-status column only when missing, and backfills legacy single-image records without duplicating them. It is not a general migration framework.

## Current Pipeline

Public submission path:

```text
1. Site is created or selected
       |
       v
2. Observation is submitted
   - One to six images are stored
   - Contributor notes, tags, and severity are stored
   - Public submissions are set to human_review_status = Pending
       |
       v
3. Human Review Queue
   - Reviewer approves for AI, rejects, or marks sensitive
   - Reviewer may redact notes and update tags or severity before AI analysis
   - Sensitive evidence is suppressed from general dashboard and site views
       |
       v
4. AI Analysis
   - Only allowed when status is ApprovedForAI
   - Azure OpenAI Vision runs when enabled and configured
   - Mock analyzer is used when Azure is disabled or unavailable
   - All attached images plus site context are processed together
   - AI tags, severity, summary, uncertainty, confidence, provider, recommended action, and raw response are stored separately from the current human-reviewed values
       |
       v
5. AI Review Result
   - Reviewer compares current human-reviewed values with AI output; the original contributor values are not preserved separately
   - Reviewer can edit or reject the AI draft
   - Reviewer finalizes summary, next step, visible damage tags, severity, and optional routing destination
       |
       v
6. Risk Case
   - Risk score is calculated by rule-based math
   - Risk band is assigned from thresholds
   - Evidence report is generated
       |
       v
7. Manual status/routing update
   - Case status can be updated by a human
   - Routed cases require a recorded destination
   - routed_to records a human-entered destination only
   - Report output is regenerated so status and routing remain current
```

Internal reviewer-led intake path:

```text
1. Reviewer opens Add Site
       |
       v
2. Reviewer enters site name, location, description, and attaches photos
       |
       v
3. App creates Site + ApprovedForAI Observation
       |
       v
4. Analyzer receives all attached images plus site context text
       |
       v
5. App redirects to AI Review Result for human finalization
```

## AI Analysis Boundary

AI analysis is a draft triage aid only.

The analysis endpoint checks:

```text
observation.human_review_status == ApprovedForAI
```

If the observation is `Pending`, `Rejected`, or `Sensitive`, the endpoint returns `403 Forbidden` before Azure or mock analysis runs.

Azure errors must fall back to mock analysis. The app must remain usable with `AZURE_OPENAI_ENABLED=false` and no credentials.

The mock analyzer scans notes and does not inspect image pixels. The UI and reports label that limitation explicitly.

## Explainable Risk Scoring

Risk calculation lives in `backend/app/risk.py`.

The model is deterministic:

```text
risk score = sum(final damage tag weights) * severity
final score = min(risk score, 100)
```

Risk bands:

- Low: 0-29
- Medium: 30-59
- High: 60-100

On the primary route, final tags and severity come from the human finalization step. The legacy case route scores the observation's current values. In both paths, AI may suggest tags but does not calculate the score.

## Evidence Reports

Reports are generated after a Risk Case is created.

Current report content includes:

- Site details.
- Observation details.
- All observation images.
- Human review audit trail.
- AI audit trail.
- AI uncertainty and human AI-finalization decision.
- Reviewed summary and recommended next step.
- Finalized damage tags and severity.
- Explainable risk score equation.
- Final routing destination, if entered by the reviewer.
- Safety warning blockquote.

Reports are written as Markdown and can be viewed as HTML through the app.

The HTML route renders a structured evidence document; it does not merely display raw Markdown. The raw Markdown remains available in a collapsible source view and as a download.

## Manual Routing Policy

HeritageRisk AI does not auto-route official reports.

The `routed_to` value is a human-entered documentation field. The app does not send reports to councils, site owners, authorities, email systems, messaging systems, or external services.

## Deployment Boundary

The current build is a local single-reviewer competition demo. User accounts, authentication, cloud deployment, and production handling of public or sensitive data are outside the implemented scope.

Legacy reviewer-led intake can create an `ApprovedForAI` observation directly, and the legacy case route can create a case without the newer explicit AI-finalization record. Case statuses are assignable labels rather than enforced sequential transitions. See [competition_baseline.md](competition_baseline.md) for the full verified limitation set.

## Local Development Commands

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Run the app:

```bash
cd backend
python3 run.py
```

Run tests:

```bash
cd backend
AZURE_OPENAI_ENABLED=false pytest
```

Seed demo data:

```bash
cd backend
python3 -m app.seed
```

The dashboard also includes a **Seed Demo Data** button that posts to `/seed`.

## Non-Negotiable Constraints

1. AI output is visible-risk triage only.
2. The public workflow must preserve its review-before-AI gate.
3. The primary Risk Case route must preserve human AI-output finalization.
4. The risk score must remain explainable and rule-based.
5. The mock analyzer must work without credentials or network access.
6. The app must not hardcode secrets.
7. Official reports must include the safety warning.
8. The app must not auto-route official reports or claim structural safety conclusions.
