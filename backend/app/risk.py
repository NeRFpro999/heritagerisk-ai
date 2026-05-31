"""
Rule-based risk scoring — each visible damage tag has a weight,
multiplied by severity (1–5), capped at 100.

Band thresholds: Low < 30 | Medium 30–60 | High > 60
"""

TAG_WEIGHTS: dict[str, int] = {
    "crack":             8,
    "erosion":           7,
    "corrosion":         7,
    "water_staining":    6,
    "vegetation_growth": 4,
    "graffiti":          3,
    "other":             2,
}

ALL_TAGS: list[str] = list(TAG_WEIGHTS.keys())

# Human-readable labels used in templates
TAG_LABELS: dict[str, str] = {
    "crack":             "Crack",
    "erosion":           "Erosion",
    "corrosion":         "Corrosion / Rust",
    "water_staining":    "Water Staining",
    "vegetation_growth": "Vegetation Growth",
    "graffiti":          "Graffiti",
    "other":             "Other",
}


def calculate_risk(tags: list[str], severity: int) -> tuple[int, str]:
    """Return (score 0–100, band string)."""
    tag_sum = sum(TAG_WEIGHTS.get(t, 0) for t in tags)
    score = min(100, tag_sum * max(1, severity))

    if score < 30:
        band = "Low"
    elif score <= 60:
        band = "Medium"
    else:
        band = "High"

    return score, band
