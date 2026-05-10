"""
Azure OpenAI Vision provider.

Sends an uploaded heritage-site image plus observer notes to Azure OpenAI
for visual damage analysis, returning structured damage tags and a summary.

The result is for human review only. It does not replace professional
conservation, engineering, cultural heritage, or emergency assessment.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

from app.config import settings
from app.services.ai_analysis import AIAnalysisResult

# ── Taxonomy ──────────────────────────────────────────────────────────────────
# The model is asked to pick only from this set. Anything it returns outside
# this set is silently dropped during validation.
ALLOWED_TAGS: frozenset[str] = frozenset(
    ["crack", "graffiti", "water_staining", "vegetation_growth", "erosion", "corrosion", "other"]
)

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a heritage-site deterioration assessment assistant.

Your task:
Analyse the provided image of a heritage site or heritage structure and identify
visible signs of deterioration. Return your analysis as a JSON object only —
no prose, no markdown fences, just the raw JSON.

Rules you must follow:
- Only identify deterioration that is clearly visible in the image.
- Do not claim certainty when deterioration is ambiguous.
- Do not recommend physical repairs, invasive actions, or work by untrained users.
- Do not tell anyone to enter unsafe, restricted, or structurally unstable areas.
- This output is for human review only. It does not replace a professional
  conservation, engineering, cultural heritage, or emergency assessment.

Required JSON output — return exactly this structure, no extra keys:
{
  "damage_tags": [<list of strings — choose only from the allowed values below>],
  "severity": <integer 1 to 5, where 1 = minor, 5 = severe>,
  "confidence": <integer 0 to 100 reflecting your confidence in the assessment>,
  "summary": "<short human-readable description of visible risk indicators>",
  "recommended_action": "<safe coordination action for human review — e.g. schedule inspection>"
}

Allowed damage_tag values (use only these exact strings):
  crack, graffiti, water_staining, vegetation_growth, erosion, corrosion, other

If no deterioration is visible, return an empty damage_tags list and set
severity to 1 and confidence to your best estimate.
"""


# ── Safe fallback result ──────────────────────────────────────────────────────

def _parse_error_result(reason: str) -> AIAnalysisResult:
    """Return a safe, clearly-labelled result when parsing or API fails."""
    return AIAnalysisResult(
        damage_tags=["other"],
        severity=1,
        confidence=0,
        summary=(
            f"Azure OpenAI analysis could not be parsed: {reason}. "
            "The observation has been saved and can be reviewed manually."
        ),
        recommended_action="Human review required before any action is taken.",
        provider="azure_openai",
        raw_response=None,
    )


# ── Provider ──────────────────────────────────────────────────────────────────

