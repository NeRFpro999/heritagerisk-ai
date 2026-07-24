"""
Application configuration — reads from environment variables.

No credentials are hardcoded here. Public submission and offline mock analysis
remain available without Azure settings; reviewer actions fail closed until the
single reviewer credential is configured.
"""

import os
from pathlib import Path

# Load .env automatically when running locally.
# python-dotenv is a dev dependency; it's a no-op if the file doesn't exist.
# In production, set real environment variables directly — never commit .env.
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(_env_path, override=False)  # override=False: real env vars always win
except ImportError:
    pass  # python-dotenv not installed — fine, rely on environment variables


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


class Settings:
    # ── Azure OpenAI (all optional — app works without them) ──────────────────
    azure_openai_endpoint: str = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.environ.get("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.environ.get("AZURE_OPENAI_PRIMARY_DEPLOYMENT", "")
    azure_openai_timeout_seconds: float = _float_env("AZURE_OPENAI_TIMEOUT_SECONDS", 30)

    # Reviewer authentication fails closed when either credential is absent.
    reviewer_username: str = os.environ.get("REVIEWER_USERNAME", "")
    reviewer_password_hash: str = os.environ.get("REVIEWER_PASSWORD_HASH", "")
    session_secret_key: str = os.environ.get("SESSION_SECRET_KEY", "")

    # ── Feature flag ──────────────────────────────────────────────────────────
    # Set AZURE_OPENAI_ENABLED=true in your .env to activate real AI calls.
    # When false (the default), the app uses a rule-based mock instead.
    azure_openai_enabled: bool = os.environ.get("AZURE_OPENAI_ENABLED", "false").lower() == "true"
    ai_analysis_enabled: bool = azure_openai_enabled

    @property
    def azure_credentials_present(self) -> bool:
        """True only when all three required Azure fields are non-empty."""
        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_deployment
        )


# Single shared instance — import this everywhere instead of re-reading env vars.
settings = Settings()
