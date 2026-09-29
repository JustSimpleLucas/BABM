"""Assembly of the cross-seed and cross-condition payload for a cohort of runs.

A single run answers "what happened in this draw". A cohort answers the two
questions a result actually rests on: whether a finding survives the random
seed, and whether it differs between experimental conditions. Both come from one
place — ``statistics.robustness.build_seed_robustness_summary`` groups runs by
the modelling controls that define a condition and deliberately excludes the
seed, so the same aggregation reads as replication when the cohort holds one
condition and as comparison when it holds several.

Nothing here computes a research statistic. Every frame is built by
``exports.seed_robustness.build_seed_robustness_frames`` — the same call the CSV
export makes — so a number read on this panel and the same number read from
``robustness_reports/`` cannot disagree. This module decides only which frame
cell becomes which payload field, and how a condition is labelled.

Two dimensions cross here, and keeping them apart is the whole layout problem.
``build_seed_robustness_summary`` folds the traded asset into its grouping key,
so its ``condition_id`` identifies a *(condition, asset)* pair. The interface
needs the experimental condition on its own — that is the contrast a reader is
looking at — with the asset as a separate switch, so the identifiers are rebuilt
here from the condition columns alone.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from abm_analysis.exports.seed_robustness import (
    SeedRobustnessFrames,
    build_seed_robustness_frames,
)
from abm_analysis.statistics.diagnostics import SIGNIFICANCE_LEVEL
from abm_analysis.statistics.multi_asset import asset_series_id
from abm_analysis.statistics.robustness import CONDITION_COLUMNS
from abm_analysis.statistics.robustness_verdicts import (
    MINIMUM_SEEDS_FOR_VERDICTS,
    verdict_rows_for_display,
)
from abm_analysis.statistics.seed_convergence import (
    CONVERGENCE_METRICS,
    build_seed_convergence_table,
)
from abm_analysis.web.metrics import density_histogram, density_on_edges
from abm_analysis.web.serialisation import json_safe, numeric_or_none


#: The largest cohort the synchronous endpoint will accept. Every run costs a
#: GARCH(1,1) fit, so an unbounded selection — a click on a data root holding
#: hundreds of runs — would block the server for minutes with no way to cancel.
MAXIMUM_COHORT_RUNS = 64

#: Fewest runs that make a cohort. One run has no dispersion to report and is
#: better served by the single-run view.
MINIMUM_COHORT_RUNS = 2

#: The label shown for a condition column, and how its value should be read.
#: Only these are offered as a condition's distinguishing parameters; the rest
#: of ``CONDITION_COLUMNS`` is kept in the full description.
CONDITION_PARAMETER_LABELS: dict[str, tuple[str, str]] = {
    "experiment_name": ("Experiment", "text"),
    "time_steps": ("Time steps", "count"),
    "warmup_steps": ("Warm-up steps", "count"),
    "num_fundamentalists": ("Fundamentalists", "count"),
    "num_chartists": ("Chartists", "count"),
    "num_noise_traders": ("Noise traders", "count"),
    "num_buy_and_hold_agents": ("Buy-and-hold", "count"),
    "buy_hold_target_risky_weight": ("Buy-and-hold risky weight", "decimal"),
    "control_prospect_theory_enabled": ("Prospect theory", "switch"),
    "control_prospect_theory_agent_fraction": ("Prospect theory fraction", "decimal"),
    "control_prospect_heterogeneity_enabled": ("Prospect heterogeneity", "switch"),
    "social_enabled": ("Social influence", "switch"),
    "short_selling_enabled": ("Short selling", "switch"),
    "loss_aversion": ("Loss aversion λ", "decimal"),
    "prospect_scenario_count": ("Prospect scenarios", "count"),
}

#: The metric rows of the condition-comparison table, grouped the way
#: ``run_view`` groups its own tables so a reader moving between the two pages
#: finds the same statistics under the same headings.
METRIC_GROUPS: tuple[tuple[str, str, str, tuple[tuple[str, str, str, bool], ...]], ...] = (
    (
        "returns",
        "Return distribution",
        "Unconditional moments across seeds, as mean ± 95% CI of the per-seed value.",
        (
            ("mean_log_return", "Mean log return", "scientific", False),
            ("log_return_std_dev", "Volatility (s.d.)", "scientific", False),
            ("excess_kurtosis", "Excess kurtosis", "decimal", True),
            ("observation_count", "Observations", "integer", False),
        ),
    ),
    (
        "dependence",
        "Serial dependence",
        "Test p-values and GARCH persistence, averaged over seeds. A mean p-value "
        "is a description of the ensemble, not a pooled test.",
        (
            ("minimum_ljung_box_p_value", "Ljung–Box min p", "p_value", True),
            ("minimum_arch_lm_p_value", "ARCH-LM min p", "p_value", True),
            ("garch_persistence", "GARCH persistence α+β", "decimal", False),
        ),
    ),
    (
        "market",
        "Market outcomes",
        "Price-path and activity outcomes across seeds.",
        (
            ("max_drawdown", "Max drawdown", "percent_fraction", False),
            ("total_traded_volume", "Total traded volume", "integer", False),
        ),
    ),
)

#: The three stylised facts, paired with the success-rate column
#: ``build_seed_robustness_summary`` writes for each.
SUCCESS_RATE_FACTS: tuple[tuple[str, str, str], ...] = (
    (
        "Absence of linear autocorrelation",
        "Raw log returns show no exploitable linear dependence.",
        "weak_autocorrelation_success_rate",
    ),
    (
        "Fat tails",
        "Returns are leptokurtic relative to a Gaussian.",
        "fat_tail_success_rate",
    ),
    (
        "Volatility clustering",
        "Large moves follow large moves, of either sign.",
        "volatility_clustering_success_rate",
    ),
)

#: Share of seeds that must reproduce a fact for the cohort to read as
#: supporting it. Matches the strong-majority rule in
#: ``statistics.robustness_verdicts``, so the panel and the verdict cards below
#: it cannot tell opposite stories about the same runs.
SUCCESS_RATE_SUPPORTED = 0.80

#: Below this share the fact is reported as not reproduced rather than partial.
SUCCESS_RATE_PARTIAL = 0.50

#: ``verdict_rows_for_display`` was written for the deleted report generator and
#: speaks in tones. The dashboard already has a verdict vocabulary and one set of
#: colour tokens for it; mapping onto that vocabulary keeps a single meaning for
#: each colour across both pages.
VERDICT_TOKENS = {
    "Pass": "supported",
    "Borderline": "partial",
    "Fail": "not-supported",
    "Not available": "unavailable",
}

#: Group headings for the verdict table, keyed by the verdict frame's
#: ``category``. Order here is the order the groups are shown in.
VERDICT_CATEGORY_LABELS = {
    "metric_stability": "Metric stability",
    "stylised_fact_reproducibility": "Stylised-fact reproducibility",
    "distributional_stability": "Distributional stability",
    "stationarity": "Stationarity",
    "estimate_precision": "Estimate precision",
}


def build_cohort_view(
    run_paths: list[Path],
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
    frames: SeedRobustnessFrames | None = None,
) -> dict[str, Any]:
    """Build the complete cross-seed payload for a selected set of runs.

    Args:
        run_paths: The archived runs in the cohort. They need not share a parent
            directory: a comparison can hold an experiment's runs beside a
            calibration study's.
        phase: Step phase analysed, matching the single-run view's parameter.
        price_column: Price column log returns are computed from. The per-asset
            diagnostics use the simulator's own ``log_return`` column instead, so
            this selects the phase window rather than the return definition.
        frames: Pre-computed frames, used by the caching layer so a cohort and
            the CSV export can share one computation. Computed here when absent.

    Returns:
        A JSON-safe dictionary holding the conditions, the comparison tables,
        per-fact success rates, the robustness verdicts, the seed-convergence
        paths, the per-seed spread, and the per-condition return densities.
    """

    resolved = [Path(path).expanduser().resolve() for path in run_paths]
    computed = frames if frames is not None else build_seed_robustness_frames(
        resolved,
        phase=phase,
        price_column=price_column,
        per_asset=True,
    )

    assets = _asset_names(computed.seed_robustness)
    conditions = _build_conditions(computed.seed_robustness)
    condition_by_run = _condition_by_run(computed.runs_index, conditions)

    return json_safe(
        {
            "run_count": int(len(resolved)),
            "seed_count": computed.seed_count,
            "condition_count": len(conditions),
            "phase": phase,
            "price_column": price_column,
            "significance_level": SIGNIFICANCE_LEVEL,
            "assets": {"names": assets, "count": len(assets)},
            "runs": _build_runs(computed.runs_index, resolved, condition_by_run),
            "conditions": [condition.to_dict() for condition in conditions],
            "metric_groups": _build_metric_groups(computed.seed_robustness, conditions, assets),
            "success_rates": _build_success_rates(computed.seed_robustness, conditions, assets),
            "verdicts": _build_verdicts(computed.verdicts, computed.seed_robustness, conditions),
            # The frames are built with the default thresholds, so this is the
            # replication count that actually gated the verdicts above.
            "verdict_minimum_seeds": MINIMUM_SEEDS_FOR_VERDICTS,
            "convergence": _build_convergence(computed, conditions, assets),
            "spread": _build_spread(computed, conditions, assets),
            "distribution": _build_distribution(computed, conditions, assets, condition_by_run),
            "notes": _build_notes(computed, conditions, assets, phase),
        }
    )


class _Condition:
    """One experimental condition, independent of the traded asset.

    ``build_seed_robustness_summary`` emits a row per *(condition, asset)*. This
    collapses those rows back onto the condition, keeping the summary's own row
    keys so every lookup goes back to the frame rather than to a recomputation.
    """

    def __init__(self, index: int, values: tuple[tuple[str, Any], ...]) -> None:
        self.index = index
        self.values = dict(values)
        self.key = values
        self.condition_id = f"condition_{index}"
        self.label = ""
        self.parameters: list[dict[str, Any]] = []
        self.description = ""
        self.run_count = 0
        self.seed_count = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "label": self.label,
            "description": self.description,
            "run_count": self.run_count,
            "seed_count": self.seed_count,
            "parameters": self.parameters,
        }


def _condition_columns_present(summary: pd.DataFrame) -> list[str]:
    """Return the condition columns this summary actually carries, minus asset."""

    return [column for column in CONDITION_COLUMNS if column in summary.columns]


def _condition_key(row: pd.Series, columns: list[str]) -> tuple[tuple[str, Any], ...]:
    """Return a hashable identity for one row's experimental condition."""

    key: list[tuple[str, Any]] = []
    for column in columns:
        value = row.get(column)
        if isinstance(value, float) and math.isnan(value):
            value = None
        elif value is pd.NA or value is None:
            value = None
        else:
            value = str(value)
        key.append((column, value))
    return tuple(key)


