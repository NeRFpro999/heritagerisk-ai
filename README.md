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
   A contributor selects or describes a site and submits up to six observation images with optional notes, selected visible damage tags, and severity. Each JPEG, PNG, or WEBP file must be no larger than 10 MiB and its leading signature must match its filename suffix. Public submissions are saved as `Pending` and the browser shows a confirmation page.

2. **Human Review Queue**
   An authenticated reviewer checks safety, privacy, relevance, and image quality before AI analysis. The reviewer can replace the working notes, update working tags or severity, reject the submission, mark it sensitive, or approve and run AI. The contributor's original notes, tags, severity, and submission time remain in a separate immutable JSON record. Sensitive evidence is hidden from ordinary dashboard, site, and observation views, but uploaded files are not access controlled.

3. **AI Analysis**
   AI analysis is locked until the observation is marked `ApprovedForAI`. Every attached image is sent together with the reviewed site name, location, description, notes, and image ids. Azure OpenAI Vision can be used when credentials are configured. Otherwise, the mock analyzer runs offline and is labelled clearly. New AI results use schema v2: evidence sufficiency plus per-indicator findings with image references, confidence, evidence location, supporting visible evidence, and severity contribution. Invalid v2 output is stored as a failed validation state, not coerced into success.

4. **Human Finalization**
   The reviewer compares contributor-original values, the current editable working copy, and the separate AI proposal. For schema v2 results, the reviewer accepts, edits, or rejects proposed indicators before the final tag set feeds the scorer. The reviewer can also edit the final summary and next step, override tags and severity, or reject the AI draft. Reviewer actions do not rewrite the stored AI proposal. A rejected draft cannot become a Risk Case until analysis is rerun and reviewed.

5. **Risk Case**
   The app creates an official Risk Case with an immutable snapshot of the site details, recorded reviewer and finalizer identities, human-finalized values, per-tag weights, severity multiplier, raw equation, capped score, and band. The case page, structured browser report, and Markdown download use this snapshot, so later edits to the Observation cannot change the displayed final evidence, identities, or scoring breakdown. Contributor-original note text remains available on reviewer comparison pages but is withheld from case views and exported reports after privacy review.

## Multi-Image Observations

Observations support multiple images through the `ObservationImage` table.

The observation detail page displays all images. Site detail pages show a compact first-image thumbnail with a count for additional images. New Risk Cases capture every image reference attached at case creation, and their evidence reports render those captured references rather than the live Observation relationship.

The contributor original, current human-reviewed working values, and AI proposal remain separate. New Risk Cases snapshot all finalized observation-derived evidence, including image references, so their case and report views do not drift when the working Observation is edited later. Records created before the additive provenance migration may show original or snapshot details as unavailable rather than reconstructing them from mutable data.

Both current upload paths—public submission and authenticated reviewer-led
intake—pass through the same image helper. The legacy single-image site upload
route has been removed.
Pillow decodes each signature-matched file, applies its EXIF orientation, and
re-encodes a fresh pixel-only image without EXIF, GPS, XMP, or embedded-thumbnail
metadata under a UUID filename. Azure receives that sanitized stored image when
enabled. This does not make `/uploads` private, scan files for malware, or replace
consent and cloud-retention rules.

## AI-Assisted Site Intake

The Add Site page also supports attaching photos during site creation.

After reviewer login, attaching photos there creates the site and an
`ApprovedForAI` observation stamped with the reviewer identity, sends the images
plus site name, location, description, and optional notes to the analyzer, then
opens the AI review/finalization page.

Public observation submissions still enter the review queue as `Pending`.

## Demo Data and Azure Verification

`scripts/seed_demo.py` rebuilds a demo SQLite database from privacy-cleared
photos in `demo_assets/`. The directory is intentionally ignored by Git. Provide
a `demo_assets/manifest.json` with `sites`, each containing site details,
relative image names, contributor notes, tags, severity, review outcomes,
optional final reviewer overrides, and status-transition events. The script
submits through the real FastAPI routes with `TestClient`, so upload validation,
CSRF, reviewer login, review decisions, AI analysis, provenance snapshots, case
creation, reports, and status events all run through application code.

```bash
REVIEWER_USERNAME=demo.reviewer REVIEWER_PASSWORD='...' \
python3 scripts/seed_demo.py --mock
```

Use `--azure` only when `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and
`AZURE_OPENAI_PRIMARY_DEPLOYMENT` are present in the environment. To verify one
live Azure observation without writing fabricated success data:

```bash
AZURE_OPENAI_ENABLED=true REVIEWER_USERNAME=demo.reviewer REVIEWER_PASSWORD='...' \
python3 scripts/verify_azure.py --assets demo_assets
```

`verify_azure.py` prints the persisted structured result, latency, deployment,
and validation status. It exits nonzero if Azure falls back to mock or fails
schema validation. A validation failure preserves the sanitized raw payload; a
transport/configuration fallback preserves only the clearly labelled mock state,
not the failed Azure attempt or diagnostic.

## Reviewer Access and Local Demo Scope

Reviewer actions use one credential configured through `REVIEWER_USERNAME` and
a salted scrypt `REVIEWER_PASSWORD_HASH`. Login creates a signed session cookie
valid for eight hours; `SESSION_SECRET_KEY` keeps sessions valid across process
restarts. If that secret is blank, the process generates an ephemeral secret and
existing sessions end when the app restarts. Every form POST uses a double-submit
CSRF token. Public submission is intentionally available while logged out and
always creates a `Pending` observation.

This is still a local single-reviewer competition application, not a multi-user
account system or production public service. It has no roles, password recovery,
login throttling, HTTPS configuration, or append-only action log. Local HTTP does
not set the session cookie's `Secure` flag. Upload URLs and read-only case/report
pages remain public, and older database rows can have no recorded reviewer
identity. See [competition_baseline.md](competition_baseline.md) for verified
behavior and known limitations.

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

The Risk Case stores the exact scoring inputs and arithmetic at creation. The detail page and both report formats render that stored snapshot rather than recalculating from the Observation.

## Current Stack

- Backend: FastAPI
- ORM: SQLAlchemy
- Database: SQLite
- Templates: Jinja2
- Styling: vanilla CSS
- Reviewer access: scrypt credential + signed Starlette session
- Form protection: double-submit CSRF token
- Image validation and normalization: Pillow
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

Configure reviewer access in `.env` before using reviewer actions. Generate a
password hash without placing the password in shell history:

```bash
cd backend
python3 -c 'from app.auth import hash_reviewer_password; import getpass; print(hash_reviewer_password(getpass.getpass()))'
```

Set the resulting value as `REVIEWER_PASSWORD_HASH`, choose
`REVIEWER_USERNAME`, and generate `SESSION_SECRET_KEY` with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
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

Reviewer login is at `http://127.0.0.1:8000/reviewer/login`.

## Run Tests

```bash
cd backend
AZURE_OPENAI_ENABLED=false pytest
```

The explicit environment override keeps the suite offline even if a developer's local `.env` enables Azure.

## Seed Demo Data

With the app running, sign in as the reviewer and use the **Seed Demo Data**
button on the dashboard. The browser seed POST is reviewer-guarded and
CSRF-protected.

You can also seed from the command line:

```bash
cd backend
python3 -m app.seed
```

To reset local demo data, stop the server, delete `data/heritagerisk.db`, and seed again.
