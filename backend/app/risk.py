"""
Rule-based risk scoring — placeholder for future CV model output.

Score = min(100, sum(tag weights) × severity)
Band  : < 30 → Low  |  30–60 → Medium  |  > 60 → High
"""

TAG_WEIGHTS: dict[str, int] = {
    "crack": 8,
    "water": 7,
    "erosion": 6,
    "vegetation": 4,
    "staining": 3,
    "graffiti": 2,
}

ALL_TAGS = list(TAG_WEIGHTS.keys())


def calculate_risk(tags: list[str], severity: int) -> tuple[int, str]:
    """Return (score 0-100, band string)."""
    tag_sum = sum(TAG_WEIGHTS.get(t, 0) for t in tags)
    score = min(100, tag_sum * max(1, severity))

    if score < 30:
        band = "Low"
    elif score <= 60:
        band = "Medium"
    else:
        band = "High"

    return score, band
