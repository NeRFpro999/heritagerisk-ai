"""Metrics for paired HeritageRisk AI experiment exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


CONDITIONS = ("single_medium", "three_view")
PRESENT_TRUE = "true"
PRESENT_FALSE = "false"
PRESENT_UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class AnalysisOutputs:
    summary: dict[str, Any]
    condition_metrics: pd.DataFrame
    confusion_matrix: pd.DataFrame
    paired_deltas: pd.DataFrame
    confidence_reliability: pd.DataFrame
    kappa: pd.DataFrame
    repeatability: pd.DataFrame


def _bool_label(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "present"}:
        return PRESENT_TRUE
    if text in {"false", "0", "no", "n", "absent"}:
        return PRESENT_FALSE
    if text in {"uncertain", "unknown", "maybe", ""}:
        return PRESENT_UNCERTAIN
    raise ValueError(f"Unknown present label: {value}")


def load_ai_export(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load Task 7 export CSV into session and indicator dataframes."""
    export = pd.read_csv(path, keep_default_na=False)
    required = {"row_type", "external_asset_id", "condition", "indicator_type"}
    missing = required - set(export.columns)
    if missing:
        raise ValueError("AI export missing column(s): " + ", ".join(sorted(missing)))
    export = export.rename(columns={"external_asset_id": "asset_id"})
    sessions = export[export["row_type"] == "session"].copy()
    indicators = export[export["row_type"] == "indicator"].copy()
    if "confidence" in indicators:
        indicators["confidence"] = pd.to_numeric(indicators["confidence"], errors="coerce")
    else:
        indicators["confidence"] = np.nan
    return sessions, indicators


def load_human_reference(path: str | Path) -> pd.DataFrame:
    """Load reference labels: asset_id, indicator_type, present, reviewer_id."""
    reference = pd.read_csv(path, keep_default_na=False)
    required = {"asset_id", "indicator_type", "present", "reviewer_id"}
    missing = required - set(reference.columns)
    if missing:
        raise ValueError(
            "Human reference missing column(s): " + ", ".join(sorted(missing))
        )
    reference = reference.copy()
    reference["present"] = reference["present"].map(_bool_label)
    return reference


def consensus_reference(reference: pd.DataFrame) -> pd.DataFrame:
    """Collapse reviewer rows to one asset/indicator label for AI comparison."""
    rows = []
    for (asset_id, indicator_type), group in reference.groupby(
        ["asset_id", "indicator_type"],
        sort=True,
    ):
        labels = set(group["present"])
        if PRESENT_TRUE in labels:
            present = PRESENT_TRUE
        elif labels == {PRESENT_FALSE}:
            present = PRESENT_FALSE
        else:
            present = PRESENT_UNCERTAIN
        rows.append(
            {
                "asset_id": asset_id,
                "indicator_type": indicator_type,
                "present": present,
            }
        )
    return pd.DataFrame(rows, columns=["asset_id", "indicator_type", "present"])


def _ai_claim_set(ai_indicators: pd.DataFrame, condition: str) -> set[tuple[str, str]]:
    subset = ai_indicators[ai_indicators["condition"] == condition]
    return {
        (str(row.asset_id), str(row.indicator_type))
        for row in subset.itertuples()
        if str(row.indicator_type).strip()
    }


def _human_present_set(reference_consensus: pd.DataFrame) -> set[tuple[str, str]]:
    return {
        (str(row.asset_id), str(row.indicator_type))
        for row in reference_consensus.itertuples()
        if row.present == PRESENT_TRUE
    }


