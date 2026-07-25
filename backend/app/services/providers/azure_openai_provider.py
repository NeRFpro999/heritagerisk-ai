"""
Azure OpenAI Vision provider.

Sends the uploaded image + observer notes to Azure OpenAI for damage analysis.
Returns a validated AIAnalysisResult. The public function is analyze().

Result is for human review only — does not replace professional conservation,
engineering, cultural heritage, or emergency assessment.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from pathlib import Path

from app.ai_schema import validate_analysis_result, validation_error_text
from app.config import settings
from app.services.ai_analysis import (
    AIAnalysisResult,
    AZURE_API_DIAGNOSTIC,
    AZURE_CONFIGURATION_DIAGNOSTIC,
    AZURE_IMAGE_DIAGNOSTIC,
    AZURE_IMPORT_DIAGNOSTIC,
    AZURE_NO_IMAGES_DIAGNOSTIC,
    AZURE_PROVIDER_DIAGNOSTIC,
    AZURE_TRANSPORT_DIAGNOSTIC,
    _mock_after_azure_failure,
)

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

_SYSTEM_PROMPT_TEMPLATE = """\
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
- <safety-statement>
- Human review is required.

Required JSON structure (no extra keys):
{
  "schema_version": "2",
  "provider": "azure:<deployment>",
  "overall_summary": "<short summary of visible evidence only>",
  "evidence_sufficiency": "sufficient" | "partial" | "insufficient",
  "indicators": [
    {
      "indicator_type": "<one allowed damage tag>",
      "evidence_location": "<free text, e.g. upper left of image 2>",
      "image_refs": [<integer image ids provided by the user prompt>],
      "confidence": <number from 0 to 1>,
      "supporting_evidence": "<short quote of what is visibly present>",
      "severity_contribution": <integer 1-5>
    }
  ],
  "insufficient_reason": "<required only when evidence_sufficiency is insufficient>"
}

Allowed damage_tag values: crack, erosion, graffiti, corrosion,
water_staining, vegetation_growth, surface_loss, fire_damage, other

