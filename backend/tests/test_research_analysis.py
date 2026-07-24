import subprocess
import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.analysis.metrics import (
    analyze_experiment,
    cohen_kappa,
    condition_metrics,
    confidence_calibration,
    load_ai_export,
    load_human_reference,
    paired_deltas,
    repeatability,
)


EXPORT_COLUMNS = [
    "row_type",
    "external_asset_id",
    "asset_db_id",
    "session_id",
    "condition",
    "indicator_type",
    "evidence_sufficiency",
    "confidence",
    "evidence_location",
    "image_refs",
    "supporting_evidence",
    "severity_contribution",
    "insufficient_reason",
    "prompt_sha256",
    "schema_version",
    "model_deployment",
    "run_order",
    "operator",
    "run_at",
    "session_image_ids",
    "settings",
    "analysis_status",
    "provider",
]


def _session(asset_id: str, condition: str, sufficiency: str = "partial"):
    return {
        **{column: "" for column in EXPORT_COLUMNS},
        "row_type": "session",
        "external_asset_id": asset_id,
        "session_id": f"{asset_id}-{condition}",
        "condition": condition,
        "evidence_sufficiency": sufficiency,
    }


def _indicator(asset_id: str, condition: str, indicator_type: str, confidence: float):
    return {
        **{column: "" for column in EXPORT_COLUMNS},
        "row_type": "indicator",
        "external_asset_id": asset_id,
        "session_id": f"{asset_id}-{condition}",
        "condition": condition,
        "indicator_type": indicator_type,
        "confidence": confidence,
    }


def _toy_export() -> pd.DataFrame:
    rows = []
    for asset_id in ("a1", "a2", "a3", "a4"):
        rows.append(
            _session(
                asset_id,
                "single_medium",
                "insufficient" if asset_id == "a2" else "partial",
            )
        )
        rows.append(_session(asset_id, "three_view", "partial"))
    rows.extend(
        [
            # Human positives are a1/crack, a2/crack, a3/graffiti.
            # single_medium: TP=1 (a1/crack), FP=2 (a3/crack, a4/graffiti),
            # FN=2 (a2/crack, a3/graffiti), so P=R=F1=1/3.
            _indicator("a1", "single_medium", "crack", 0.9),
            _indicator("a3", "single_medium", "crack", 0.6),
            _indicator("a4", "single_medium", "graffiti", 0.2),
            # three_view: TP=3, FP=1 (a4/graffiti), FN=0, so
            # P=0.75, R=1.0, F1=6/7.
            _indicator("a1", "three_view", "crack", 0.95),
            _indicator("a2", "three_view", "crack", 0.8),
            _indicator("a3", "three_view", "graffiti", 0.7),
            _indicator("a4", "three_view", "graffiti", 0.3),
        ]
    )
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS)


def _reference() -> pd.DataFrame:
    rows = [
        # Double-labelled subset for kappa:
        # r1 labels [true, true, true, false]
        # r2 labels [true, false, true, false]
        # observed agreement = 3/4; expected = 0.5; kappa = 0.5.
        ("a1", "crack", "true", "r1"),
        ("a1", "crack", "true", "r2"),
        ("a2", "crack", "true", "r1"),
        ("a2", "crack", "false", "r2"),
        ("a3", "graffiti", "true", "r1"),
        ("a3", "graffiti", "true", "r2"),
        ("a4", "graffiti", "false", "r1"),
        ("a4", "graffiti", "false", "r2"),
        ("a3", "crack", "false", "r1"),
        ("a4", "crack", "uncertain", "r1"),
    ]
    return pd.DataFrame(
        rows,
        columns=["asset_id", "indicator_type", "present", "reviewer_id"],
    )


def test_condition_metrics_match_hand_computed_values():
    sessions = _toy_export()
    sessions = sessions[sessions["row_type"] == "session"].rename(
        columns={"external_asset_id": "asset_id"}
    )
    indicators = _toy_export()
    indicators = indicators[indicators["row_type"] == "indicator"].rename(
        columns={"external_asset_id": "asset_id"}
    )
    reference = _reference()

    metrics, confusion = condition_metrics(sessions, indicators, reference)
    single = metrics.set_index("condition").loc["single_medium"]
    three = metrics.set_index("condition").loc["three_view"]

    assert single["true_positive"] == 1
    assert single["false_positive"] == 2
    assert single["missed_indicator"] == 2
    assert single["precision_micro"] == 1 / 3
    assert single["recall_micro"] == 1 / 3
    assert single["f1_micro"] == 1 / 3
    assert single["unsupported_claim_rate"] == 2 / 3
    assert single["insufficient_evidence_rate"] == 1 / 4

    assert three["true_positive"] == 3
    assert three["false_positive"] == 1
    assert three["missed_indicator"] == 0
    assert three["precision_micro"] == 0.75
    assert three["recall_micro"] == 1.0
    assert round(three["f1_micro"], 6) == round(6 / 7, 6)

    graffiti_three = confusion[
        (confusion["condition"] == "three_view")
        & (confusion["indicator_type"] == "graffiti")
    ].iloc[0]
    assert graffiti_three["true_positive"] == 1
    assert graffiti_three["false_positive"] == 1