def _build_conditions(summary: pd.DataFrame) -> list[_Condition]:
    """Collapse the summary's (condition, asset) rows onto experimental conditions.

    Conditions are numbered in the summary's own order, which
    ``build_seed_robustness_summary`` already sorted by description, so the
    numbering is stable across reloads of the same cohort.
    """

    if summary.empty:
        return []

    columns = _condition_columns_present(summary)
    conditions: list[_Condition] = []
    seen: dict[tuple[tuple[str, Any], ...], _Condition] = {}
    for _, row in summary.iterrows():
        key = _condition_key(row, columns)
        condition = seen.get(key)
        if condition is None:
            condition = _Condition(len(conditions) + 1, key)
            condition.description = str(row.get("condition_description", ""))
            seen[key] = condition
            conditions.append(condition)
        # Each asset repeats the same runs, so the counts are taken rather than
        # summed: three seeds on two markets are still three runs.
        condition.run_count = max(condition.run_count, int(row.get("run_count", 0) or 0))
        condition.seed_count = max(condition.seed_count, int(row.get("seed_count", 0) or 0))

    _label_conditions(conditions, columns)
    return conditions


def _label_conditions(conditions: list[_Condition], columns: list[str]) -> None:
    """Name each condition by what distinguishes it from the others.

    A condition's full description lists all fifteen controls, which buries the
    one setting a comparison is actually about. Only the columns that vary
    across the cohort are shown, so a prospect-theory contrast reads as
    "Prospect theory on" against "Prospect theory off".
    """

    varying = [
        column
        for column in columns
        if len({condition.values.get(column) for condition in conditions}) > 1
    ]

    for condition in conditions:
        parameters: list[dict[str, Any]] = []
        for column in varying:
            label, kind = CONDITION_PARAMETER_LABELS.get(column, (column, "text"))
            parameters.append(
                {
                    "label": label,
                    "value": _parameter_value(condition.values.get(column), kind),
                    "kind": kind,
                }
            )
        condition.parameters = parameters
        if not parameters:
            condition.label = "All runs"
        else:
            condition.label = " · ".join(
                f"{entry['label']} {_parameter_text(entry)}" for entry in parameters
            )