Returning zero indicators with evidence_sufficiency="insufficient" is valid and
sometimes preferable. Use it when the images do not show enough visible evidence
to support a specific indicator. Do not diagnose causes, hidden damage,
structural safety, legal status, urgency, or whether a place is safe to enter.
"""

PROMPT_SETTINGS = {
    "max_completion_tokens": 600,
    "response_format": {"type": "json_object"},
}


def _render_system_prompt(deployment: str) -> str:
    return (
        _SYSTEM_PROMPT_TEMPLATE
        .replace("<deployment>", deployment)
        .replace("<safety-statement>", SAFETY_STATEMENT)
    )


def _canonical_json_sha256(payload: dict) -> str:
    material = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def analysis_prompt_template_configuration(
    deployment: str | None = None,
) -> dict:
    """Return the static prompt template and transmitted request settings."""
    resolved_deployment = (
        deployment or settings.azure_openai_deployment or "mock"
    )
    return {
        "system_prompt": _render_system_prompt(resolved_deployment),
        "request_settings": PROMPT_SETTINGS,
        "deployment": resolved_deployment,
    }


def analysis_prompt_template_sha256(deployment: str | None = None) -> str:
    return _canonical_json_sha256(
        analysis_prompt_template_configuration(deployment)
    )


def _analysis_notes_text(notes: str | None, image_ids: list[int] | None = None) -> str:
    notes_text = (notes or "").strip() or "No observer notes provided."
    if image_ids:
        notes_text += (
            "\nSubmitted image database ids in display order: "
            + ", ".join(str(image_id) for image_id in image_ids)
            + ". Use only these integer ids in indicator.image_refs."
        )
    return notes_text


def _normalise_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/openai/v1"):
        return f"{endpoint}/"
    return f"{endpoint}/openai/v1/"


def _mock_fallback_result(
    image_path: str,
    notes: str | None,
    image_ids: list[int] | None,
    *,
    deployment: object,
    diagnostic: str,
) -> AIAnalysisResult:
    """Return a mock result after one sanitized Azure failure attempt."""
    return _mock_after_azure_failure(
        image_path,
        notes,
        image_ids,
        deployment=deployment,
        diagnostic=diagnostic,
    )


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


def build_analysis_request_payload(
    image_paths: list[str],
    notes: str | None,
    image_ids: list[int] | None,
    deployment: str,
) -> dict:
    """Build the exact Chat Completions arguments used by Azure analysis."""
    user_content = []
    for image_path in image_paths:
        b64, mime_type = _encode_image(image_path)
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            }
        )
    if not user_content:
        raise ValueError("At least one image is required.")

    notes_text = _analysis_notes_text(notes, image_ids)
    user_content.append({"type": "text", "text": f"Observer notes: {notes_text}"})
    return {
        "model": deployment,
        "messages": [
            {"role": "system", "content": _render_system_prompt(deployment)},
            {"role": "user", "content": user_content},
        ],
        **PROMPT_SETTINGS,
    }


def analysis_rendered_request_sha256(
    image_paths: list[str],
    notes: str | None,
    image_ids: list[int] | None,
    deployment: str,
) -> str:
    """Hash a canonical form of the final request without storing its content."""
    return _canonical_json_sha256(
        build_analysis_request_payload(
            image_paths,
            notes,
            image_ids,
            deployment,
        )
    )


def _with_rendered_request_hash(
    result: AIAnalysisResult,
    request_payload: dict,
) -> AIAnalysisResult:
    result.rendered_request_sha256 = _canonical_json_sha256(request_payload)
    return result


def _failed_validation_result(raw_payload, deployment: str, error: str) -> AIAnalysisResult:
    safe_raw = json.dumps(
        {
            "schema_version": "2",
            "validation_status": "failed",
            "provider": f"azure:{deployment}",
            "validation_error": error,
            "raw_payload": raw_payload,
        }
    )

    return AIAnalysisResult(
        damage_tags=[],
        severity=1,
        confidence=0,
        summary="Azure OpenAI returned a response that failed schema validation.",
        recommended_action="Human review required before any action is taken.",
        provider=f"azure:{deployment}",
        raw_response=safe_raw,
        uncertainty="AI response validation failed.",
        validation_error=error,
        structured_response=None,
    )


def _validate_response(
    data: dict,
    deployment: str,
    image_ids: list[int] | None = None,
) -> AIAnalysisResult:
    try:
        result = validate_analysis_result(
            data,
            allowed_image_ids=set(image_ids or []) if image_ids is not None else None,
        )
    except Exception as exc:  # noqa: BLE001
        return _failed_validation_result(data, deployment, validation_error_text(exc))

    tags = [indicator.indicator_type for indicator in result.indicators]
    severity = max(
        [indicator.severity_contribution for indicator in result.indicators],
        default=1,
    )
    confidence = int(
        round(
            max([indicator.confidence for indicator in result.indicators], default=0)
            * 100
        )
    )
    safe_payload = result.model_dump()
    safe_payload["provider"] = f"azure:{deployment}"
    summary = result.overall_summary
    if result.evidence_sufficiency == "insufficient":
        summary = "No visible indicators confirmed. " + summary

    return AIAnalysisResult(
        damage_tags=tags,
        severity=severity,
        confidence=confidence,
        summary=summary,
        recommended_action=(
            "HeritageRisk AI is for visible risk triage only. Human review is "
            "required before any action."
        ),
        provider=f"azure:{deployment}",
        raw_response=json.dumps(safe_payload),
        uncertainty=result.insufficient_reason
        or f"Evidence sufficiency: {result.evidence_sufficiency}.",
        structured_response=safe_payload,
    )

class AzureOpenAIImageAnalyzer:
    def __init__(self) -> None:
        self.endpoint = settings.azure_openai_endpoint
        self.api_key = settings.azure_openai_api_key
        self.deployment = settings.azure_openai_deployment
        self.api_version = settings.azure_openai_api_version
        self.timeout_seconds = settings.azure_openai_timeout_seconds

    def _validate_response(
        self,
        data: dict,
        image_ids: list[int] | None = None,
    ) -> AIAnalysisResult:
        return _validate_response(data, self.deployment, image_ids)

    def analyze(
        self,
        image_path: str,
        notes: str | None = None,
        image_id: int | None = None,
    ) -> AIAnalysisResult:
        return self.analyze_many(
            [image_path],
            notes,
            image_ids=[image_id] if image_id else None,
        )

    def analyze_many(
        self,
        image_paths: list[str],
        notes: str | None = None,
        image_ids: list[int] | None = None,
    ) -> AIAnalysisResult:
        """
        Send one or more images + notes to Azure OpenAI Vision.
        Returns a validated AIAnalysisResult; never raises.
        """
        if (
            not self.endpoint
            or not self.api_key
            or not self.deployment
            or not self.api_version
        ):
            primary_image_path = image_paths[0] if image_paths else ""
            return _mock_fallback_result(
                primary_image_path,
                notes,
                image_ids,
                deployment=self.deployment,
                diagnostic=AZURE_CONFIGURATION_DIAGNOSTIC,
            )

        if not image_paths:
            return _mock_fallback_result(
                "",
                notes,
                image_ids,
                deployment=self.deployment,
                diagnostic=AZURE_NO_IMAGES_DIAGNOSTIC,
            )

        # Lazy import — the rest of the app works even if openai isn't installed
        try:
            from openai import APIError, APIConnectionError, APIStatusError, OpenAI
        except ImportError:
            primary_image_path = image_paths[0] if image_paths else ""
            return _mock_fallback_result(
                primary_image_path,
                notes,
                image_ids,
                deployment=self.deployment,
                diagnostic=AZURE_IMPORT_DIAGNOSTIC,
            )

        try:
            request_payload = build_analysis_request_payload(
                image_paths,
                notes,
                image_ids,
                self.deployment,
            )
        except (FileNotFoundError, OSError, ValueError):
            primary_image_path = image_paths[0] if image_paths else ""
            return _mock_fallback_result(
                primary_image_path,
                notes,
                image_ids,
                deployment=self.deployment,
                diagnostic=AZURE_IMAGE_DIAGNOSTIC,
            )

        try:
            # Azure's v1 endpoint does not accept an api-version query parameter.
            # The explicit setting is validated as "v1" during configuration.
            client = OpenAI(
                api_key=self.api_key,
                base_url=_normalise_endpoint(self.endpoint),
                timeout=self.timeout_seconds,
            )
            response = client.chat.completions.create(**request_payload)
        except APIConnectionError:
            return _with_rendered_request_hash(
                _mock_fallback_result(
                    image_paths[0],
                    notes,
                    image_ids,
                    deployment=self.deployment,
                    diagnostic=AZURE_TRANSPORT_DIAGNOSTIC,
                ),
                request_payload,
            )
        except (APIStatusError, APIError):
            return _with_rendered_request_hash(
                _mock_fallback_result(
                    image_paths[0],
                    notes,
                    image_ids,
                    deployment=self.deployment,
                    diagnostic=AZURE_API_DIAGNOSTIC,
                ),
                request_payload,
            )
        except Exception:  # noqa: BLE001
            return _with_rendered_request_hash(
                _mock_fallback_result(
                    image_paths[0],
                    notes,
                    image_ids,
                    deployment=self.deployment,
                    diagnostic=AZURE_PROVIDER_DIAGNOSTIC,
                ),
                request_payload,
            )

        try:
            content = (response.choices[0].message.content or "").strip()
            # Strip any accidental markdown fences the model sometimes adds
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
        except (IndexError, AttributeError):
            return _with_rendered_request_hash(
                _failed_validation_result(
                    "",
                    self.deployment,
                    "Azure response was missing message content.",
                ),
                request_payload,
            )
        except json.JSONDecodeError:
            return _with_rendered_request_hash(
                _failed_validation_result(
                    content,
                    self.deployment,
                    "Azure response was not valid JSON.",
                ),
                request_payload,
            )

        return _with_rendered_request_hash(
            _validate_response(data, self.deployment, image_ids),
            request_payload,
        )
