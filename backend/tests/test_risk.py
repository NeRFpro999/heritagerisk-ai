from app.risk import calculate_risk


def test_low_risk_score():
    score, band = calculate_risk(["graffiti"], severity=2)
    assert score == 6
    assert band == "Low"


def test_medium_risk_score():
    score, band = calculate_risk(["crack", "water_staining"], severity=3)
    assert score == 42
    assert band == "Medium"


def test_high_risk_score():
    score, band = calculate_risk(["crack", "erosion", "corrosion", "water_staining"], severity=5)
    assert score > 60
    assert band == "High"


def test_score_is_capped_at_100():
    score, band = calculate_risk(["crack", "erosion", "corrosion", "water_staining"] * 5, severity=5)
    assert score == 100
    assert band == "High"


def test_unknown_tag_has_low_default_weight():
    # Unknown tags get weight 0 — score is just 0, which is Low
    score, band = calculate_risk(["unknown_damage"], severity=4)
    assert score <= 10
    assert band == "Low"
