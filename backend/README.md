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
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/openai/v1/
AZURE_OPENAI_API_KEY=your-real-api-key
AZURE_OPENAI_PRIMARY_DEPLOYMENT=your-vision-deployment-name
AZURE_OPENAI_TIMEOUT_SECONDS=30
```

**Important:** `AZURE_OPENAI_PRIMARY_DEPLOYMENT` must support image input.
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
2. Open the review queue and approve, reject, or mark the submission sensitive.
3. Analyze an approved observation (mock mode works without a key).
4. Review the AI draft and finalize the tags and severity to create a Risk Case.
5. Update the case status or record a routing destination manually.
6. Open the HTML or Markdown evidence report.

Legacy site-observation and case routes remain for compatibility and bypass parts
of this primary flow. Case statuses are not enforced as a sequential state machine.

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
| `http://127.0.0.1:8000/sites/new` | Add a heritage site |
| `http://127.0.0.1:8000/cases` | All risk cases |
| `http://127.0.0.1:8000/health` | Health check → `{"status":"ok"}` |
| `http://127.0.0.1:8000/docs` | Interactive API docs (Swagger UI) |

---

## Database note

At startup the app creates missing tables and runs a guarded, idempotent SQLite
migration for the July review-status and multi-image schema. Existing legacy
single-image records are backfilled into `ObservationImage` rows.

---

## File storage

| Directory | Contents |
|-----------|----------|
| `../data/uploads/` | Uploaded images (UUID-prefixed filenames) |
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
│   └── test_ai.py              # pytest tests (no real API calls)
└── app/
    ├── main.py                 # FastAPI app + all routes
    ├── config.py               # Env-var settings, .env loading
    ├── database.py             # SQLAlchemy engine, session, startup migration
    ├── models.py               # ORM: Site, Observation, ObservationImage, RiskCase
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
