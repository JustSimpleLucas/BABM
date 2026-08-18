"""Seed-robustness summaries for replicated ABM experiment conditions."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


# Modelling controls and population settings that define one experimental
# condition. ``run_label`` and ``seed`` are deliberately excluded: the seed is
# the replication device itself, and the replicate workflow stamps each run
# with ``run_label = seed_<n>``, so grouping by either would split replicated
# seeds into singleton conditions and make every dispersion statistic zero.
CONDITION_COLUMNS = [
    "experiment_name",
    "time_steps",
    "warmup_steps",
    "num_fundamentalists",
    "num_chartists",
    "num_noise_traders",
    "num_buy_and_hold_agents",
    "buy_hold_target_risky_weight",
    "control_prospect_theory_enabled",
    "control_prospect_theory_agent_fraction",
    "control_prospect_heterogeneity_enabled",
    "social_enabled",
    "short_selling_enabled",
    "loss_aversion",
    "prospect_scenario_count",
]

ROBUSTNESS_METRICS = [
    "mean_log_return",
    "log_return_std_dev",
    "excess_kurtosis",
    "max_drawdown",
    "total_traded_volume",
    "minimum_ljung_box_p_value",
    "minimum_arch_lm_p_value",
    "garch_persistence",
    "observation_count",
]


def build_seed_robustness_summary(
    runs_index: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate run diagnostics by experimental condition, excluding seed.

    Replication across random seeds is a core requirement for simulation-based
    research. This summary groups by modelling controls and population settings
    so a reader can distinguish parameter effects from one-off random draws.

    Each condition is exposed twice: ``condition_id`` is a short identifier
    (``condition_1``, ``condition_2``, ...) suitable for tables and chart
    axes, while ``condition_description`` keeps the full ``key=value`` listing
    for CSV-based reproducibility. The individual condition columns are also
    emitted, so the description is never the only source of the settings.
    """

    if runs_index.empty or "run_id" not in runs_index.columns:
        return pd.DataFrame()

    merged = merge_run_and_diagnostic_metrics(runs_index, diagnostics)
    group_columns = [column for column in CONDITION_COLUMNS if column in merged.columns]
    fallback_grouping = not group_columns
    if fallback_grouping:
        # Without condition metadata every run is treated as one condition.
        group_columns = ["_condition_group"]
        merged["_condition_group"] = "all_runs"
    if "asset" in merged.columns and merged["asset"].astype(str).str.strip().ne("").any():
        # Per-asset diagnostics carry one row per (run, asset). Each asset is a
        # separate market with its own stylised facts, so it becomes its own
        # condition; grouping without it would count one run twice and average
        # two different markets' verdicts into a single success rate.
        group_columns = [*group_columns, "asset"]

    rows: list[dict[str, object]] = []
    for group_key, group in merged.groupby(group_columns, dropna=False):
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        row: dict[str, object] = {
            "condition_description": "all_runs"
            if fallback_grouping and "asset" not in group_columns
            else _condition_label(group.iloc[0], group_columns),
            "run_count": int(len(group)),
            "seed_count": int(pd.to_numeric(group.get("seed"), errors="coerce").nunique())
            if "seed" in group.columns
            else int(len(group)),
        }
        for column, value in zip(group_columns, group_values, strict=True):
            if column == "_condition_group":
                continue
            row[column] = value

        for metric in ROBUSTNESS_METRICS:
            if metric not in group.columns:
                continue
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                continue
            row.update(_aggregate_metric(metric, values))

        row["fat_tail_success_rate"] = _success_rate(
            group,
            "fat_tail_conclusion",
            ("consistent with fat-tailed returns",),
        )
        row["volatility_clustering_success_rate"] = _success_rate(
            group,
            "volatility_clustering_conclusion",
            ("consistent with volatility clustering", "supports volatility clustering"),
        )
        row["weak_autocorrelation_success_rate"] = _success_rate(
            group,
            "autocorrelation_conclusion",
            ("absence of autocorrelation",),
        )
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    # Sorting by the full description keeps condition numbering deterministic
    # across report regenerations; the short identifier is then assigned in
    # that stable order.
    result = result.sort_values(["condition_description"]).reset_index(drop=True)
    result.insert(
        0,
        "condition_id",
        [f"condition_{index}" for index in range(1, len(result) + 1)],
    )
    return result


def merge_run_and_diagnostic_metrics(
    runs_index: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Join run-level summary metrics with per-run diagnostic columns.

    Shared by the condition-level robustness summary and the seed-count
    convergence analysis so both views aggregate exactly the same merged
    metric values.
    """

    runs = runs_index.copy()
    if diagnostics.empty or "run_id" not in diagnostics.columns:
        return runs

    per_asset = (
        "asset" in diagnostics.columns
        and diagnostics["asset"].astype(str).str.strip().ne("").any()
    )
    if per_asset:
        # Run-level summary metrics describe the primary asset only. When the
        # diagnostics are per-asset, letting the run-level column win would
        # report the primary asset's kurtosis, drawdown, or volume on every
        # asset's row, so the per-asset value takes precedence on collision.
        runs = runs.drop(
            columns=[
                column
                for column in diagnostics.columns
                if column != "run_id" and column in runs.columns
            ]
        )

    diagnostic_columns = [
        column
        for column in diagnostics.columns
        if column == "run_id" or column not in runs.columns
    ]
    merged = runs.merge(
        diagnostics[diagnostic_columns],
        on="run_id",
        how="left",
    )
    return merged


def _aggregate_metric(metric: str, values: pd.Series) -> dict[str, float | int]:
    count = int(len(values))
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if count > 1 else 0.0
    standard_error = std / math.sqrt(count) if count > 1 else 0.0
    ci_half_width = 1.96 * standard_error
    q25 = float(values.quantile(0.25))
    q75 = float(values.quantile(0.75))
    coefficient_of_variation = std / abs(mean) if abs(mean) > 1.0e-12 else np.nan
    return {
        f"{metric}_count": count,
        f"{metric}_mean": mean,
        f"{metric}_median": float(values.median()),
        f"{metric}_std": std,
        f"{metric}_min": float(values.min()),
        f"{metric}_max": float(values.max()),
        f"{metric}_q25": q25,
        f"{metric}_q75": q75,
        f"{metric}_iqr": q75 - q25,
        f"{metric}_coefficient_of_variation": coefficient_of_variation,
        f"{metric}_ci95_lower": mean - ci_half_width,
        f"{metric}_ci95_upper": mean + ci_half_width,
    }


def _success_rate(
    data: pd.DataFrame,
    column: str,
    success_phrases: tuple[str, ...],
) -> float:
    if column not in data.columns:
        return np.nan
    values = data[column].dropna().astype(str).str.lower()
    if values.empty:
        return np.nan
    successes = values.apply(lambda value: any(phrase in value for phrase in success_phrases))
    return float(successes.mean())


def _condition_label(row: pd.Series, group_columns: list[str]) -> str:
    parts: list[str] = []
    for column in group_columns:
        value = row.get(column, pd.NA)
        if pd.isna(value):
            continue
        parts.append(f"{column}={value}")
    return "; ".join(parts) if parts else "all_runs"
