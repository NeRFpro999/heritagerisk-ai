from app.risk import calculate_risk, calculate_risk_breakdown


def test_low_risk_score():
    score, band = calculate_risk(["graffiti"], severity=2)
    assert score == 6
    assert band == "Low"


def test_medium_risk_score():
    score, band = calculate_risk(["crack", "water_staining"], severity=3)
    assert score == 42
    assert band == "Medium"


def test_high_risk_score():
    score, band = calculate_risk(
        ["crack", "erosion", "corrosion", "water_staining"],
        severity=5,
    )
    assert score > 60
    assert band == "High"


def test_score_uses_sum_of_tag_weights_times_severity():
    score, band = calculate_risk(["crack", "water_staining"], severity=3)
    assert score == (8 + 6) * 3
    assert band == "Medium"


def test_score_of_60_maps_to_high():
    score, band = calculate_risk(["crack", "erosion"], severity=4)
    assert score == 60
    assert band == "High"


def test_score_is_capped_at_100():
    score, band = calculate_risk(
        ["crack", "erosion", "corrosion", "water_staining"] * 5,
        severity=5,
    )
    assert score == 100
    assert band == "High"


def test_risk_breakdown_exposes_equation_parts_and_cap():
    breakdown = calculate_risk_breakdown(
        ["crack", "erosion", "corrosion", "water_staining"] * 5,
        severity=5,
    )

    assert breakdown["tag_sum"] == (8 + 7 + 7 + 6) * 5
    assert breakdown["severity"] == 5
    assert breakdown["raw_score"] == breakdown["tag_sum"] * 5
    assert breakdown["score"] == 100
    assert breakdown["capped"] is True
    assert breakdown["band"] == "High"
    assert breakdown["thresholds"] == {
        "Low": "0-29",
        "Medium": "30-59",
        "High": "60-100",
    }


def test_unknown_tag_has_low_default_weight():
    # Unknown tags get weight 0 — score is just 0, which is Low
    score, band = calculate_risk(["unknown_damage"], severity=4)
    assert score <= 10
    assert band == "Low"
