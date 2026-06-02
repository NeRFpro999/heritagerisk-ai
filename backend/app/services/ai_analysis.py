"""
AI image analysis — single entry point for the app.

  AI_ANALYSIS_ENABLED=false (default)  → mock result, no API call
  AI_ANALYSIS_ENABLED=true, no creds  → mock result with warning prefix
  AI_ANALYSIS_ENABLED=true, creds set → Azure OpenAI Vision
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

# Must match the taxonomy in azure_openai_provider.py
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
    damage_tags: list[str]
    severity: int           # 1–5
    confidence: int         # 0–100
    summary: str
    recommended_action: str
    provider: str           # "mock" | "azure_openai"
    raw_response: str | None = field(default=None)


def _mock_analyze(image_path: str, notes: str | None) -> AIAnalysisResult:
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
        "corrosion": "corrosion",
        "rust":     "corrosion",
        "oxidis":   "corrosion",
        "oxidiz":   "corrosion",
    }
    for keyword, tag in keyword_map.items():
        if keyword in notes_lower and tag not in detected_tags:
            detected_tags.append(tag)

    image_present = bool(image_path and Path(image_path).exists())
    if not detected_tags:
        detected_tags = ["other"]

    severity = min(5, max(1, len(detected_tags) + 1))
    confidence = 35 if len(detected_tags) > 1 else 20

    prefix = "" if image_present else "No image uploaded. "
    summary = (
        f"{prefix}Mock analysis used because Azure AI is disabled or unavailable. "
        f"Keywords detected in notes: {', '.join(detected_tags)}."
    )

    return AIAnalysisResult(
        damage_tags=detected_tags,
        severity=severity,
        confidence=confidence,
        summary=summary,
        recommended_action=(
            "HeritageRisk AI is for visible risk triage only. "
            "It does not replace professional conservation, engineering, emergency, legal, or cultural heritage advice."
        ),
        provider="mock",
        raw_response=None,
    )


def analyze_observation_image(
    image_path: str,
    notes: str | None = None,
) -> AIAnalysisResult:
    """
    Analyse an observation image and return an AIAnalysisResult.
    Never raises — errors are captured inside the provider and returned
    as a result with confidence=0 so the route can always write to the DB.
    """
    if not settings.ai_analysis_enabled:
        return _mock_analyze(image_path, notes)

    if not settings.azure_credentials_present:
        result = _mock_analyze(image_path, notes)
        result.summary = (
            "Mock analysis used because Azure AI is disabled or unavailable. "
            + result.summary
        )
        return result

    from app.services.providers.azure_openai_provider import AzureOpenAIImageAnalyzer
    return AzureOpenAIImageAnalyzer().analyze(image_path, notes)
