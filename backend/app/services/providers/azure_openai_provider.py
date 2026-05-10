"""
Azure OpenAI Vision provider — SCAFFOLD ONLY. No real API call is made yet.

When you are ready to implement:
  1. pip install openai>=1.0.0  (the official OpenAI Python SDK works with Azure)
  2. Encode the image as base64 and build a chat/completions request with a
     vision-capable model (e.g. gpt-4o or gpt-4-vision-preview).
  3. Parse the JSON response into an AIAnalysisResult.
  4. In app/services/ai_analysis.py, uncomment the import and routing block
     that calls this class.

Azure OpenAI Vision docs:
  https://learn.microsoft.com/azure/ai-services/openai/how-to/gpt-with-vision
"""

from __future__ import annotations

from app.config import settings
from app.services.ai_analysis import AIAnalysisResult


class AzureOpenAIImageAnalyzer:
    """
    Sends an uploaded heritage-site image plus observer notes to Azure OpenAI
    for visual damage analysis, returning structured damage tags and a summary.
    """

    def __init__(self) -> None:
        self._validate_config()

    def _validate_config(self) -> None:
        """Raise early with a clear message if credentials are not configured."""
        missing = []
        if not settings.azure_openai_endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not settings.azure_openai_api_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if not settings.azure_openai_deployment:
            missing.append("AZURE_OPENAI_DEPLOYMENT")
        if missing:
            raise EnvironmentError(
                f"Azure OpenAI provider is missing required environment variables: "
                f"{', '.join(missing)}. "
                f"Set them in your .env file (see .env.example)."
            )

    def analyze(self, image_path: str, notes: str | None = None) -> AIAnalysisResult:
        """
        Analyse the image at image_path using Azure OpenAI Vision.

        TODO: Implement this method when you are ready to connect real AI.

        Steps to implement:
          1. Load and base64-encode the image file.
          2. Build the Azure OpenAI chat/completions request:
               - Use the model from settings.azure_openai_deployment.
               - Send a system prompt describing the heritage damage taxonomy.
               - Include the base64 image as an image_url content block.
               - Include observer notes as a text content block.
               - Ask the model to return structured JSON:
                   { "damage_tags": [...], "severity": 1-5,
                     "summary": "...", "recommended_action": "..." }
          3. Parse the JSON from the model's response content.
          4. Return AIAnalysisResult(
               damage_tags=..., severity=..., confidence=...,
               summary=..., recommended_action=...,
               provider="azure_openai",
               raw_response=<raw JSON string>,
             )

        Example SDK call (pseudocode):
            from openai import AzureOpenAI
            client = AzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
            )
            response = client.chat.completions.create(
                model=settings.azure_openai_deployment,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": notes or "No notes provided."},
                    ]},
                ],
                max_tokens=500,
            )
        """
        raise NotImplementedError(
            "AzureOpenAIImageAnalyzer.analyze() is a scaffold — "
            "the real API call has not been implemented yet. "
            "See the TODO comments in this file for implementation steps."
        )
