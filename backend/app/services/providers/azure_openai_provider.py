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
    [
        "crack",
        "erosion",
        "graffiti",
        "corrosion",
        "water_staining",
        "vegetation_growth",
        "surface_loss",
        "fire_damage",
        "other",
    ]
)

SAFETY_STATEMENT = (
    "HeritageRisk AI is for visible risk triage only. It does not replace "
    "professional conservation, engineering, emergency, legal, or cultural "
    "heritage advice."
)

_SYSTEM_PROMPT = f"""\
You are a heritage-site deterioration assessment assistant.

Analyse the provided image or images of a heritage site and identify visible signs of
deterioration. Return your analysis as a JSON object only — no prose, no
markdown fences, just raw JSON.

Rules:
- Only identify deterioration that is clearly visible in the image.
- Do not claim certainty when deterioration is ambiguous.
- Mention uncertainty in the summary when image evidence is unclear,
  obstructed, distant, or incomplete.
- Do not recommend physical repairs or invasive actions.
- Do not tell anyone to enter unsafe or structurally unstable areas.
- {SAFETY_STATEMENT}
- Human review is required.

Required JSON structure (no extra keys):
{{
  "damage_tags": [<strings from the allowed list below>],
  "severity": <integer 1–5, where 1 = minor, 5 = severe>,
  "confidence": <integer 0–100>,
  "summary": "<short description of visible risk indicators>",
  "uncertainty": "<what is unclear, obstructed, distant, or not visible>",
  "recommended_action": "<safe coordination action for human review>"
}}

Allowed damage_tag values: crack, erosion, graffiti, corrosion,
water_staining, vegetation_growth, surface_loss, fire_damage, other

If no deterioration is visible, return an empty damage_tags list, severity 1,
and your best confidence estimate.
"""


def _normalise_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/openai/v1"):
        return f"{endpoint}/"
    return f"{endpoint}/openai/v1/"


def _mock_fallback_result(image_path: str, notes: str | None) -> AIAnalysisResult:
    """Return the standard mock result without exposing Azure diagnostics."""
    from app.services.ai_analysis import _mock_analyze

    return _mock_analyze(image_path, notes)


def _encode_image(image_path: str) -> tuple[str, str]:
    """Return (base64_string, mime_type). Raises on missing or unsupported file."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise ValueError(
            f"Unsupported image format '{mime_type}'. Need JPEG, PNG, WEBP, "
            "or GIF."
        )

    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return b64, mime_type


def _validate_response(data: dict, deployment: str) -> AIAnalysisResult:
    """
    Parse the model's dict into an AIAnalysisResult.
    Any missing or out-of-range field is replaced with a safe default
    so the caller always gets a usable result.
    """
    raw_tags = data.get("damage_tags", [])
    tags = (
        [tag for tag in raw_tags if isinstance(tag, str) and tag in ALLOWED_TAGS]
        if isinstance(raw_tags, list)
        else []
    )
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

    summary = (
        str(data.get("summary", "")).strip()
        or "No summary provided by the model."
    )
    uncertainty = str(data.get("uncertainty", "")).strip() or (
        "No uncertainty statement was provided. Human verification is required."
    )
    action = (
        str(data.get("recommended_action", "")).strip()
        or "Human review required before any action is taken."
    )

    # Store the validated fields as raw JSON — never the original image bytes
    safe_raw = json.dumps({
        "damage_tags": tags,
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "uncertainty": uncertainty,
        "recommended_action": action,
    })

    return AIAnalysisResult(
        damage_tags=tags,
        severity=severity,
        confidence=confidence,
        summary=summary,
        recommended_action=action,
        provider=f"azure:{deployment}",
        raw_response=safe_raw,
        uncertainty=uncertainty,
    )


class AzureOpenAIImageAnalyzer:
    def __init__(self) -> None:
        self.endpoint = settings.azure_openai_endpoint
        self.api_key = settings.azure_openai_api_key
        self.deployment = settings.azure_openai_deployment
        self.timeout_seconds = settings.azure_openai_timeout_seconds

    def _validate_response(self, data: dict) -> AIAnalysisResult:
        return _validate_response(data, self.deployment)

    def analyze(self, image_path: str, notes: str | None = None) -> AIAnalysisResult:
        return self.analyze_many([image_path], notes)

    def analyze_many(
        self,
        image_paths: list[str],
        notes: str | None = None,
    ) -> AIAnalysisResult:
        """
        Send one or more images + notes to Azure OpenAI Vision.
        Returns a validated AIAnalysisResult; never raises.
        """
        if not self.endpoint or not self.api_key or not self.deployment:
            primary_image_path = image_paths[0] if image_paths else ""
            return _mock_fallback_result(primary_image_path, notes)

        # Lazy import — the rest of the app works even if openai isn't installed
        try:
            from openai import APIError, APIConnectionError, APIStatusError, OpenAI
        except ImportError:
            primary_image_path = image_paths[0] if image_paths else ""
            return _mock_fallback_result(primary_image_path, notes)

        user_content = []
        try:
            for image_path in image_paths:
                b64, mime_type = _encode_image(image_path)
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    }
                )
        except (FileNotFoundError, ValueError):
            primary_image_path = image_paths[0] if image_paths else ""
            return _mock_fallback_result(primary_image_path, notes)

        if not user_content:
            return _mock_fallback_result("", notes)

        notes_text = (notes or "").strip() or "No observer notes provided."
        user_content.append({"type": "text", "text": f"Observer notes: {notes_text}"})

        try:
            client = OpenAI(
                api_key=self.api_key,
                base_url=_normalise_endpoint(self.endpoint),
                timeout=self.timeout_seconds,
            )
            response = client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_completion_tokens=600,
            )
        except (APIConnectionError, APIStatusError, APIError):
            return _mock_fallback_result(image_paths[0], notes)
        except Exception:  # noqa: BLE001
            return _mock_fallback_result(image_paths[0], notes)

        try:
            content = (response.choices[0].message.content or "").strip()
            # Strip any accidental markdown fences the model sometimes adds
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
        except (IndexError, AttributeError):
            return _mock_fallback_result(image_paths[0], notes)
        except json.JSONDecodeError:
            return _mock_fallback_result(image_paths[0], notes)

        return _validate_response(data, self.deployment)