def test_paired_delta_kappa_confidence_and_repeatability_known_answers():
    export = _toy_export()
    sessions = export[export["row_type"] == "session"].rename(
        columns={"external_asset_id": "asset_id"}
    )
    indicators = export[export["row_type"] == "indicator"].rename(
        columns={"external_asset_id": "asset_id"}
    )
    reference = _reference()

    deltas, stats = paired_deltas(indicators, reference, seed=7, resamples=200)
    # Per-asset recall and F1 deltas are [0, 1, 1, 0], mean = 0.5.
    assert deltas["recall_delta"].tolist() == [0.0, 1.0, 1.0, 0.0]
    assert deltas["f1_delta"].tolist() == [0.0, 1.0, 1.0, 0.0]
    assert stats["recall_delta"]["mean_delta"] == 0.5
    assert stats["f1_delta"]["mean_delta"] == 0.5
    assert stats["recall_delta"]["n_assets"] == 4

    kappa = cohen_kappa(reference).iloc[0]
    assert kappa["observed_agreement"] == 0.75
    assert kappa["expected_agreement"] == 0.5
    assert kappa["cohen_kappa"] == 0.5

    means, reliability = confidence_calibration(indicators, reference)
    assert round(means["mean_confidence_correct"], 4) == round((0.9 + 0.95 + 0.8 + 0.7) / 4, 4)
    assert round(means["mean_confidence_incorrect"], 4) == round((0.6 + 0.2 + 0.3) / 3, 4)
    assert not reliability.empty

    repeated = pd.DataFrame(
        [
            {"asset_id": "a1", "condition": "three_view", "session_id": "r1", "indicator_type": "crack"},
            {"asset_id": "a1", "condition": "three_view", "session_id": "r1", "indicator_type": "graffiti"},
            {"asset_id": "a1", "condition": "three_view", "session_id": "r2", "indicator_type": "crack"},
            {"asset_id": "a1", "condition": "three_view", "session_id": "r2", "indicator_type": "graffiti"},
            {"asset_id": "a2", "condition": "three_view", "session_id": "r1", "indicator_type": "crack"},
            {"asset_id": "a2", "condition": "three_view", "session_id": "r2", "indicator_type": "graffiti"},
        ]
    )
    repeat = repeatability(repeated).set_index("asset_id")
    assert repeat.loc["a1", "exact_agreement"] == 1.0
    assert repeat.loc["a1", "per_indicator_agreement"] == 1.0
    assert repeat.loc["a2", "exact_agreement"] == 0.0
    assert repeat.loc["a2", "per_indicator_agreement"] == 0.0


def test_loaders_and_report_outputs(tmp_path):
    ai_path = tmp_path / "ai_export.csv"
    human_path = tmp_path / "human_reference.csv"
    output_dir = tmp_path / "outputs"
    _toy_export().to_csv(ai_path, index=False)
    _reference().to_csv(human_path, index=False)

    sessions, indicators = load_ai_export(ai_path)
    reference = load_human_reference(human_path)
    outputs = analyze_experiment(sessions, indicators, reference, seed=11, resamples=100)
    assert outputs.summary["n_physical_assets"] == 4
    assert "n = 4 physical assets" in outputs.summary["asset_independence_statement"]

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "analyze_experiment.py"),
            "--ai-export",
            str(ai_path),
            "--human-reference",
            str(human_path),
            "--output-dir",
            str(output_dir),
            "--seed",
            "11",
            "--resamples",
            "100",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    results = (output_dir / "results.md").read_text(encoding="utf-8")
    assert "n = 4 physical assets" in results
    assert "Condition Metrics" in results
    assert (output_dir / "confusion_matrix.csv").exists()
    assert (output_dir / "paired_deltas.csv").exists()
