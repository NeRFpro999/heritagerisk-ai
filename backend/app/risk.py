"""
Rule-based risk scoring — each visible damage tag has a weight,
multiplied by severity (1–5), capped at 100.

Band thresholds: Low 0-29 | Medium 30-59 | High 60-100
"""

TAG_WEIGHTS: dict[str, int] = {
    "crack":             8,
    "erosion":           7,
    "graffiti":          3,
    "corrosion":         7,
    "water_staining":    6,
    "vegetation_growth": 4,
    "surface_loss":      7,
    "fire_damage":       7,
    "other":             2,
}

ALL_TAGS: list[str] = list(TAG_WEIGHTS.keys())

# Human-readable labels used in templates
TAG_LABELS: dict[str, str] = {
    "crack":             "Crack",
    "erosion":           "Erosion",
    "graffiti":          "Graffiti",
    "corrosion":         "Corrosion / Rust",
    "water_staining":    "Water Staining",
    "vegetation_growth": "Vegetation Growth",
    "surface_loss":      "Surface Loss",
    "fire_damage":       "Fire Damage",
    "other":             "Other",
}


def _normalise_severity(severity: int) -> int:
    return max(1, min(5, severity))


def _band_for_score(score: int) -> str:
    if score < 30:
        return "Low"
    if score < 60:
        return "Medium"
    return "High"


def calculate_risk(tags: list[str], severity: int) -> tuple[int, str]:
    """Return (score 0–100, band string)."""
    tag_sum = sum(TAG_WEIGHTS.get(t, 0) for t in tags)
    score = min(100, tag_sum * _normalise_severity(severity))
    return score, _band_for_score(score)


def calculate_risk_breakdown(tags: list[str], severity: int) -> dict:
    """Return the score, band, and visible arithmetic used for review."""
    normalised_severity = _normalise_severity(severity)
    tag_weights = [
        {
            "tag": tag,
            "label": TAG_LABELS.get(tag, tag),
            "weight": TAG_WEIGHTS.get(tag, 0),
        }
        for tag in tags
    ]
    tag_sum = sum(item["weight"] for item in tag_weights)
    raw_score = tag_sum * normalised_severity
    score = min(100, raw_score)

    return {
        "tag_weights": tag_weights,
        "tag_sum": tag_sum,
        "severity": normalised_severity,
        "raw_score": raw_score,
        "score": score,
        "capped": raw_score > 100,
        "band": _band_for_score(score),
        "thresholds": {
            "Low": "0-29",
            "Medium": "30-59",
            "High": "60-100",
        },
    }
