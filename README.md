# HeritageRisk AI

HeritageRisk AI is a human-reviewed heritage conservation triage tool.

Its primary public workflow lets a contributor submit visible evidence from a heritage site, requires a human approval before AI analysis, uses AI only to draft triage notes, and asks a human reviewer to finalize the tags and severity before creating a Risk Case.

The project is built for a student competition setting, so the architecture is intentionally lean: FastAPI, SQLAlchemy, SQLite, Jinja2 templates, vanilla CSS, Azure OpenAI Vision when configured, and an offline mock fallback by default.

## Responsible AI Boundary

HeritageRisk AI is for visible-risk triage only.

The system does not diagnose structural failure, decide whether a site is safe, replace professional conservation or engineering advice, or automatically route official reports. AI output is treated as draft evidence for human review.

Required safety statement used in the app and reports:

> HeritageRisk AI is for visible risk triage only. It does not replace professional conservation, engineering, emergency, legal, or cultural heritage advice.

## Human-in-the-Loop Workflow

The primary public workflow is:

```text
User Submission
  -> Human Review Queue
  -> AI Analysis
  -> Human Finalization
  -> Risk Case
```

1. **User Submission**
   A contributor selects or describes a site and submits up to six observation images with optional notes, selected visible damage tags, and severity. Public submissions are saved as `Pending` and the browser shows a confirmation page.

2. **Human Review Queue**
   A reviewer checks safety, privacy, relevance, and image quality before AI analysis. The reviewer can replace notes, update tags or severity, reject the submission, mark it sensitive, or approve and run AI. Sensitive evidence is hidden from ordinary dashboard, site, and observation views, but uploaded files are not access controlled.

3. **AI Analysis**
   AI analysis is locked until the observation is marked `ApprovedForAI`. Every attached image is sent together with the reviewed site name, location, description, and notes. Azure OpenAI Vision can be used when credentials are configured. Otherwise, the mock analyzer runs offline and is labelled clearly.

4. **Human Finalization**
   The reviewer compares the current human-reviewed values with separate AI suggestions. These values may differ from the original submission because the review step overwrites notes, tags, and severity. The reviewer can edit the final summary and next step, accept or override tags and severity, or reject the AI draft. A rejected draft cannot become a Risk Case until analysis is rerun and reviewed.

5. **Risk Case**
   The app creates an official Risk Case from the human-finalized values. The structured browser report and Markdown download record all images, the reviewed AI draft, uncertainty, audit trail, explainable score, workflow status, routing destination, limitations, and safety notice.

## Multi-Image Observations

Observations support multiple images through the `ObservationImage` table.

The observation detail page displays all images. Site detail pages show a compact first-image thumbnail with a count for additional images. Evidence reports also include every image attached to the observation.

The current human-reviewed tags and severity remain separate from AI suggestions until the finalization form is submitted. AI application does not silently overwrite those values, but the app does not preserve an immutable copy of the original contributor text, tags, or severity.

## AI-Assisted Site Intake

The Add Site page also supports attaching photos during site creation.

When photos are attached there, the app creates the site, creates an approved observation, sends the images plus site name, location, description, and optional notes to the analyzer, then opens the AI review/finalization page. This path is intended for an internal reviewer-led demo flow.

Public observation submissions still enter the review queue as `Pending`.

## Local Demo Scope

The current competition build is a local single-reviewer application. It does not include user accounts, authentication, cloud deployment, email delivery, or automatic council submission. Legacy intake and case routes also bypass parts of the primary review flow. See [competition_baseline.md](competition_baseline.md) for verified behavior and known limitations.

## Explainable Risk Scoring

Risk scoring is rule-based. AI does not calculate the final score.

The formula is:

```text
risk score = sum(final damage tag weights) * human-selected severity
```

The result is capped at 100:

```text
final score = min(tag weight sum * severity, 100)
```

Risk bands are:

- Low: 0-29
- Medium: 30-59
- High: 60-100

The Risk Case detail page and generated evidence report show the tag weights, severity multiplier, equation, cap status, and final band.

## Current Stack

- Backend: FastAPI
- ORM: SQLAlchemy
- Database: SQLite
- Templates: Jinja2
- Styling: vanilla CSS
- AI provider: Azure OpenAI Vision when enabled
- Offline fallback: mock analyzer
- Tests: pytest

## Run Locally

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

The app works without Azure credentials. To configure Azure, copy the example environment file and fill in real values locally:

```bash
cp .env.example .env
```

Run the app:

```bash
cd backend
python3 run.py
```

Open:

```text
http://127.0.0.1:8000
```

## Run Tests

```bash
cd backend
AZURE_OPENAI_ENABLED=false pytest
```

The explicit environment override keeps the suite offline even if a developer's local `.env` enables Azure.

## Seed Demo Data

With the app running, use the **Seed Demo Data** button on the dashboard.

You can also seed from the command line:

```bash
cd backend
python3 -m app.seed
```

To reset local demo data, stop the server, delete `data/heritagerisk.db`, and seed again.