def _parameter_value(value: Any, kind: str) -> Any:
    """Coerce one condition value for the payload, by how it should be read."""

    if value is None:
        return None
    if kind == "text":
        return str(value)
    if kind == "switch":
        number = numeric_or_none(value)
        return None if number is None else bool(number)
    return numeric_or_none(value)


def _parameter_text(entry: dict[str, Any]) -> str:
    """Render one distinguishing parameter for a condition's inline label."""

    value = entry["value"]
    if value is None:
        return "—"
    if entry["kind"] == "switch":
        return "on" if value else "off"
    if entry["kind"] == "count":
        return f"{int(value):,}"
    if entry["kind"] == "decimal":
        return f"{float(value):g}"
    return str(value)


def _asset_names(summary: pd.DataFrame) -> list[str]:
    """Return the traded markets the cohort covers, in a stable order.

    Runs archived before the multi-asset extension carry a blank asset. Those
    become the single unnamed market, reported under the same label the
    single-run view uses for them.
    """

    if summary.empty or "asset" not in summary.columns:
        return ["market"]
    names = sorted({str(value).strip() for value in summary["asset"] if str(value).strip()})
    return names or ["market"]


def _summary_row(
    summary: pd.DataFrame,
    condition: _Condition,
    asset: str,
    columns: list[str],
) -> pd.Series | None:
    """Find the summary row for one (condition, asset) pair."""

    if summary.empty:
        return None
    for _, row in summary.iterrows():
        if _condition_key(row, columns) != condition.key:
            continue
        row_asset = str(row.get("asset", "") or "").strip() or "market"
        if row_asset == asset:
            return row
    return None


