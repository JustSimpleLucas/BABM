"""Assembly of the statistics payload the dashboard renders for one run.

Every number served here is recomputed from the run's own artefacts using the
same ``statistics`` functions the exported CSV tables use, so the dashboard and
the citable file cannot disagree. Where a figure is instead read straight from
the simulator's ``summary_metrics.csv``, the payload says so in the metric's
``source`` field — a reader should always be able to tell which layer produced
a number they might quote.

The statistics are reported **per traded asset**: a multi-asset run gets one
column per market in every table and one line per market in every chart, driven
by ``asset_view``. Single-asset runs take the same shape with one column.

The three groups follow how the research question reads them:

``returns``
    Shape of the unconditional log-return distribution — the moments behind the
    fat-tails stylised fact.
``dependence``
    Linear and non-linear serial dependence — absence of raw autocorrelation
    alongside persistent volatility, the two facts that must hold together.
``market``
    Price-path and microstructure outcomes that put the return statistics in
    context: mispricing against the fundamental, drawdown, traded volume,
    spread, and allocative efficiency.

Agent-level outcomes live in their own panel, built by ``agent_view``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from abm_analysis.archive.archives import build_run_archive
from abm_analysis.archive.data import read_csv_if_exists
from abm_analysis.archive.run_ids import parse_run_id
from abm_analysis.archive.timeseries import load_step_timeseries
from abm_analysis.statistics.diagnostics import LJUNG_BOX_LAGS, SIGNIFICANCE_LEVEL
from abm_analysis.web.agent_view import build_agent_view
from abm_analysis.web.asset_view import (
    AssetContext,
    build_autocorrelations,
    build_cross_asset_view,
    build_diagnostic_rows,
    build_market_metrics,
    build_return_distributions,
    build_return_series,
    build_series,
    resolve_asset_context,
)
from abm_analysis.web.metrics import (
    SIMULATOR_SUMMARY_SOURCE,
    asset_metric,
    evidence,
    read_agent_snapshot,
)
from abm_analysis.web.protagonist_view import build_protagonist_view
from abm_analysis.web.serialisation import json_safe, numeric_or_none


#: Conclusions from ``statistics.diagnostics`` that mean the stylised fact was
#: reproduced. Matching on the exact strings keeps the interface's verdict
#: colouring tied to the diagnostic module rather than to keyword guessing.
SUPPORTING_CONCLUSIONS = frozenset(
    {
        "Consistent with absence of autocorrelation",
        "Consistent with fat-tailed returns",
        "Consistent with volatility clustering",
    }
)


def build_run_view(
    run_dir: Path | str,
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> dict[str, Any]:
    """Build the complete statistics payload for one archived run.

    Args:
        run_dir: Directory of the archived run.
        phase: Step phase analysed. ``"all"`` includes initial and warm-up rows;
            the default excludes them so warm-up transients do not contaminate
            the stylised-fact diagnostics.
        price_column: Price column log returns are computed from.

    Returns:
        A JSON-safe dictionary with the run's identity, parameters, the asset
        dimension, per-asset metrics and verdicts, the series backing each
        chart, the cross-asset panel, and the agent panel.
    """

    run_path = Path(run_dir).expanduser().resolve()
    archive = build_run_archive(run_path)

    time_series = load_step_timeseries(run_path, price_column=price_column)
    analysed = _select_phase(time_series, phase)
    summary_metrics = _read_summary_metrics(archive.summary_metrics_csv)

    context = resolve_asset_context(run_path, phase=phase, price_column=price_column)
    diagnostics_by_asset = build_diagnostic_rows(
        run_path,
        analysed,
        phase=phase,
        price_column=price_column,
        context=context,
    )
    returns_by_asset = build_return_series(run_path, analysed, phase=phase, context=context)
    market_metrics = build_market_metrics(
        run_path,
        analysed,
        phase=phase,
        price_column=price_column,
        context=context,
        diagnostics_by_asset=diagnostics_by_asset,
    )
    primary = diagnostics_by_asset.get(context.names[0], {})

    # Read once and share: the agent panel and the protagonist panel must be
    # describing the same population, and the file is not small.
    agents = read_agent_snapshot(archive)

    return json_safe(
        {
            "run_id": archive.run_id,
            "path": str(run_path),
            "phase": phase,
            "price_column": price_column,
            "significance_level": SIGNIFICANCE_LEVEL,
            "observation_count": primary.get("observation_count"),
            "diagnostic_status": primary.get("diagnostic_status"),
            "diagnostic_message": primary.get("diagnostic_message"),
            "identity": _build_identity(archive.run_id, summary_metrics, archive.metadata_json),
            "parameters": _build_parameters(archive.run_id, summary_metrics),
            "assets": context.to_dict(),
            "metric_groups": _build_metric_groups(
                diagnostics_by_asset, summary_metrics, market_metrics, context
            ),
            "stylised_facts": _build_stylised_facts(diagnostics_by_asset, context),
            "series": build_series(
                run_path, analysed, phase=phase, price_column=price_column, context=context
            ),
            "return_distribution": build_return_distributions(returns_by_asset),
            "autocorrelation": build_autocorrelations(returns_by_asset),
            "cross_asset": build_cross_asset_view(run_path, phase=phase, context=context),
            "agents": build_agent_view(archive, agents, summary_metrics),
            "protagonist": build_protagonist_view(archive, agents, summary_metrics),
        }
    )


def _select_phase(time_series: pd.DataFrame, phase: str) -> pd.DataFrame:
    """Restrict the frame to one step phase, mirroring the analysis commands.

    This is a hard filter that may return nothing, unlike the soft filter in
    ``statistics.multi_asset.load_asset_panel``, which falls back to every row
    when a phase matches none. The asymmetry is why ``resolve_asset_context``
    checks the per-asset panel separately rather than assuming the two agree.
    """

    if phase.lower() == "all" or "phase" not in time_series.columns:
        return time_series.reset_index(drop=True)
    return time_series[time_series["phase"] == phase].reset_index(drop=True)


def _read_summary_metrics(summary_metrics_csv: Path | None) -> dict[str, Any]:
    """Read the simulator's headline scalars, or an empty mapping when absent.

    Archives predating a metric — or written with archiving partially disabled —
    simply lack the column; the dashboard then shows the metric as unavailable
    instead of failing to open the run.
    """

    summary = read_csv_if_exists(summary_metrics_csv)
    if summary.empty:
        return {}
    return summary.iloc[0].to_dict()


def _read_metadata(metadata_json: Path | None) -> dict[str, Any]:
    """Read a run's build metadata, tolerating a missing or unreadable file."""

    if metadata_json is None or not metadata_json.is_file():
        return {}
    try:
        with metadata_json.open(encoding="utf-8") as handle:
            content = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return content if isinstance(content, dict) else {}


