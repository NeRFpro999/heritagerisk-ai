# HeritageRisk AI — Backend

FastAPI backend for the HeritageRisk AI MVP.

## Prerequisites

- Python 3.11 or higher
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
AI_ANALYSIS_ENABLED=false   # or just leave it unset
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
AI_ANALYSIS_ENABLED=true
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_KEY=your-real-api-key
AZURE_OPENAI_DEPLOYMENT=your-vision-deployment-name
AZURE_OPENAI_API_VERSION=2024-02-01
```

**Important:** `AZURE_OPENAI_DEPLOYMENT` must be a **vision-capable** deployment
(e.g. `gpt-4o`, `gpt-4-turbo` with vision, or `gpt-4-vision-preview`).
A text-only deployment will fail and the result will be saved with
`ai_analysis_status = "failed"` — the app will not crash.

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

## Demo workflow

1. Open **http://127.0.0.1:8000** → click **+ Add Site**.
2. Add name / location / description → save.
3. On the site page → **+ Add Observation** → upload photo, add notes, tick damage types.
4. On the observation page → **Run AI Analysis** (works in mock mode — no key needed).
5. Click **Create Risk Case** to generate a risk score and evidence report.
6. On the case page → update status (Draft → Needs Review → Verified → Routed → Closed).

---

## Running tests

```bash
cd backend
pytest tests/ -v
```

Tests do not call the real Azure OpenAI API. They cover mock mode, missing
credentials, bad JSON responses, and risk score calculation.

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

If you have an existing `data/heritagerisk.db` from before the AI fields were
added, delete it so the schema is recreated:

```bash
rm ../data/heritagerisk.db
```

Uploaded images in `data/uploads/` are unaffected.

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
    ├── database.py             # SQLAlchemy engine + session
    ├── models.py               # ORM: Site, Observation, RiskCase
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