def _cell(row: pd.Series | None, metric: str) -> dict[str, Any] | None:
    """Build one comparison cell from the aggregate columns of a summary row.

    Returns ``None`` when the metric was not aggregated for this condition, so
    the interface can render an absent measurement rather than a zero.
    """

    if row is None:
        return None
    mean = numeric_or_none(row.get(f"{metric}_mean"))
    if mean is None:
        return None
    lower = numeric_or_none(row.get(f"{metric}_ci95_lower"))
    upper = numeric_or_none(row.get(f"{metric}_ci95_upper"))
    half_width = None
    if lower is not None and upper is not None:
        half_width = (upper - lower) / 2.0
    return {
        "mean": mean,
        "median": numeric_or_none(row.get(f"{metric}_median")),
        "std": numeric_or_none(row.get(f"{metric}_std")),
        "ci_low": lower,
        "ci_high": upper,
        "ci_half_width": half_width,
        "cov": numeric_or_none(row.get(f"{metric}_coefficient_of_variation")),
        "minimum": numeric_or_none(row.get(f"{metric}_min")),
        "maximum": numeric_or_none(row.get(f"{metric}_max")),
        "count": numeric_or_none(row.get(f"{metric}_count")),
    }


def _build_metric_groups(
    summary: pd.DataFrame,
    conditions: list[_Condition],
    assets: list[str],
) -> list[dict[str, Any]]:
    """Build the comparison tables: rows are metrics, columns are conditions."""

    columns = _condition_columns_present(summary)
    groups: list[dict[str, Any]] = []
    for key, title, caption, definitions in METRIC_GROUPS:
        metrics: list[dict[str, Any]] = []
        for metric, label, number_format, emphasis in definitions:
            values: dict[str, dict[str, Any]] = {}
            for asset in assets:
                per_condition: dict[str, Any] = {}
                for condition in conditions:
                    row = _summary_row(summary, condition, asset, columns)
                    per_condition[condition.condition_id] = _cell(row, metric)
                values[asset] = per_condition
            if any(cell for per_asset in values.values() for cell in per_asset.values()):
                metrics.append(
                    {
                        "key": metric,
                        "label": label,
                        "format": number_format,
                        "emphasis": emphasis,
                        "values": values,
                    }
                )
        if metrics:
            groups.append({"key": key, "title": title, "caption": caption, "metrics": metrics})
    return groups


