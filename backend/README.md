# HeritageRisk AI — Backend

FastAPI backend for the HeritageRisk AI MVP.

## Prerequisites

- Python 3.11 or higher
- `pip`

## Setup

```bash
# 1. Move into the backend directory
cd backend

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

## Run the server (no AI credentials needed)

```bash
python3 run.py
```

The app starts at **http://127.0.0.1:8000**

Hot-reload is on by default — saving any `.py` file restarts the server automatically.

The app works fully without any Azure OpenAI credentials. The AI analysis
feature runs in **mock / rule-based mode** by default.

## Key URLs

| URL | What it does |
|-----|-------------|
| `http://127.0.0.1:8000/` | Dashboard |
| `http://127.0.0.1:8000/sites/new` | Add a heritage site |
| `http://127.0.0.1:8000/cases` | All risk cases |
| `http://127.0.0.1:8000/health` | Health check (returns JSON) |
| `http://127.0.0.1:8000/docs` | Interactive API docs (Swagger UI) |

## Demo workflow

1. Open the dashboard and click **+ Add Site**.
2. Fill in name / location / description and save.
3. On the site page, click **+ Add Observation**.
4. Upload a photo, write damage notes, tick damage types, set severity, and save.
5. On the observation detail page, click **Run AI Analysis** (works in mock mode — no API key needed).
6. Click **Create Risk Case** to promote the observation.
7. The risk score is calculated automatically. Open the case to update its status or view the evidence report.

## AI analysis — scaffold only (no real AI yet)

The AI analysis feature is a scaffold prepared for Azure OpenAI Vision.
The current analysis is **rule-based / mock** — it scans observer notes for
damage keywords and returns a placeholder result.

> **Warning: never commit real API keys.**
> The `.env` file is listed in `.gitignore` and must never be committed.
> Use `.env.example` as a template.

### Running without AI (default)

No configuration needed. `AI_ANALYSIS_ENABLED` defaults to `false`.
Click "Run AI Analysis" on any observation — it will return a mock result
clearly labelled as placeholder data.

### Preparing for Azure OpenAI (future)

```bash
# Copy the template
cp ../.env.example .env

# Edit .env — fill in your real Azure OpenAI values:
#   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
#   AZURE_OPENAI_API_KEY=your-real-key
#   AZURE_OPENAI_DEPLOYMENT=your-deployment-name
#   AI_ANALYSIS_ENABLED=true
```

When `AI_ANALYSIS_ENABLED=true` and all three Azure fields are set, the app
will route to the real provider. The provider implementation lives in
`app/services/providers/azure_openai_provider.py` — see the TODO comments
there for the exact implementation steps.

### AI architecture at a glance

```
app/config.py                          ← reads env vars, exposes settings object
app/services/ai_analysis.py            ← public entry point: analyze_observation_image()
app/services/providers/
    azure_openai_provider.py           ← scaffold for real Azure OpenAI call
```

The route `POST /observations/{id}/analyze` calls `analyze_observation_image()`
which routes to mock or real provider based on config. The result is saved to
the `observations` table (ai_summary, ai_confidence, ai_provider, etc.) and
displayed on the observation and case detail pages.

## Database note

The new AI fields are added to the `observations` table. SQLAlchemy creates the
table from scratch on first run. If you have an existing `data/heritagerisk.db`
from a previous session (before the AI fields were added), delete it so the
schema is recreated:

```bash
rm ../data/heritagerisk.db
```

Any previously uploaded images in `data/uploads/` are unaffected.

## File storage

| Directory | Contents |
|-----------|----------|
| `../data/uploads/` | Uploaded images (UUID-prefixed filenames) |
| `../data/heritagerisk.db` | SQLite database (auto-created on first run) |
| `../reports/` | Generated Markdown evidence reports |

These directories are gitignored. `.gitkeep` files hold their place in the repo.

## Project structure

```
backend/
├── run.py                         # Entry point: python3 run.py
├── requirements.txt
├── README.md
└── app/
    ├── main.py                    # FastAPI app, all routes
    ├── config.py                  # Env-var settings (Azure OpenAI, feature flags)
    ├── database.py                # SQLAlchemy engine + session
    ├── models.py                  # ORM: Site, Observation, RiskCase
    ├── risk.py                    # Rule-based risk scoring
    ├── reports.py                 # Markdown report generator
    ├── services/
    │   ├── ai_analysis.py         # Public AI entry point + mock fallback
    │   └── providers/
    │       └── azure_openai_provider.py   # Azure OpenAI scaffold (not yet implemented)
    ├── templates/                 # Jinja2 HTML templates
    └── static/
        └── style.css
```

../.env.example                    # Copy to .env — never commit real keys
```