def _build_identity(
    run_id: str,
    summary_metrics: dict[str, Any],
    metadata_json: Path | None,
) -> dict[str, Any]:
    """Describe where the run came from, for reproducibility at a glance."""

    metadata = _read_metadata(metadata_json)
    parsed = parse_run_id(run_id)
    return {
        "run_id": run_id,
        "experiment_name": summary_metrics.get("experiment_name"),
        "run_label": summary_metrics.get("run_label"),
        "status": summary_metrics.get("status"),
        "created_at": summary_metrics.get("created_at_local")
        or parsed.get("run_id_created_at_local"),
        "config_hash": summary_metrics.get("config_hash"),
        "model_version": metadata.get("model_version"),
        "git_commit": metadata.get("git_commit"),
        "git_dirty": metadata.get("git_dirty"),
        "compiler": metadata.get("compiler"),
    }


def _build_parameters(run_id: str, summary_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """List the experimental settings that distinguish this run from another.

    Values come from ``summary_metrics.csv`` where available, because that is
    the authoritative parameter record; the run-id is only the sortable label
    and its schema is frozen, so it can lag behind the model.
    """

    parsed = parse_run_id(run_id)
    definitions = [
        ("Seed", "seed", "run_id_seed", None),
        ("Time steps", "time_steps", "run_id_time_steps", None),
        ("Warm-up steps", "warmup_steps", None, None),
        ("Fundamentalists", "num_fundamentalists", "run_id_num_fundamentalists", None),
        ("Chartists", "num_chartists", "run_id_num_chartists", None),
        ("Noise traders", "num_noise_traders", "run_id_num_noise_traders", None),
        ("Buy-and-hold", "num_buy_and_hold_agents", "run_id_num_buy_and_hold_agents", None),
        ("Prospect theory", "prospect_theory_enabled", "run_id_prospect_theory_enabled", "switch"),
        (
            "Prospect heterogeneity",
            "prospect_heterogeneity_enabled",
            "run_id_prospect_heterogeneity_enabled",
            "switch",
        ),
        ("Social influence", "social_enabled", "run_id_social_enabled", "switch"),
        ("Short selling", "short_selling_enabled", "run_id_short_selling_enabled", "switch"),
        ("Transaction cost rate", "transaction_cost_rate", None, "rate"),
    ]

    parameters: list[dict[str, Any]] = []
    for label, summary_key, run_id_key, kind in definitions:
        value = summary_metrics.get(summary_key)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            value = parsed.get(run_id_key) if run_id_key else None
        parameters.append(
            {
                "label": label,
                "value": numeric_or_none(value) if kind != "switch" else _switch_state(value),
                "kind": kind or "count",
            }
        )
    return parameters


def _switch_state(value: Any) -> bool | None:
    """Interpret a ``1``/``0`` switch column as a boolean, or ``None`` if absent."""

    number = numeric_or_none(value)
    return None if number is None else bool(number)


def _build_metric_groups(
    diagnostics_by_asset: dict[str, dict[str, Any]],
    summary_metrics: dict[str, Any],
    market_metrics: dict[str, dict[str, float | None]],
    context: AssetContext,
) -> list[dict[str, Any]]:
    """Assemble the three metric tables shown above the charts.

    Each metric is one table row carrying a value per asset, so a two-asset run
    reads as two columns of the same statistics rather than as two pages.
    """

    def diagnostic(key: str) -> dict[str, Any]:
        return {name: row.get(key) for name, row in diagnostics_by_asset.items()}

    def market(key: str) -> dict[str, Any]:
        return {name: values.get(key) for name, values in market_metrics.items()}

    ljung_box_label = "/".join(str(lag) for lag in LJUNG_BOX_LAGS)
    return [
        {
            "key": "returns",
            "title": "Return distribution",
            "caption": "Unconditional moments of the log-return series over the analysed phase.",
            "metrics": [
                asset_metric("Observations", diagnostic("observation_count"), format="integer"),
                asset_metric("Mean log return", diagnostic("mean_log_return"), format="scientific"),
                asset_metric(
                    "Volatility (s.d.)", diagnostic("log_return_std_dev"), format="scientific"
                ),
                asset_metric("Skewness", diagnostic("skewness"), format="decimal"),
                asset_metric(
                    "Excess kurtosis",
                    diagnostic("excess_kurtosis"),
                    format="decimal",
                    emphasis=True,
                ),
                asset_metric("Jarque–Bera p", diagnostic("jarque_bera_p_value"), format="p_value"),
            ],
        },
        {
            "key": "dependence",
            "title": "Serial dependence",
            "caption": (
                "Linear dependence in raw returns against non-linear dependence in their magnitude."
            ),
            "metrics": [
                asset_metric(
                    "Lag-1 autocorrelation",
                    {context.primary: summary_metrics.get("lag1_return_autocorrelation")},
                    format="decimal",
                    source=SIMULATOR_SUMMARY_SOURCE,
                    scope="primary",
                ),
                asset_metric(
                    f"Ljung–Box min p (lags {ljung_box_label})",
                    diagnostic("minimum_ljung_box_p_value"),
                    format="p_value",
                    emphasis=True,
                ),
                asset_metric(
                    "ARCH-LM min p",
                    diagnostic("minimum_arch_lm_p_value"),
                    format="p_value",
                    emphasis=True,
                ),
                asset_metric("GARCH(1,1) α", diagnostic("garch_alpha1"), format="decimal"),
                asset_metric("GARCH(1,1) β", diagnostic("garch_beta1"), format="decimal"),
                asset_metric(
                    "GARCH persistence α+β", diagnostic("garch_persistence"), format="decimal"
                ),
            ],
        },
        {
            "key": "market",
            "title": "Market outcomes",
            "caption": "Price path, trading activity, and order-book conditions per market.",
            "metrics": [
                asset_metric("Final market price", market("final_price"), format="price"),
                asset_metric("Final fundamental", market("final_fundamental"), format="price"),
                asset_metric(
                    "Mispricing",
                    market("mispricing_percent"),
                    format="percent_points",
                    emphasis=True,
                ),
                asset_metric(
                    "Max drawdown", market("max_drawdown"), format="percent_fraction"
                ),
                asset_metric(
                    "Total traded volume", market("total_traded_volume"), format="integer"
                ),
                asset_metric(
                    "Mean bid–ask spread", market("mean_bid_ask_spread"), format="price"
                ),
                asset_metric(
                    "Mean allocative efficiency",
                    market("mean_allocative_efficiency"),
                    format="decimal",
                ),
            ],
        },
    ]


def _build_stylised_facts(
    diagnostics_by_asset: dict[str, dict[str, Any]],
    context: AssetContext,
) -> list[dict[str, Any]]:
    """Turn the diagnostic conclusions into the verdict cards, one row per asset.

    Each row pairs the stylised fact with the test evidence behind it, so the
    verdict is never presented without the statistic that produced it. A
    two-asset run can reproduce a fact in one market and not the other, which is
    a result in itself and must not be collapsed into a single verdict.
    """

    definitions = [
        (
            "Absence of linear autocorrelation",
            "Raw log returns show no exploitable linear dependence.",
            "autocorrelation_conclusion",
            [
                ("Ljung–Box min p-value", "minimum_ljung_box_p_value", "p_value"),
                ("Rejects no autocorrelation", "ljung_box_rejects_no_autocorrelation", "flag"),
            ],
        ),
        (
            "Fat tails",
            "Returns are leptokurtic relative to a Gaussian.",
            "fat_tail_conclusion",
            [
                ("Excess kurtosis", "excess_kurtosis", "decimal"),
                ("Jarque–Bera p-value", "jarque_bera_p_value", "p_value"),
            ],
        ),
        (
            "Volatility clustering",
            "Large moves follow large moves, of either sign.",
            "volatility_clustering_conclusion",
            [
                ("ARCH-LM min p-value", "minimum_arch_lm_p_value", "p_value"),
                ("GARCH persistence α+β", "garch_persistence", "decimal"),
            ],
        ),
    ]

    facts: list[dict[str, Any]] = []
    for fact, expectation, conclusion_key, evidence_keys in definitions:
        per_asset: dict[str, Any] = {}
        for name in context.names:
            row = diagnostics_by_asset.get(name, {})
            conclusion = row.get(conclusion_key)
            per_asset[name] = {
                "conclusion": conclusion,
                "verdict": _classify_conclusion(conclusion),
                "evidence": [
                    evidence(label, row.get(key), number_format)
                    for label, key, number_format in evidence_keys
                ],
            }
        facts.append({"fact": fact, "expectation": expectation, "assets": per_asset})
    return facts


def _classify_conclusion(conclusion: Any) -> str:
    """Reduce a diagnostic conclusion to a token the interface can colour.

    ``supported`` means the stylised fact was reproduced, ``partial`` that only
    part of the evidence points that way, ``not-supported`` that it did not, and
    ``unavailable`` that the test could not run on this series.
    """

    if not isinstance(conclusion, str) or not conclusion:
        return "unavailable"
    if conclusion in SUPPORTING_CONCLUSIONS:
        return "supported"
    lowered = conclusion.lower()
    if "unavailable" in lowered:
        return "unavailable"
    if "but" in lowered or "supports" in lowered:
        return "partial"
    return "not-supported"