def _build_success_rates(
    summary: pd.DataFrame,
    conditions: list[_Condition],
    assets: list[str],
) -> list[dict[str, Any]]:
    """Build the per-fact reproduction rates that replace single-seed verdicts."""

    columns = _condition_columns_present(summary)
    facts: list[dict[str, Any]] = []
    for fact, expectation, column in SUCCESS_RATE_FACTS:
        per_asset: dict[str, Any] = {}
        for asset in assets:
            per_condition: dict[str, Any] = {}
            for condition in conditions:
                row = _summary_row(summary, condition, asset, columns)
                rate = numeric_or_none(None if row is None else row.get(column))
                run_count = 0 if row is None else int(row.get("run_count", 0) or 0)
                per_condition[condition.condition_id] = {
                    "rate": rate,
                    "runs": run_count,
                    "successes": None if rate is None else int(round(rate * run_count)),
                    "verdict": _rate_verdict(rate),
                }
            per_asset[asset] = per_condition
        facts.append({"fact": fact, "expectation": expectation, "assets": per_asset})
    return facts


def _rate_verdict(rate: float | None) -> str:
    """Classify a reproduction rate into the dashboard's verdict vocabulary."""

    if rate is None:
        return "unavailable"
    if rate >= SUCCESS_RATE_SUPPORTED:
        return "supported"
    if rate >= SUCCESS_RATE_PARTIAL:
        return "partial"
    return "not-supported"


def _build_verdicts(
    verdicts: pd.DataFrame,
    summary: pd.DataFrame,
    conditions: list[_Condition],
) -> list[dict[str, Any]]:
    """Adapt the robustness verdict table to the dashboard's row vocabulary.

    Each row carries the rule as numbers (statistic, value, comparison and the
    two cut-offs) beside the prose, so the page can print a value against the
    thresholds that judged it and keep the hypothesis and interpretation for a
    tooltip.

    The verdict criteria are prefixed ``Condition N:`` using the summary's own
    numbering, which counts each *market* of each condition separately. That
    numbering is right for the CSV, where the summary sits alongside, but on the
    page it contradicts the condition list above it — "Condition 3" would name
    something the reader was never shown. The prefixes are rewritten to the
    condition label and market they actually describe.
    """

    if verdicts.empty:
        return []

    names = _summary_condition_names(summary, conditions)
    cards: list[dict[str, Any]] = []
    # ``verdict_rows_for_display`` keeps the frame's order and length, so the
    # display row and the frame row describe the same criterion.
    for card, (_, row) in zip(verdict_rows_for_display(verdicts), verdicts.iterrows()):
        criterion = str(card["fact"])
        scope = names.get(_criterion_prefix(criterion))
        if scope is not None:
            criterion = criterion.split(": ", 1)[1]
        category = str(row.get("category", ""))
        sample_size = numeric_or_none(row.get("sample_size"))
        cards.append(
            {
                "criterion": criterion,
                "scope": None if scope is None else scope["label"],
                "condition_id": None if scope is None else scope["condition_id"],
                "asset": None if scope is None else scope["asset"],
                "category": category,
                "category_label": VERDICT_CATEGORY_LABELS.get(category, category),
                "verdict": card["verdict"],
                "token": VERDICT_TOKENS.get(card["verdict"], "unavailable"),
                "statistic": str(row.get("statistic", "")),
                "value": numeric_or_none(row.get("metric_value")),
                "value_format": str(row.get("value_format", "ratio")),
                "comparison": str(row.get("comparison", "")),
                "pass_threshold": numeric_or_none(row.get("pass_threshold")),
                "borderline_threshold": numeric_or_none(row.get("borderline_threshold")),
                "sample_size": None if sample_size is None else int(sample_size),
                "sample_unit": str(row.get("sample_unit", "") or ""),
                "hypothesis": card["hypothesis"],
                "evidence": card["quantitative_evidence"],
                "interpretation": card["interpretation"],
            }
        )
    return cards


