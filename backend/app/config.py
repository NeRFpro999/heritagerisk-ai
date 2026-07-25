"""
Application configuration — reads from environment variables.

No credentials are hardcoded here. Public submission and offline mock analysis
remain available without Azure settings; reviewer actions fail closed until the
single reviewer credential is configured.
"""

import logging
import os
from pathlib import Path
from typing import Mapping

# Load .env automatically when running locally.
# python-dotenv is a dev dependency; it's a no-op if the file doesn't exist.
# In production, set real environment variables directly — never commit .env.
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(_env_path, override=False)  # override=False: real env vars always win
except ImportError:
    pass  # python-dotenv not installed — fine, rely on environment variables


logger = logging.getLogger(__name__)


def _float_env(environ: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(environ.get(name, str(default)))
    except ValueError:
        return default


class Settings:
    """Environment-backed settings with fail-safe Azure activation."""

    REQUIRED_AZURE_VARIABLES = (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    )

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        values = os.environ if environ is None else environ

        self.azure_openai_endpoint = values.get(
            "AZURE_OPENAI_ENDPOINT",
            "",
        ).strip()
        self.azure_openai_api_key = values.get(
            "AZURE_OPENAI_API_KEY",
            "",
        ).strip()
        self.azure_openai_deployment = values.get(
            "AZURE_OPENAI_DEPLOYMENT",
            "",
        ).strip()
        self.azure_openai_api_version = values.get(
            "AZURE_OPENAI_API_VERSION",
            "",
        ).strip()
        self.azure_openai_timeout_seconds = _float_env(
            values,
            "AZURE_OPENAI_TIMEOUT_SECONDS",
            30,
        )

        self.reviewer_username = values.get("REVIEWER_USERNAME", "")
        self.reviewer_password_hash = values.get("REVIEWER_PASSWORD_HASH", "")
        self.session_secret_key = values.get("SESSION_SECRET_KEY", "")

        self.azure_openai_requested = (
            values.get("AZURE_OPENAI_ENABLED", "false").lower() == "true"
        )
        self.azure_missing_variables = tuple(
            name
            for name in self.REQUIRED_AZURE_VARIABLES
            if not values.get(name, "").strip()
        )
        self.azure_api_version_supported = (
            self.azure_openai_api_version.lower() == "v1"
        )
        self.azure_credentials_present = bool(
            not self.azure_missing_variables
            and self.azure_api_version_supported
        )
        self.azure_openai_enabled = bool(
            self.azure_openai_requested
            and self.azure_credentials_present
        )
        self.ai_analysis_enabled = self.azure_openai_enabled

        if self.azure_openai_requested and self.azure_missing_variables:
            logger.warning(
                "Azure OpenAI was requested but is disabled because required "
                "environment variables are missing: %s. Mock analysis remains active.",
                ", ".join(self.azure_missing_variables),
            )
        elif self.azure_openai_requested and not self.azure_api_version_supported:
            logger.warning(
                "Azure OpenAI was requested but is disabled because "
                "AZURE_OPENAI_API_VERSION must be 'v1' for the configured v1 "
                "endpoint. Mock analysis remains active."
            )


settings = Settings()
