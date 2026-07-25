"""Pure Markdown rendering for analysis outputs."""

from __future__ import annotations

import pandas as pd

from .metrics import AnalysisOutputs


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    columns = [str(column) for column in frame.columns]
    rows = [
        [str(value) for value in record]
        for record in frame.astype(object).where(pd.notna(frame), "").to_numpy()
    ]
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def render_results_markdown(outputs: AnalysisOutputs) -> str:
    delta_stats = outputs.summary["paired_delta_stats"]
    confidence = outputs.summary["confidence"]
    lines = [
        "# HeritageRisk Paired Experiment Results",
        "",
        outputs.summary["asset_independence_statement"],
        "",
        "Primary condition metrics use run_index 0. Repeatability uses all",
        "exported run indices for each asset and condition.",
        "",
        "Photos are grouped by physical asset; site concentration is reported so",
        "asset-level independence is explicit.",
        "",
        "## Site Concentration",
        "",
        f"- Site counts: `{outputs.summary['site_concentration']['site_counts']}`",
        f"- Largest site asset share: `{outputs.summary['site_concentration']['largest_site_asset_share']}`",
        "",
        "## Condition Metrics",
        "",
        _markdown_table(outputs.condition_metrics),
        "",
        "## Paired Per-Asset Delta Tests",
        "",
    ]
    for metric, values in delta_stats.items():
        lines.extend(
            [
                f"### {metric}",
                "",
                f"- n physical assets: {values['n_assets']}",
                f"- Mean delta: {values['mean_delta']}",
                f"- Wilcoxon statistic: {values['wilcoxon_statistic']}",
                f"- Wilcoxon p-value: {values['wilcoxon_p']}",
                f"- Effect size, mean delta / SD(delta): {values['effect_size_mean_over_sd']}",
                f"- Bootstrap 95% CI: [{values['bootstrap_ci_low']}, {values['bootstrap_ci_high']}]",
                "",
            ]
        )
    lines.extend(
        [
            "## Confidence Calibration",
            "",
            f"- Mean confidence, correct indicators: {confidence['mean_confidence_correct']}",
            f"- Mean confidence, incorrect indicators: {confidence['mean_confidence_incorrect']}",
            "",
            _markdown_table(outputs.confidence_reliability),
            "",
            "## Inter-Rater Agreement",
            "",
            "Cohen's kappa is reported for the double-labelled subset next to the",
            "human-vs-AI disagreement counts in the confusion matrix CSV.",
            "",
            _markdown_table(outputs.kappa),
            "",
          