def _criterion_prefix(criterion: str) -> str:
    """Return the ``Condition N`` prefix of a verdict criterion, or an empty string."""

    head, separator, _ = criterion.partition(": ")
    if separator and head.startswith("Condition "):
        return head
    return ""


def _summary_condition_names(
    summary: pd.DataFrame,
    conditions: list[_Condition],
) -> dict[str, dict[str, Any]]:
    """Map each ``Condition N`` prefix onto the condition and market it names."""

    if summary.empty or len(summary) <= 1:
        return {}

    columns = _condition_columns_present(summary)
    by_key = {condition.key: condition for condition in conditions}
    assets_present = {str(row.get("asset", "") or "").strip() for _, row in summary.iterrows()}
    multi_asset = len(assets_present) > 1

    names: dict[str, dict[str, Any]] = {}
    for index, (_, row) in enumerate(summary.iterrows(), start=1):
        condition_id = str(row.get("condition_id", "") or "")
        suffix = condition_id.removeprefix("condition_")
        number = suffix if suffix != condition_id and suffix.isdigit() else str(index)
        condition = by_key.get(_condition_key(row, columns))
        asset = str(row.get("asset", "") or "").strip() or "market"
        label = "All runs" if condition is None else condition.label
        names[f"Condition {number}"] = {
            "label": f"{label} · {asset}" if multi_asset else label,
            "condition_id": None if condition is None else condition.condition_id,
            "asset": asset,
        }
    return names


def _condition_by_run(
    runs_index: pd.DataFrame,
    conditions: list[_Condition],
) -> dict[str, str]:
    """Map each run id to the condition it belongs to."""

    if runs_index.empty or "run_id" not in runs_index.columns or not conditions:
        return {}
    columns = list(conditions[0].values)
    mapping: dict[str, str] = {}
    for _, row in runs_index.iterrows():
        key = _condition_key(row, columns)
        for condition in conditions:
            if condition.key == key:
                mapping[str(row["run_id"])] = condition.condition_id
                break
    return mapping


def _build_runs(
    runs_index: pd.DataFrame,
    run_paths: list[Path],
    condition_by_run: dict[str, str],
) -> list[dict[str, Any]]:
    """List the cohort's runs with the condition each was assigned to."""

    directory_by_name = {path.name: path for path in run_paths}
    if runs_index.empty or "run_id" not in runs_index.columns:
        return [{"run_id": path.name, "seed": None, "condition_id": None} for path in run_paths]

    runs: list[dict[str, Any]] = []
    for _, row in runs_index.iterrows():
        run_id = str(row["run_id"])
        directory = str(row.get("run_directory", run_id))
        runs.append(
            {
                "run_id": run_id,
                "directory": directory,
                "seed": numeric_or_none(row.get("seed")),
                "condition_id": condition_by_run.get(run_id),
                "resolved": directory in directory_by_name or run_id in directory_by_name,
            }
        )
    return runs


def _condition_runs_index(
    runs_index: pd.DataFrame,
    condition: _Condition,
) -> pd.DataFrame:
    """Restrict the runs index to one condition's runs."""

    if runs_index.empty:
        return runs_index
    columns = list(condition.values)
    keep = [
        _condition_key(row, columns) == condition.key for _, row in runs_index.iterrows()
    ]
    return runs_index[pd.Series(keep, index=runs_index.index)]


def _asset_diagnostics(diagnostics: pd.DataFrame, asset: str) -> pd.DataFrame:
    """Restrict per-asset diagnostics to one market.

    Convergence and spread must not pool markets: two assets of one run are two
    observations of different processes, and averaging them would understate the
    dispersion the panel exists to show.
    """

    if diagnostics.empty or "asset" not in diagnostics.columns:
        return diagnostics
    normalised = diagnostics["asset"].astype(str).str.strip()
    if not normalised.ne("").any():
        return diagnostics
    return diagnostics[normalised == asset]


