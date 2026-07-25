# HeritageRisk AI — Backend

FastAPI backend for the HeritageRisk AI MVP.

## Prerequisites

- Python 3.12 or higher
- `pip`

## Setup

```bash
cd backend

python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

## Run the server

```bash
python3 run.py
```

Opens at **http://127.0.0.1:8000** with hot-reload enabled.

---

## AI analysis — how it works

### Mode 1: Mock (default — no credentials needed)

The app works out of the box without any Azure credentials.
The "Run AI Analysis" button runs a rule-based keyword scan of the observer
notes and returns a placeholder result clearly labelled **MOCK**.

To confirm mock mode is active, check your `.env` (or environment):

```
AZURE_OPENAI_ENABLED=false   # or just leave it unset
```

### Mode 2: Azure OpenAI Vision (real image analysis)

> **Warning — never commit real API keys.**
> The `.env` file is listed in `.gitignore`. Only ever put real credentials in
> `.env` locally. Never paste them into source files, templates, or logs.

**Step 1 — copy the template**

```bash
cp ../.env.example .env
```

**Step 2 — fill in your Azure values**

Open `.env` and set:

```
AZURE_OPENAI_ENABLED=true
AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE_NAME.openai.azure.com/
AZURE_OPENAI_API_KEY=YOUR_AZURE_OPENAI_API_KEY
AZURE_OPENAI_DEPLOYMENT=YOUR_GPT5_MINI_DEPLOYMENT_NAME
AZURE_OPENAI_API_VERSION=v1
AZURE_OPENAI_TIMEOUT_SECONDS=30
```

**Important:** `AZURE_OPENAI_DEPLOYMENT` is the Azure deployment name, which
may differ from the underlying model name, and it must support image input.
Configuration, connection, or response failures fall back to a clearly labelled
mock result; the route does not fabricate an Azure success.

**Step 3 — restart the server**

```bash
python3 run.py
```

**Step 4 — test it**

1. Add a site and an observation with a photo.
2. Open the observation detail page.
3. Click **Run AI Analysis**.
4. The result panel shows **AZURE OPENAI** badge, a summary, confidence %, and recommended action.

### AI output disclaimer

AI output is for human review only. It does not replace professional
conservation, engineering, cultural heritage, or emergency assessment.

---

## Primary public demo workflow

1. Open **http://127.0.0.1:8000/observations/submit** and submit one to six images.
2. Sign in at **http://127.0.0.1:8000/reviewer/login**.
3. Open the review queue and approve, reject, or mark the submission sensitive.
4. Analyze an approved observation (mock mode works without a key).
5. Review the AI draft and finalize the tags and severity to create a Risk Case.
6. Update the case status or record a routing destination manually.
7. Open the HTML or Markdown evidence report.

Reviewer comparison pages can show the preserved contributor-original notes.
Case views and exported reports use the reviewed-at-finalization notes and
withhold the original text so privacy redaction is not reversed.

The legacy site-observation upload routes and template have been removed. The
compatibility case-creation POST remains, but it is reviewer-authenticated,
CSRF-protected, and records finalizer identity plus the same immutable snapshot.
It does not present the primary comparison form. Case status updates follow the
enforced Draft -> Needs Review -> Verified -> Routed -> Closed transition rules,
with a `CaseEvent` history row for each accepted transition.

### Demo database and Azure verification scripts

From the repository root, `scripts/seed_demo.py` rebuilds a demo database from
privacy-cleared images under ignored `demo_assets/`:

```bash
REVIEWER_USERNAME=demo.reviewer REVIEWER_PASSWORD='...' \
python3 scripts/seed_demo.py --mock
```

The manifest-driven seed uses the real FastAPI routes through `TestClient`, not
raw inserts, so provenance, review, analysis, case finalization, reports, and
status events are exercised. `--azure` requires Azure endpoint, API key, and
deployment environment variables.

`scripts/verify_azure.py` sends one manifest observation through live Azure when
`AZURE_OPENAI_ENABLED=true` and all Azure variables are present. It prints the
structured persisted result, latency, deployment id, and validation status, and
exits nonzero if the app falls back to mock or validation fails. Invalid schema
payloads retain sanitized raw data. Transport, configuration, import, image
preparation, and API failures append a failed Azure analysis record with a fixed
sanitized diagnostic and timestamp, then append the clearly labelled mock
fallback as a separate record. The verifier prints this ordered attempt history.

Every upload route uses one shared image helper. It accepts JPEG, PNG, and WEBP
files up to 10 MiB only when the leading signature matches the suffix, requires
Pillow to decode them, applies EXIF orientation, and writes a fresh metadata-free
image under a UUID filename. The stored files contain no source EXIF, GPS, XMP,
or embedded thumbnail, and these sanitized files are what Azure receives when
enabled. They remain publicly addressable under `/uploads` and are not
malware-scanned.

### Reviewer login and CSRF

Reviewer actions use the single credential configured by `REVIEWER_USERNAME`
and `REVIEWER_PASSWORD_HASH`. Generate the salted scrypt password hash with:

```bash
python3 -c 'from app.auth import hash_reviewer_password; import getpass; print(hash_reviewer_password(getpass.getpass()))'
```

Set a stable `SESSION_SECRET_KEY` to keep signed sessions valid across restarts:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Sessions expire after eight hours. If `SESSION_SECRET_KEY` is blank, the app
uses a process-ephemeral secret and existing sessions end on restart. All form
POSTs use a double-submit CSRF token. Public submission stays logged out by
design and always lands in `Pending`.

This is minimal reviewer access control, not a multi-user account system. There
is no role model, login throttling, password recovery, per-status updater field,
or append-only action log. Local HTTP leaves the session cookie without the
`Secure` flag. Uploaded files and read-only case/report routes remain public.

---

## Running tests

```bash
cd backend
AZURE_OPENAI_ENABLED=false pytest tests/ -v
```

The explicit override prevents a local `.env` from enabling live Azure calls.
Azure-dependent test paths use mocked clients.

---

## Key URLs

| URL | What it does |
|-----|-------------|
| `http://127.0.0.1:8000/` | Dashboard |
| `http://127.0.0.1:8000/reviewer/login` | Reviewer sign-in |
| `http://127.0.0.1:8000/observations/submit` | Public multi-image submission |
| `http://127.0.0.1:8000/observations/review` | Authenticated reviewer queue |
| `http://127.0.0.1:8000/sites/new` | Add a heritage site |
| `http://127.0.0.1:8000/cases` | All risk cases |
| `http://127.0.0.1:8000/health` | Health check → `{"status":"ok"}` |
| `http://127.0.0.1:8000/docs` | Interactive API docs (Swagger UI) |