class AzureOpenAIImageAnalyzer:
    """Calls Azure OpenAI Vision and returns a validated AIAnalysisResult."""

    def __init__(self) -> None:
        self._validate_config()

    def _validate_config(self) -> None:
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
                f"{', '.join(missing)}. Set them in your .env file (see .env.example)."
            )

    # ── Image encoding ────────────────────────────────────────────────────────

    def _encode_image(self, image_path: str) -> tuple[str, str]:
        """
        Read image file and return (base64_string, mime_type).
        Raises FileNotFoundError if the path does not exist.
        Raises ValueError for unsupported formats.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        mime_type, _ = mimetypes.guess_type(str(path))
        supported = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if mime_type not in supported:
            raise ValueError(
                f"Unsupported image format '{mime_type}'. "
                f"Supported: JPEG, PNG, WEBP, GIF."
            )

        raw_bytes = path.read_bytes()
        b64 = base64.standard_b64encode(raw_bytes).decode("ascii")
        return b64, mime_type

    # ── Response validation ───────────────────────────────────────────────────

    def _validate_response(self, data: dict) -> AIAnalysisResult:
        """
        Parse and validate the dict the model returned.
        Any field that is missing or out of range is replaced with a safe default
        rather than crashing — the caller always gets a usable result.
        """
        # damage_tags: keep only allowed values
        raw_tags = data.get("damage_tags", [])
        if not isinstance(raw_tags, list):
            raw_tags = []
        tags = [t for t in raw_tags if isinstance(t, str) and t in ALLOWED_TAGS]
        if not tags:
            tags = ["other"]

        # severity: integer 1–5
        try:
            severity = int(data.get("severity", 1))
            severity = max(1, min(5, severity))
        except (TypeError, ValueError):
            severity = 1

        # confidence: integer 0–100
        try:
            confidence = int(data.get("confidence", 0))
            confidence = max(0, min(100, confidence))
        except (TypeError, ValueError):
            confidence = 0

        # summary: non-empty string
        summary = str(data.get("summary", "")).strip()
        if not summary:
            summary = "No summary provided by the model."

        # recommended_action: non-empty string
        action = str(data.get("recommended_action", "")).strip()
        if not action:
            action = "Human review required before any action is taken."

        # raw_response: store the original JSON fields only — never image data
        safe_raw = json.dumps(
            {
                "damage_tags": tags,
                "severity": severity,
                "confidence": confidence,
                "summary": summary,
                "recommended_action": action,
            }
        )

        return AIAnalysisResult(
            damage_tags=tags,
            severity=severity,
            confidence=confidence,
            summary=summary,
            recommended_action=action,
            provider="azure_openai",
            raw_response=safe_raw,
        )

    # ── Main entry point ──────────────────────────────────────────────────────

    def analyze(self, image_path: str, notes: str | None = None) -> AIAnalysisResult:
        """
        Send the image and observer notes to Azure OpenAI Vision.
        Returns a validated AIAnalysisResult.

        On any error (network, auth, bad JSON, missing image) this method
        returns a safe fallback result rather than raising — the route layer
        catches the provider-level status.
        """
        # Lazy import: only import openai when this code path is actually reached.
        # This means the rest of the app works fine even if openai is not installed.
        try:
            from openai import AzureOpenAI, APIError, APIConnectionError, AuthenticationError
        except ImportError:
            return _parse_error_result(
                "The 'openai' package is not installed. Run: pip install openai"
            )

        # Encode image
        try:
            b64, mime_type = self._encode_image(image_path)
        except FileNotFoundError:
            return _parse_error_result("Image file not found on disk.")
        except ValueError as exc:
            return _parse_error_result(str(exc))

        # Build user message
        notes_text = (notes or "").strip() or "No observer notes provided."
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            },
            {
                "type": "text",
                "text": f"Observer notes: {notes_text}",
            },
        ]

        # Call Azure OpenAI
        try:
            client = AzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
            )
            response = client.chat.completions.create(
                model=settings.azure_openai_deployment,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=600,
                temperature=0.1,  # low temperature for consistent structured output
            )
        except AuthenticationError:
            return _parse_error_result(
                "Azure OpenAI authentication failed. Check AZURE_OPENAI_API_KEY."
            )
        except APIConnectionError:
            return _parse_error_result(
                "Could not reach Azure OpenAI endpoint. Check AZURE_OPENAI_ENDPOINT."
            )
        except APIError as exc:
            # APIError carries a status_code; log the code, not the full message
            # which might reflect request content
            return _parse_error_result(
                f"Azure OpenAI API error (status {getattr(exc, 'status_code', 'unknown')})."
            )
        except Exception as exc:  # noqa: BLE001
            # Catch-all: surface type only, not message, to avoid leaking details
            return _parse_error_result(
                f"Unexpected error calling Azure OpenAI ({type(exc).__name__})."
            )

        # Extract and parse response text
        try:
            content = response.choices[0].message.content or ""
            # Strip accidental markdown fences the model sometimes adds
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
        except (IndexError, AttributeError):
            return _parse_error_result("Model returned an empty response.")
        except json.JSONDecodeError:
            return _parse_error_result("Model response was not valid JSON.")

        return self._validate_response(data)