def _build_convergence(
    frames: SeedRobustnessFrames,
    conditions: list[_Condition],
    assets: list[str],
) -> dict[str, Any]:
    """Build the running mean ± CI path against accumulated seed count.

    Computed per condition and per asset rather than over the whole cohort. The
    exported table pools every run because an export describes one replicated
    experiment; a cohort may hold two conditions, and a convergence path that
    mixed them would show the contrast as dispersion.
    """

    series: list[dict[str, Any]] = []
    for condition in conditions:
        condition_runs = _condition_runs_index(frames.runs_index, condition)
        if condition_runs.empty:
            continue
        for asset in assets:
            table = build_seed_convergence_table(
                condition_runs,
                _asset_diagnostics(frames.diagnostics, asset),
            )
            if table.empty:
                continue
            for metric in CONVERGENCE_METRICS:
                rows = table[table["metric"] == metric]
                if rows.empty:
                    continue
                series.append(
                    {
                        "condition_id": condition.condition_id,
                        "asset": asset,
                        "metric": metric,
                        "label": _metric_label(metric),
                        "format": _metric_format(metric),
                        "seed_count": [int(value) for value in rows["seed_count"]],
                        "running_mean": [numeric_or_none(v) for v in rows["running_mean"]],
                        "ci_half_width": [
                            numeric_or_none(v) for v in rows["ci95_half_width"]
                        ],
                        "relative_ci_half_width": [
                            numeric_or_none(v) for v in rows["relative_ci95_half_width"]
                        ],
                    }
                )
    return {
        "available": bool(series),
        "metrics": [
            {"key": metric, "label": _metric_label(metric), "format": _metric_format(metric)}
            for metric in CONVERGENCE_METRICS
        ],
        "series": series,
    }


def _build_spread(
    frames: SeedRobustnessFrames,
    conditions: list[_Condition],
    assets: list[str],
) -> dict[str, Any]:
    """Build the per-seed values behind each condition's mean.

    A mean and a confidence interval hide whether one seed carried the result.
    These are the individual draws, so an outlier stays visible.
    """

    diagnostics = frames.diagnostics
    if diagnostics.empty or "run_id" not in diagnostics.columns:
        return {"available": False, "metrics": [], "series": []}

    seed_by_run = _seed_lookup(frames.runs_index)
    condition_by_run = _condition_by_run(frames.runs_index, conditions)

    metrics = [metric for _, _, _, definitions in METRIC_GROUPS for metric, *_ in definitions]
    series: list[dict[str, Any]] = []
    for metric in metrics:
        if metric not in diagnostics.columns:
            continue
        for condition in conditions:
            for asset in assets:
                points: list[dict[str, Any]] = []
                for _, row in _asset_diagnostics(diagnostics, asset).iterrows():
                    run_id = str(row.get("run_id", ""))
                    if condition_by_run.get(run_id) != condition.condition_id:
                        continue
                    value = numeric_or_none(row.get(metric))
                    if value is None:
                        continue
                    points.append({"seed": seed_by_run.get(run_id), "value": value})
                if points:
                    series.append(
                        {
                            "metric": metric,
                            "condition_id": condition.condition_id,
                            "asset": asset,
                            "points": sorted(
                                points,
                                key=lambda point: (point["seed"] is None, point["seed"]),
                            ),
                        }
                    )
    return {
        "available": bool(series),
        "metrics": [
            {"key": metric, "label": _metric_label(metric), "format": _metric_format(metric)}
            for metric in metrics
            if metric in diagnostics.columns
        ],
        "series": series,
    }


def _seed_lookup(runs_index: pd.DataFrame) -> dict[str, float | None]:
    """Map run id to seed, for labelling individual draws."""

    if runs_index.empty or "run_id" not in runs_index.columns:
        return {}
    seeds = runs_index.get("seed")
    if seeds is None:
        return {str(run_id): None for run_id in runs_index["run_id"]}
    return {
        str(run_id): numeric_or_none(seed)
        for run_id, seed in zip(runs_index["run_id"], seeds, strict=True)
    }


