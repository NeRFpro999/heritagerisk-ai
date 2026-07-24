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
| Image handling | Pillow | Signature validation, EXIF orientation, and metadata-free re-encoding |
| Reviewer access | Starlette signed session + `hashlib.scrypt` | One environment-configured reviewer credential; eight-hour session |
| Form security | Double-submit CSRF token | Required on every state-changing form POST |
| AI provider | Azure OpenAI Vision | Optional, enabled by environment flag |
| AI fallback | Mock analyzer | Default path; works offline |
| Reports | Markdown and structured HTML | Markdown generator plus Jinja2 report view |
| Tests | pytest | Run from `backend/` |
| Server | uvicorn | Started by `backend/run.py` |

## Data Model

Core models:

- `Site`: heritage place metadata.
- `Observation`: editable working notes/tags/severity, human review status,
  `reviewed_by`, immutable `contributor_original` JSON, separate AI proposal
  fields/raw JSON, and a separate reviewer-decision JSON record.
- `ObservationImage`: one or more uploaded images linked to an observation.
- `RiskCase`: case linked one-to-one with an observation, with `finalized_by`,
  stored score/band, and an immutable `final_snapshot` JSON containing reviewer
  identities, accepted evidence, and exact scoring arithmetic.

The application uses `Base.metadata.create_all()` plus a small idempotent SQLite startup helper. The helper checks `PRAGMA table_info`, adds missing review/provenance/identity columns, and backfills legacy single-image records without duplicating them. It cannot reconstruct contributor originals, reviewer identities, or final case details that were never stored, so those fields remain `NULL` for older rows. It is not a general migration framework.

## Current Pipeline

Public submission path:

```text
1. Site is created or selected
       |
       v
2. Observation is submitted
   - One to six images are stored
   - Each file is at most 10 MiB and its JPEG/PNG/WEBP signature must match its allowed suffix
   - Pillow decodes it, applies EXIF orientation, and re-encodes a fresh metadata-free image under a UUID filename
   - Contributor notes, tags, severity, and submission time are copied once into contributor_original
   - The same values initialize the editable Observation working fields
   - Public submissions are set to human_review_status = Pending
       |
       v
3. Human Review Queue
   - Reviewer must have the signed reviewer session
   - Reviewer approves for AI, rejects, or marks sensitive
   - Reviewer may redact working notes and update working tags or severity
   - contributor_original is never changed by review routes
   - reviewed_by is stamped from the authenticated session
   - Sensitive evidence is suppressed from general dashboard and site views
       |
       v
4. AI Analysis
   - Only allowed when status is ApprovedForAI
   - Azure OpenAI Vision runs when enabled and configured
   - Mock analyzer is used when Azure is disabled or unavailable
   - All attached images plus site context are processed together
   - AI tags, severity, summary, uncertainty, confidence, provider, recommended action, and raw response are stored separately from the current human-reviewed values
   - Reviewer edit, accept, and reject routes do not rewrite that AI proposal
       |
       v
5. AI Review Result
   - Reviewer session is required
   - Reviewer compares contributor-original, current working, and AI-proposed values
   - Reviewer can edit the final accepted values or reject the unchanged AI proposal
   - Reviewer finalizes summary, next step, visible damage tags, severity, and optional routing destination
       |
       v
6. Risk Case
   - Risk score is calculated by rule-based math
   - Risk band is assigned from thresholds
   - Site details, final tags/severity, weights, multiplier, raw equation, capped score, band, final wording, contributor original, AI proposal, and image references are snapshotted
   - Case and report views render observation-derived values only from that snapshot
   - finalized_by and both snapshotted reviewer identities are rendered for audit
       |
       v
7. Manual status/routing update
   - Case status can be advanced only through the allowed transition graph
   - Routed cases require a recorded destination
   - routed_to records a human-entered destination only
   - CaseEvent rows record each accepted transition with reviewer identity,
     timestamp, and optional note
   - Report output is regenerated so status and routing remain current
```

Internal reviewer-led intake path:

```text
1. Reviewer opens Add Site
   - Signed reviewer session is required
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

The public submission and authenticated reviewer-led intake routes call the same
upload helper. The legacy site-observation GET/POST routes and template have been
removed. Stored files omit EXIF, GPS, XMP, embedded thumbnails, and other source
metadata, and Azure receives those sanitized files. The control does not provide
malware scanning, private media delivery, an aggregate request limit, rate
limiting, or consent/cloud-retention governance.

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

On the primary route, final tags and severity come from the human finalization step. The compatibility case route accepts the current reviewed values without showing the comparison form. Both paths require a reviewer session, CSRF validation, and a recorded reviewer identity, and both store the same immutable scoring snapshot on `RiskCase`; AI may suggest tags but does not calculate the score.

## Evidence Reports

Reports are generated after a Risk Case is created.

Current report content includes:

- Site details captured at case creation.
- Contributor-original metadata and reviewed-at-finalization details. Original note text is preserved for reviewer comparison but withheld from case reports after privacy review.
- Image references captured at case creation.
- Human review audit trail.
- Reviewer and finalizer identities captured in the immutable case snapshot.
- The AI proposal captured in the immutable case snapshot and the separate reviewer decision.
- AI uncertainty and human AI-finalization decision.
- Reviewed summary and recommended next step.
- Finalized damage tags and severity.
- Explainable risk score equation.
- Final routing destination, if entered by the reviewer.
- Safety warning blockquote.

Reports are written as Markdown and can be viewed as HTML through the app.

For new, snapshotted cases, all observation-derived report fields come from
`RiskCase.final_snapshot`. Regeneration can update the live case status and
routing destination, but later Observation edits cannot change final evidence,
score, equation, or band. Pre-provenance cases use their stored scalar score and
band and show unavailable snapshot details without consulting the live
Observation.

The HTML route renders a structured evidence document; it does not merely display raw Markdown. The raw Markdown remains available in a collapsible source view and as a download.

## Manual Routing Policy

HeritageRisk AI does not auto-route official reports.

The `routed_to` value is a human-entered documentation field. The app does not send reports to councils, site owners, authorities, email systems, messaging systems, or external services.

## Deployment Boundary

The current build is a local single-reviewer competition demo. Reviewer actions
use one `REVIEWER_USERNAME` plus scrypt `REVIEWER_PASSWORD_HASH`, with an
eight-hour signed session. `SESSION_SECRET_KEY` should be configured; otherwise
the generated process-ephemeral secret invalidates sessions at restart. All form
POSTs use double-submit CSRF validation. Public submission remains logged out and
always enters `Pending`.

This is not a multi-user or production authentication system. There are no
individual accounts or roles, login throttling, password recovery, per-status
updater roles, or full append-only event history for every edit. Local HTTP
leaves the session cookie without `Secure`. Uploaded images and read-only
case/report routes remain public. Historical identity columns can be `NULL`, and
report GET routes regenerate files and write `report_path`. See
[competition_baseline.md](competition_baseline.md)
for the full verified limitation set.

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
