"""
AI image analysis service — single public entry point for the app.

Routing:
  AI_ANALYSIS_ENABLED=false (default) → mock result, no API call
  AI_ANALYSIS_ENABLED=true + credentials missing → mock result with warning
  AI_ANALYSIS_ENABLED=true + credentials present → Azure OpenAI Vision

To add a new provider in the future, add a branch at the bottom of
analyze_observation_image(). Nothing else in the app needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

# Allowed damage tags — must match the taxonomy in azure_openai_provider.py
ALLOWED_TAGS: list[str] = [
    "crack",
    "graffiti",
    "water_staining",
    "vegetation_growth",
    "erosion",
    "corrosion",
    "other",
]


@dataclass
class AIAnalysisResult:
    """Structured result returned by any analysis provider."""

    damage_tags: list[str]
    severity: int           # 1–5
    confidence: int         # 0–100
    summary: str
    recommended_action: str
    provider: str           # "mock" | "azure_openai"
    raw_response: str | None = field(default=None)


# ── Mock / rule-based fallback ─────────────────────────────────────────────────

def _mock_analyze(image_path: str, notes: str | None) -> AIAnalysisResult:
    """
    Returns a deterministic placeholder result by scanning the observer's notes
    for damage keywords. No image file or API key is required.

    Uses the same tag taxonomy as the Azure OpenAI provider so mock and real
    results are stored and displayed consistently.
    """
    detected_tags: list[str] = []
    notes_lower = (notes or "").lower()

    keyword_map: dict[str, str] = {
        "crack": "crack",
        "fracture": "crack",
        "split": "crack",
        "graffiti": "graffiti",
        "vandal": "graffiti",
        "tag": "graffiti",
        "water": "water_staining",
        "damp": "water_staining",
        "flood": "water_staining",
        "stain": "water_staining",
        "leak": "water_staining",
        "vegetation": "vegetation_growth",
        "plant": "vegetation_growth",
        "moss": "vegetation_growth",
        "ivy": "vegetation_growth",
        "weed": "vegetation_growth",
        "erosion": "erosion",
        "erode": "erosion",
        "wear": "erosion",
        "corrosion": "corrosion",
        "rust": "corrosion",
        "oxidis": "corrosion",
        "oxidiz": "corrosion",
    }
    for keyword, tag in keyword_map.items():
        if keyword in notes_lower and tag not in detected_tags:
            detected_tags.append(tag)

    image_present = bool(image_path and Path(image_path).exists())
    if not detected_tags:
        detected_tags = ["other"]

    severity = min(5, max(1, len(detected_tags) + 1))
    confidence = 35 if len(detected_tags) > 1 else 20

    prefix = "" if image_present else "No image available for visual analysis. "
    summary = (
        f"{prefix}Rule-based mock detected possible indicators from notes: "
        f"{', '.join(detected_tags)}. "
        "This is NOT a real AI result — connect Azure OpenAI Vision for real analysis."
    )

    return AIAnalysisResult(
        damage_tags=detected_tags,
        severity=severity,
        confidence=confidence,
        summary=summary,
        recommended_action=(
            "Schedule an in-person inspection to verify these findings before any action."
        ),
        provider="mock",
        raw_response=None,
    )


# ── Public entry point ─────────────────────────────────────────────────────────

def analyze_observation_image(
    image_path: str,
    notes: str | None = None,
) -> AIAnalysisResult:
    """
    Analyse an observation image and return an AIAnalysisResult.

    This function never raises — all errors are captured inside the provider
    and returned as a result with provider="azure_openai" and confidence=0.
    The caller (the route) always gets a result it can write to the database.
    """

    if not settings.ai_analysis_enabled:
        return _mock_analyze(image_path, notes)

    if not settings.azure_credentials_present:
        result = _mock_analyze(image_path, notes)
        result.summary = (
            "[AI_ANALYSIS_ENABLED=true but Azure credentials are not set — "
            "using mock fallback.] " + result.summary
        )
        return result

    # Credentials are present — use the real Azure OpenAI provider.
    # The provider's analyze() method catches all exceptions internally and
    # returns a safe fallback result rather than raising.
    from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer
    return AzureOpenAIImageAnalyzer().analyze(image_path, notes)