def _build_distribution(
    frames: SeedRobustnessFrames,
    conditions: list[_Condition],
    assets: list[str],
    condition_by_run: dict[str, str],
) -> dict[str, Any]:
    """Pool each condition's returns onto shared bins for one overlay per asset.

    Every condition of one market is binned on the same edges. Densities binned
    to their own ranges would put differently-scaled curves on one axis and make
    a narrow distribution look like a wide one.
    """

    if not frames.return_series:
        return {"available": False, "assets": {}}

    per_asset: dict[str, Any] = {}
    for asset in assets:
        pooled: dict[str, list[np.ndarray]] = {}
        for series_key, values in frames.return_series.items():
            run_id, series_asset = _split_series_key(series_key, assets)
            if series_asset != asset:
                continue
            condition_id = condition_by_run.get(run_id)
            if condition_id is None:
                continue
            finite = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
            finite = finite[np.isfinite(finite)]
            if finite.size:
                pooled.setdefault(condition_id, []).append(finite)

        if not pooled:
            continue
        combined = np.concatenate([array for arrays in pooled.values() for array in arrays])
        histogram = density_histogram(combined)
        if not histogram.get("available"):
            continue
        edges = histogram["bin_edges"]
        per_asset[asset] = {
            "bin_centre": histogram["bin_centre"],
            "bin_width": histogram["bin_width"],
            "conditions": {
                condition_id: {
                    "density": density_on_edges(np.concatenate(arrays), edges),
                    "observations": int(sum(array.size for array in arrays)),
                }
                for condition_id, arrays in pooled.items()
            },
        }

    return {"available": bool(per_asset), "assets": per_asset}


def _split_series_key(series_key: str, assets: list[str]) -> tuple[str, str]:
    """Split a return-series key back into its run id and asset.

    ``build_return_series_by_asset`` keys composite series through
    ``asset_series_id`` and falls back to a plain run id for archives with no
    per-asset artefact. Rebuilding the composite form for each known asset
    identifies the split exactly, rather than searching for the separator in a
    run id that might contain it.
    """

    for asset in assets:
        if series_key.endswith(asset_series_id("", asset).lstrip()):
            suffix = asset_series_id("", asset)
            return series_key[: -len(suffix)], asset
    return series_key, assets[0] if assets else "market"


def _metric_label(metric: str) -> str:
    """Return the display label for a metric key."""

    for _, _, _, definitions in METRIC_GROUPS:
        for key, label, _, _ in definitions:
            if key == metric:
                return label
    return metric.replace("_", " ").capitalize()


def _metric_format(metric: str) -> str:
    """Return the number format for a metric key."""

    for _, _, _, definitions in METRIC_GROUPS:
        for key, _, number_format, _ in definitions:
            if key == metric:
                return number_format
    return "decimal"


def _build_notes(
    frames: SeedRobustnessFrames,
    conditions: list[_Condition],
    assets: list[str],
    phase: str,
) -> list[str]:
    """State what the cohort covers and where its numbers stop being safe."""

    notes = [
        f"{len(conditions)} condition(s) over {frames.seed_count} distinct seed(s), "
        f"{phase} phase.",
        "Cross-seed tables are computed by the same functions that write "
        "robustness_reports/, so a number here and the same number in those CSVs agree.",
    ]
    if len(assets) > 1:
        notes.append(
            f"{len(assets)} traded markets are reported separately; seeds are never "
            "pooled across markets."
        )
    if frames.seed_count == 0:
        notes.append(
            "No run in this cohort records a seed, so nothing here can be read as "
            "replication: the runs are aggregated, but not across known draws."
        )
    elif frames.seed_count < MINIMUM_COHORT_RUNS:
        notes.append(
            "Every run in this cohort shares one seed, so the dispersion statistics "
            "describe nothing and the verdicts read as unavailable."
        )
    if len(conditions) > 1:
        notes.append(
            "Robustness verdicts are evaluated over the whole cohort. With more than "
            "one condition selected, a dispersion criterion reflects the contrast "
            "between conditions as well as the spread within them."
        )
    notes.append("Verdicts are screening diagnostics, not causal claims.")
    return notes
