"""
Application configuration — reads from environment variables.

No API keys are hardcoded here. Copy .env.example to .env and fill in
real values only when you are ready to connect to Azure OpenAI.
The app runs fully without any of these values set.
"""

import os


class Settings:
    # ── Azure OpenAI (all optional — app works without them) ──────────────────
    azure_openai_endpoint: str = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.environ.get("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
    azure_openai_api_version: str = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")

    # ── Feature flag ──────────────────────────────────────────────────────────
    # Set AI_ANALYSIS_ENABLED=true in your .env to activate real AI calls.
    # When false (the default), the app uses a rule-based mock instead.
    ai_analysis_enabled: bool = os.environ.get("AI_ANALYSIS_ENABLED", "false").lower() == "true"

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
