"""
AI image analysis — single entry point for the app.

  AZURE_OPENAI_ENABLED=false (default)  → mock result, no API call
  AZURE_OPENAI_ENABLED=true, no creds  → mock result with warning prefix
  AZURE_OPENAI_ENABLED=true, creds set → Azure OpenAI Vision
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from app.config import settings

# Must match the taxonomy in azure_openai_provider.py
ALLOWED_TAGS: list[str] = [
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


@dataclass
class AIAnalysisResult:
    damage_tags: list[str]
    severity: int           # 1–5
    confidence: int         # 0–100
    summary: str
    recommended_action: str
    provider: str           # "mock" | "azure:<deployment>"
    raw_response: str | None = field(default=None)
    uncertainty: str = field(
        default="No uncertainty statement was provided. Human verification is required."
    )
    schema_version: str = "2"
    structured_response: dict | None = None
    validation_error: str | None = None


def _mock_analyze(
    image_path: str,
    notes: str | None,
    image_ids: list[int] | None = None,
) -> AIAnalysisResult:
    """
    Keyword-scan the observer notes for damage indicators.
    No image or API key needed — used when Azure is disabled or unconfigured.
    """
    detected_tags: list[str] = []
    notes_lower = (notes or "").lower()

    keyword_map: dict[str, str] = {
        "crack":    "crack",
        "fracture": "crack",
        "split":    "crack",
        "graffiti": "graffiti",
        "vandal":   "graffiti",
        "tag":      "graffiti",
        "water":    "water_staining",
        "damp":     "water_staining",
        "flood":    "water_staining",
        "stain":    "water_staining",
        "leak":     "water_staining",
        "vegetation": "vegetation_growth",
        "plant":    "vegetation_growth",
        "moss":     "vegetation_growth",
        "ivy":      "vegetation_growth",
        "weed":     "vegetation_growth",
        "erosion":  "erosion",
        "erode":    "erosion",
        "wear":     "erosion",
        "surface loss": "surface_loss",
        "spalling": "surface_loss",
        "flaking":  "surface_loss",
        "corrosion": "corrosion",
        "rust":     "corrosion",
        "oxidis":   "corrosion",
        "oxidiz":   "corrosion",
        "fire":     "fire_damage",
        "burn":     "fire_damage",
        "scorch":   "fire_damage",
        "char":     "fire_damage",
    }
    for keyword, tag in keyword_map.items():
        if keyword in notes_lower and tag not in detected_tags:
            detected_tags.append(tag)

    image_present = bool(image_path and Path(image_path).exists())
    prefix = "" if image_present else "No image uploaded. "
    image_refs = list(image_ids or [])
    if not image_refs:
        image_refs = [1] if image_present else []
    if detected_tags:
        severity = min(5, max(1, len(detected_tags) + 1))
        confidence = 35 if len(detected_tags) > 1 else 20
        evidence_sufficiency = "partial"
        summary = (
            f"{prefix}Mock analysis used because Azure AI is disabled or unavailable. "
            f"Keywords detected in notes: {', '.join(detected_tags)}."
        )
        indicators = [
            {
                "indicator_type": tag,
                "evidence_location": (
                    f"keyword mention in reviewed notes; image refs {', '.join(str(ref) for ref in image_refs) or 'unavailable'}"
                ),
                "image_refs": image_refs,
                "confidence": 0.35 if len(detected_tags) > 1 else 0.2,
                "supporting_evidence": f"Reviewed notes mention {tag.replace('_', ' ')}.",
                "severity_contribution": severity,
            }
            for tag in detected_tags
        ]
        insufficient_reason = None
    else:
        detected_tags = []
        severity = 1
        confidence = 10
        evidence_sufficiency = "insufficient"
        summary = (
            f"{prefix}Mock analysis used because Azure AI is disabled or unavailable. "
            "No keyword indicators were detected in the reviewed notes."
        )
        indicators = []
        insufficient_reason = (
            "Mock fallback scans reviewed notes only and found no supported "
            "visible-risk keywords."
        )

    structured_response = {
        "schema_version": "2",
        "provider": "mock",
        "overall_summary": summary,
        "evidence_sufficiency": evidence_sufficiency,
        "indicators": indicators,
        "insufficient_reason": insufficient_reason,
    }

    return AIAnalysisResult(
        damage_tags=detected_tags,
        severity=severity,
        confidence=confidence,
        summary=summary,
        recommended_action=(
            "HeritageRisk AI is for visible risk triage only. "
            "It does not replace professional conservation, engineering, "
            "emergency, legal, or cultural heritage advice."
        ),
        provider="mock",
        raw_response=json.dumps(structured_response),
        uncertainty=(
            "High uncertainty. Mock fallback scans contributor notes and does not "
            "inspect image pixels."
        ),
        structured_response=structured_response,
    )


def analyze_observation_image(
    image_path: str,
    notes: str | None = None,
    image_id: int | None = None,
) -> AIAnalysisResult:
    """
    Analyse an observation image and return an AIAnalysisResult.
    Never raises — errors are captured inside the provider and returned
    as a result with confidence=0 so the route can always write to the DB.
    """
    if not getattr(settings, "azure_openai_enabled", False):
        return _mock_analyze(image_path, notes, [image_id] if image_id else None)

    if not settings.azure_credentials_present:
        result = _mock_analyze(image_path, notes, [image_id] if image_id else None)
        result.summary = (
            "Mock analysis used because Azure AI is disabled or unavailable. "
            + result.summary
        )
        return result

    try:
        from app.services.providers.azure_openai_provider import (
            AzureOpenAIImageAnalyzer,
        )

        return AzureOpenAIImageAnalyzer().analyze(image_path, notes, image_id=image_id)
    except Exception:  # noqa: BLE001
        return _mock_analyze(image_path, notes, [image_id] if image_id else None)


def analyze_observation_images(
    image_paths: list[str],
    notes: str | None = None,
    image_ids: list[int] | None = None,
) -> AIAnalysisResult:
    """Analyse one or more observation images behind the same fallback rules."""
    valid_paths = [path for path in image_paths if path]
    primary_image_path = valid_paths[0] if valid_paths else ""

    if not getattr(settings, "azure_openai_enabled", False):
        return _mock_analyze(primary_image_path, notes, image_ids)

    if not settings.azure_credentials_present:
        result = _mock_analyze(primary_image_path, notes, image_ids)
        result.summary = (
            "Mock analysis used because Azure AI is disabled or unavailable. "
            + result.summary
        )
        return result

    try:
        from app.services.providers.azure_openai_provider import (
            AzureOpenAIImageAnalyzer,
        )

        return AzureOpenAIImageAnalyzer().analyze_many(valid_paths, notes, image_ids=image_ids)
    except Exception:  # noqa: BLE001
        return _mock_analyze(primary_image_path, notes, image_ids)
