"""
Azure OpenAI Vision provider.

Sends the uploaded image + observer notes to Azure OpenAI for damage analysis.
Returns a validated AIAnalysisResult. The public function is analyze().

Result is for human review only — does not replace professional conservation,
engineering, cultural heritage, or emergency assessment.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

from app.config import settings
from app.services.ai_analysis import AIAnalysisResult

ALLOWED_TAGS: frozenset[str] = frozenset(
    ["crack", "graffiti", "water_staining", "vegetation_growth", "erosion", "corrosion", "other"]
)

_SYSTEM_PROMPT = """\
You are a heritage-site deterioration assessment assistant.

Analyse the provided image of a heritage site and identify visible signs of
deterioration. Return your analysis as a JSON object only — no prose, no
markdown fences, just raw JSON.

Rules:
- Only identify deterioration that is clearly visible in the image.
- Do not claim certainty when deterioration is ambiguous.
- Do not recommend physical repairs or invasive actions.
- Do not tell anyone to enter unsafe or structurally unstable areas.
- This output is for human review only.

Required JSON structure (no extra keys):
{
  "damage_tags": [<strings from the allowed list below>],
  "severity": <integer 1–5, where 1 = minor, 5 = severe>,
  "confidence": <integer 0–100>,
  "summary": "<short description of visible risk indicators>",
  "recommended_action": "<safe coordination action for human review>"
}

Allowed damage_tag values: crack, graffiti, water_staining, vegetation_growth, erosion, corrosion, other

If no deterioration is visible, return an empty damage_tags list, severity 1,
and your best confidence estimate.
"""


def _parse_error_result(reason: str) -> AIAnalysisResult:
    """Safe fallback when the API call or JSON parsing fails."""
    return AIAnalysisResult(
        damage_tags=["other"],
        severity=1,
        confidence=0,
        summary=(
            f"Azure OpenAI analysis could not be completed: {reason}. "
            "The observation has been saved and can be reviewed manually."
        ),
        recommended_action="Human review required before any action is taken.",
        provider="azure_openai",
        raw_response=None,
    )


def _encode_image(image_path: str) -> tuple[str, str]:
    """Return (base64_string, mime_type). Raises on missing or unsupported file."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise ValueError(f"Unsupported image format '{mime_type}'. Need JPEG, PNG, WEBP, or GIF.")

    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return b64, mime_type


def _validate_response(data: dict) -> AIAnalysisResult:
    """
    Parse the model's dict into an AIAnalysisResult.
    Any missing or out-of-range field is replaced with a safe default
    so the caller always gets a usable result.
    """
    raw_tags = data.get("damage_tags", [])
    tags = [t for t in raw_tags if isinstance(t, str) and t in ALLOWED_TAGS] if isinstance(raw_tags, list) else []
    if not tags:
        tags = ["other"]

    try:
        severity = max(1, min(5, int(data.get("severity", 1))))
    except (TypeError, ValueError):
        severity = 1

    try:
        confidence = max(0, min(100, int(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0

    summary = str(data.get("summary", "")).strip() or "No summary provided by the model."
    action = str(data.get("recommended_action", "")).strip() or "Human review required before any action is taken."

    # Store the validated fields as raw JSON — never the original image bytes
    safe_raw = json.dumps({
        "damage_tags": tags,
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "recommended_action": action,
    })

    return AIAnalysisResult(
        damage_tags=tags,
        severity=severity,
        confidence=confidence,
        summary=summary,
        recommended_action=action,
        provider="azure_openai",
        raw_response=safe_raw,
    )


class AzureOpenAIImageAnalyzer:
    def __init__(self) -> None:
        # Fail fast if credentials are missing — the caller in ai_analysis.py
        # only instantiates this when azure_credentials_present is True, so
        # this check exists as a safety net for direct usage.
        missing = [
            name for name, val in [
                ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
                ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
                ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
            ] if not val
        ]
        if missing:
            raise EnvironmentError(
                f"Azure OpenAI provider is missing required environment variables: "
                f"{', '.join(missing)}. Set them in your .env file (see .env.example)."
            )

    def _validate_response(self, data: dict) -> AIAnalysisResult:
        return _validate_response(data)

    def analyze(self, image_path: str, notes: str | None = None) -> AIAnalysisResult:
        """
        Send image + notes to Azure OpenAI Vision.
        Returns a validated AIAnalysisResult; never raises.
        """
        # Lazy import — the rest of the app works even if openai isn't installed
        try:
            from openai import AzureOpenAI, APIError, APIConnectionError, AuthenticationError
        except ImportError:
            return _parse_error_result("the 'openai' package is not installed (run: pip install openai)")

        try:
            b64, mime_type = _encode_image(image_path)
        except FileNotFoundError:
            return _parse_error_result("image file not found on disk")
        except ValueError as exc:
            return _parse_error_result(str(exc))

        notes_text = (notes or "").strip() or "No observer notes provided."
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            {"type": "text", "text": f"Observer notes: {notes_text}"},
        ]

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
                temperature=0.1,
            )
        except AuthenticationError:
            return _parse_error_result("authentication failed — check AZURE_OPENAI_API_KEY")
        except APIConnectionError:
            return _parse_error_result("could not reach endpoint — check AZURE_OPENAI_ENDPOINT")
        except APIError as exc:
            return _parse_error_result(f"API error (status {getattr(exc, 'status_code', 'unknown')})")
        except Exception as exc:  # noqa: BLE001
            return _parse_error_result(f"unexpected error ({type(exc).__name__})")

        try:
            content = (response.choices[0].message.content or "").strip()
            # Strip any accidental markdown fences the model sometimes adds
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
        except (IndexError, AttributeError):
            return _parse_error_result("model returned an empty response")
        except json.JSONDecodeError:
            return _parse_error_result("model response was not valid JSON")

        return _validate_response(data)