def _indicator_types(reference: pd.DataFrame, ai_indicators: pd.DataFrame) -> list[str]:
    indicators = set(reference["indicator_type"].dropna().astype(str))
    if not ai_indicators.empty:
        indicators |= set(ai_indicators["indicator_type"].dropna().astype(str))
    return sorted(indicator for indicator in indicators if indicator)


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def condition_metrics(
    sessions: pd.DataFrame,
    ai_indicators: pd.DataFrame,
    reference: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return micro/macro metrics and indicator confusion counts by condition."""
    reference_consensus = consensus_reference(reference)
    human_present = _human_present_set(reference_consensus)
    indicator_types = _indicator_types(reference_consensus, ai_indicators)
    metric_rows = []
    confusion_rows = []
    for condition in sorted(set(sessions["condition"]) | set(CONDITIONS)):
        ai_claims = _ai_claim_set(ai_indicators, condition)
        tp = len(ai_claims & human_present)
        fp = len(ai_claims - human_present)
        fn = len(human_present - ai_claims)
        micro = _prf(tp, fp, fn)
        per_indicator = []
        for indicator_type in indicator_types:
            ai_for_type = {pair for pair in ai_claims if pair[1] == indicator_type}
            human_for_type = {pair for pair in human_present if pair[1] == indicator_type}
            type_tp = len(ai_for_type & human_for_type)
            type_fp = len(ai_for_type - human_for_type)
            type_fn = len(human_for_type - ai_for_type)
            per_indicator.append(_prf(type_tp, type_fp, type_fn))
            confusion_rows.append(
                {
                    "condition": condition,
                    "indicator_type": indicator_type,
                    "true_positive": type_tp,
                    "false_positive": type_fp,
                    "missed_indicator": type_fn,
                }
            )
        insufficient_rate = 0.0
        if not sessions.empty and "evidence_sufficiency" in sessions:
            condition_sessions = sessions[sessions["condition"] == condition]
            if len(condition_sessions):
                insufficient_rate = (
                    condition_sessions["evidence_sufficiency"].eq("insufficient").mean()
                )
        macro_precision = float(np.mean([row["precision"] for row in per_indicator])) if per_indicator else 0.0
        macro_recall = float(np.mean([row["recall"] for row in per_indicator])) if per_indicator else 0.0
        macro_f1 = float(np.mean([row["f1"] for row in per_indicator])) if per_indicator else 0.0
        metric_rows.append(
            {
                "condition": condition,
                "n_assets": int(reference_consensus["asset_id"].nunique()),
                "true_positive": tp,
                "false_positive": fp,
                "missed_indicator": fn,
                "precision_micro": micro["precision"],
                "recall_micro": micro["recall"],
                "f1_micro": micro["f1"],
                "precision_macro": macro_precision,
                "recall_macro": macro_recall,
                "f1_macro": macro_f1,
                "unsupported_claim_rate": fp / len(ai_claims) if ai_claims else 0.0,
                "insufficient_evidence_rate": float(insufficient_rate),
            }
        )
    return pd.DataFrame(metric_rows), pd.DataFrame(confusion_rows)


def _asset_scores(
    ai_indicators: pd.DataFrame,
    reference: pd.DataFrame,
) -> pd.DataFrame:
    reference_consensus = consensus_reference(reference)
    human_present = _human_present_set(reference_consensus)
    rows = []
    for asset_id in sorted(reference_consensus["asset_id"].unique()):
        human_asset = {pair for pair in human_present if pair[0] == asset_id}
        for condition in CONDITIONS:
            ai_asset = {
                pair
                for pair in _ai_claim_set(ai_indicators, condition)
                if pair[0] == asset_id
            }
            tp = len(ai_asset & human_asset)
            fp = len(ai_asset - human_asset)
            fn = len(human_asset - ai_asset)
            scores = _prf(tp, fp, fn)
            rows.append(
                {
                    "asset_id": asset_id,
                    "condition": condition,
                    "recall": scores["recall"],
                    "f1": scores["f1"],
                }
            )
    return pd.DataFrame(rows)


def bootstrap_ci(
    values: np.ndarray | list[float],
    *,
    seed: int = 20260723,
    resamples: int = 10_000,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    sample_means = [
        float(np.mean(rng.choice(values, size=len(values), replace=True)))
        for _ in range(resamples)
    ]
    return (
        float(np.percentile(sample_means, 2.5)),
        float(np.percentile(sample_means, 97.5)),
    )


def paired_deltas(
    ai_indicators: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    seed: int = 20260723,
    resamples: int = 10_000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    scores = _asset_scores(ai_indicators, reference)
    wide = scores.pivot(index="asset_id", columns="condition", values=["recall", "f1"])
    rows = []
    for asset_id in wide.index:
        rows.append(
            {
                "asset_id": asset_id,
                "recall_single_medium": wide.loc[asset_id, ("recall", "single_medium")],
                "recall_three_view": wide.loc[asset_id, ("recall", "three_view")],
                "recall_delta": wide.loc[asset_id, ("recall", "three_view")]
                - wide.loc[asset_id, ("recall", "single_medium")],
                "f1_single_medium": wide.loc[asset_id, ("f1", "single_medium")],
                "f1_three_view": wide.loc[asset_id, ("f1", "three_view")],
                "f1_delta": wide.loc[asset_id, ("f1", "three_view")]
                - wide.loc[asset_id, ("f1", "single_medium")],
            }
        )
    delta_df = pd.DataFrame(rows)
    stats_summary: dict[str, Any] = {}
    for metric in ("recall_delta", "f1_delta"):
        values = delta_df[metric].to_numpy(dtype=float)
        if len(values) and np.any(values != 0):
            wilcoxon = stats.wilcoxon(values)
            p_value = float(wilcoxon.pvalue)
            statistic = float(wilcoxon.statistic)
        else:
            p_value = 1.0
            statistic = 0.0
        std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        effect_size = float(np.mean(values) / std) if std else 0.0
        ci_low, ci_high = bootstrap_ci(values, seed=seed, resamples=resamples)
        stats_summary[metric] = {
            "mean_delta": float(np.mean(values)) if len(values) else np.nan,
            "wilcoxon_statistic": statistic,
            "wilcoxon_p": p_value,
            "effect_size_mean_over_sd": effect_size,
            "bootstrap_ci_low": ci_low,
            "bootstrap_ci_high": ci_high,
            "n_assets": int(len(values)),
        }
    return delta_df, stats_summary


def confidence_calibration(
    ai_indicators: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    bins: list[float] | None = None,
) -> tuple[dict[str, float], pd.DataFrame]:
    reference_consensus = consensus_reference(reference)
    human_present = _human_present_set(reference_consensus)
    rows = []
    for row in ai_indicators.itertuples():
        if not str(row.indicator_type).strip():
            continue
        rows.append(
            {
                "asset_id": row.asset_id,
                "condition": row.condition,
                "indicator_type": row.indicator_type,
                "confidence": float(row.confidence) if pd.notna(row.confidence) else np.nan,
                "correct": (str(row.asset_id), str(row.indicator_type)) in human_present,
            }
        )
    claims = pd.DataFrame(rows)
    if claims.empty:
        return {"mean_confidence_correct": np.nan, "mean_confidence_incorrect": np.nan}, pd.DataFrame()
    means = {
        "mean_confidence_correct": float(
            claims.loc[claims["correct"], "confidence"].mean()
        ),
        "mean_confidence_incorrect": float(
            claims.loc[~claims["correct"], "confidence"].mean()
        ),
    }
    bins = bins or [0.0, 0.2, 0.4, 0.6, 0.8, 1.000001]
    claims["confidence_bin"] = pd.cut(
        claims["confidence"],
        bins=bins,
        include_lowest=True,
        right=False,
    ).astype(str)
    reliability = (
        claims.groupby(["condition", "confidence_bin"], observed=False)
        .agg(
            count=("correct", "size"),
            accuracy=("correct", "mean"),
            mean_confidence=("confidence", "mean"),
        )
        .reset_index()
    )
    return means, reliability


def cohen_kappa(reference: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for reviewer_pair, group in _double_labelled_pairs(reference):
        labels_a = group[f"present_{reviewer_pair[0]}"].tolist()
        labels_b = group[f"present_{reviewer_pair[1]}"].tolist()
        labels = sorted(set(labels_a) | set(labels_b))
        observed = float(np.mean([a == b for a, b in zip(labels_a, labels_b)]))
        expected = 0.0
        for label in labels:
            expected += (labels_a.count(label) / len(labels_a)) * (
                labels_b.count(label) / len(labels_b)
            )
        kappa = (observed - expected) / (1 - expected) if expected < 1 else 1.0
        rows.append(
            {
                "reviewer_a": reviewer_pair[0],
                "reviewer_b": reviewer_pair[1],
                "n_items": len(labels_a),
                "observed_agreement": observed,
                "expected_agreement": expected,
                "cohen_kappa": kappa,
            }
        )
    return pd.DataFrame(rows)


def _double_labelled_pairs(reference: pd.DataFrame):
    reviewers = sorted(reference["reviewer_id"].unique())
    for index, reviewer_a in enumerate(reviewers):
        for reviewer_b in reviewers[index + 1 :]:
            a = reference[reference["reviewer_id"] == reviewer_a][
                ["asset_id", "indicator_type", "present"]
            ].rename(columns={"present": f"present_{reviewer_a}"})
            b = reference[reference["reviewer_id"] == reviewer_b][
                ["asset_id", "indicator_type", "present"]
            ].rename(columns={"present": f"present_{reviewer_b}"})
            merged = a.merge(b, on=["asset_id", "indicator_type"], how="inner")
            if not merged.empty:
                yield (reviewer_a, reviewer_b), merged


def repeatability(ai_indicators: pd.DataFrame) -> pd.DataFrame:
    """Agreement across repeated sessions sharing asset_id and condition."""
    if "session_id" not in ai_indicators:
        return pd.DataFrame()
    rows = []
    grouped = ai_indicators.groupby(["asset_id", "condition"], sort=True)
    for (asset_id, condition), group in grouped:
        sets = [
            set(session_group["indicator_type"].astype(str))
            for _, session_group in group.groupby("session_id")
        ]
        if len(sets) < 2:
            continue
        exact_pairs = []
        jaccard_pairs = []
        for i, left in enumerate(sets):
            for right in sets[i + 1 :]:
                exact_pairs.append(left == right)
                union = left | right
                jaccard_pairs.append(len(left & right) / len(union) if union else 1.0)
        rows.append(
            {
                "asset_id": asset_id,
                "condition": condition,
                "repeat_runs": len(sets),
                "exact_agreement": float(np.mean(exact_pairs)),
                "per_indicator_agreement": float(np.mean(jaccard_pairs)),
            }
        )
    return pd.DataFrame(rows)


def site_concentration(sessions: pd.DataFrame) -> dict[str, Any]:
    if "site_label" in sessions and sessions["site_label"].any():
        counts = sessions[["asset_id", "site_label"]].drop_duplicates()["site_label"].value_counts()
        return {"site_counts": counts.to_dict(), "largest_site_asset_share": float(counts.max() / counts.sum())}
    return {"site_counts": {}, "largest_site_asset_share": np.nan}


def analyze_experiment(
    sessions: pd.DataFrame,
    ai_indicators: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    seed: int = 20260723,
    resamples: int = 10_000,
) -> AnalysisOutputs:
    metrics_df, confusion = condition_metrics(sessions, ai_indicators, reference)
    deltas, delta_stats = paired_deltas(
        ai_indicators,
        reference,
        seed=seed,
        resamples=resamples,
    )
    confidence_means, reliability = confidence_calibration(ai_indicators, reference)
    kappa_df = cohen_kappa(reference)
    repeatability_df = repeatability(ai_indicators)
    n_assets = int(reference["asset_id"].nunique())
    summary = {
        "n_physical_assets": n_assets,
        "asset_independence_statement": (
            f"n = {n_assets} physical assets; photos of one asset are never "
            "treated as independent samples."
        ),
        "site_concentration": site_concentration(sessions),
        "paired_delta_stats": delta_stats,
        "confidence": confidence_means,
    }
    return AnalysisOutputs(
        summary=summary,
        condition_metrics=metrics_df,
        confusion_matrix=confusion,
        paired_deltas=deltas,
        confidence_reliability=reliability,
        kappa=kappa_df,
        repeatability=repeatability_df,
    )