---

## Database note

At startup the app creates missing tables and runs a guarded, idempotent SQLite
migration for the July review-status, identity, multi-image, and provenance schema. Existing
legacy single-image records are backfilled into `ObservationImage` rows. Legacy
rows whose contributor originals, final Risk Case snapshots, or reviewer
identities were never recorded remain `NULL`; the app shows those details as
unavailable rather than inventing provenance for them.

---

## File storage

| Directory | Contents |
|-----------|----------|
| `../data/uploads/` | Sanitized uploaded images (UUID-generated filenames) |
| `../data/heritagerisk.db` | SQLite database (auto-created on first run) |
| `../reports/` | Generated Markdown evidence reports |

---

## Project structure

```
backend/
├── run.py
├── requirements.txt
├── README.md
├── tests/
│   └── test_*.py               # pytest suite (Azure paths are mocked)
└── app/
    ├── main.py                 # FastAPI app + all 28 routes
    ├── auth.py                 # Reviewer session, scrypt password, and CSRF helpers
    ├── config.py               # Env-var settings, .env loading
    ├── database.py             # SQLAlchemy engine, session, startup migration
    ├── models.py               # ORM: workflow, AI-attempt, case, event, experiment rows
    ├── provider_identity.py    # Canonical Azure/mock/unknown classifier
    ├── provenance.py           # Immutable contributor/case snapshot builders
    ├── risk.py                 # Rule-based risk scoring
    ├── reports.py              # Markdown report generator
    ├── services/
    │   ├── ai_analysis.py      # Public entry point + mock fallback
    │   └── providers/
    │       └── azure_openai_provider.py   # Real Azure OpenAI Vision call
    ├── templates/              # Jinja2 HTML templates
    └── static/
        └── style.css

../.env.example                 # Copy to .env — never commit real keys
```
