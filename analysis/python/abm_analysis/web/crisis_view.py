"""Crisis-lens payload: the rows that sit beneath the price chart.

The price chart says what the market did; this module says when it was in
trouble and what trouble looked like. For every traded asset it supplies the
rows of the synchronised market stack that the price series alone cannot —
distance from fundamental value, realised volatility, drawdown — together with
the stress windows to shade and the normal-versus-stress comparison beside them.

Nothing here computes a research statistic. The stress flags, the rolling
volatility, the drawdown and the regime summaries all come from
``abm_analysis.statistics.stress``, the module the exported stress tables are
built from, so a window shaded on the page and the same window in a CSV cannot
disagree. This module decides only how the flags are windowed for the chart and
which summary cell becomes which payload field.

**Stress is offered under three definitions, not one.** ``annotate_stress_regimes``
flags a row when rolling volatility is in the top quintile *or* drawdown from the
running peak reaches 10%. The two triggers are different things: a volatility
burst is an *event*, while drawdown is a *state* that persists until the price
recovers to within 10% of its old high. A market that falls and never recovers is
"in drawdown" for the rest of the run, so on such a run the combined flag shades
nearly the whole chart and says nothing about where the turbulence was. Showing
the triggers separately keeps both readings available, with the volatility event
as the default.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from abm_analysis.statistics.stress import (
    DEFAULT_STRESS_DRAWDOWN_THRESHOLD,
    DEFAULT_STRESS_ROLLING_WINDOW,
    DEFAULT_STRESS_VOLATILITY_QUANTILE,
    StressFrame,
    build_asset_stress_frames,
    build_step_stress_frame,
    find_stress_intervals,
    summarise_stress_regimes,
)
from abm_analysis.web.asset_view import AssetContext
from abm_analysis.web.metrics import values_of
from abm_analysis.web.serialisation import numeric_or_none


#: The ways a row can be called "stressed", in the order the interface offers
#: them. ``volatility`` is first because it is the event reading and the default.
STRESS_DEFINITIONS = ("volatility", "drawdown", "either")

#: Cells of the normal-versus-stress table, as (summary key, label, number
#: format). A deliberate subset of what ``summarise_stress_regimes`` produces:
#: the price, liquidity and order-mix measures a reader compares across regimes.
REGIME_METRICS: tuple[tuple[str, str, str], ...] = (
    ("observation_count", "Observations", "integer"),
    ("log_return_std_dev", "Volatility (s.d.)", "scientific"),
    ("max_abs_log_return", "Largest absolute return", "scientific"),
    ("min_log_return", "Worst return", "scientific"),
    ("max_drawdown", "Max drawdown", "percent_fraction"),
    ("mean_traded_volume", "Mean traded volume", "amount"),
    ("mean_bid_ask_spread", "Mean bid–ask spread", "price"),
    ("mean_total_depth", "Mean book depth", "amount"),
    ("mean_depth_imbalance", "Depth imbalance (bid − ask)", "decimal"),
    ("mean_market_order_share", "Market-order share", "percent_fraction"),
    ("mean_executed_trades", "Trades per step", "amount"),
)

#: Below this many observations a regime's standard deviation, extremes and
#: means are not stable enough to compare, so the interface marks the column.
#: Thirty is the conventional small-sample boundary rather than a derived one.
MINIMUM_REGIME_OBSERVATIONS = 30

#: Regimes of the summary, in column order.
REGIMES = ("all", "normal", "stress")


def build_crisis_view(
    run_path: Path,
    analysed: pd.DataFrame,
    *,
    phase: str,
    price_column: str,
    context: AssetContext,
    series: dict[str, Any],
) -> dict[str, Any]:
    """Build the crisis-lens payload for one run.

    Args:
        run_path: Archived run directory.
        analysed: The phase-restricted primary-asset step series, used for runs
            read from ``step_timeseries.csv``.
        phase: Step phase analysed, matching the rest of the run view.
        price_column: Price column the stress diagnostics are computed from.
        context: Which assets are reported and from which artefact.
        series: The chart series already built for this run. The per-asset rows
            are reindexed onto ``series["step"]`` so every row of the stack
            shares one x-axis and one thinning stride; the stress *windows* are
            taken from the full-resolution frame and are never thinned.

    Returns:
        A payload with ``available`` false and a ``message`` when no stress
        diagnostics could be computed, rather than an error: a run missing a
        column should still open.
    """

    try:
        frames = _stress_frames(run_path, analysed, phase, price_column, context)
    except (KeyError, ValueError) as error:
        return _unavailable(f"Crisis diagnostics could not be computed: {error}")
    if not frames:
        return _unavailable("This run has no price series to compute crisis diagnostics from.")

    steps = pd.Index(pd.to_numeric(pd.Series(series.get("step", [])), errors="coerce"))
    tracks: dict[str, Any] = {}
    assets: dict[str, Any] = {}
    thresholds: dict[str, float | None] = {}
    for name in context.names:
        frame = frames.get(name)
        if frame is None:
            continue
        tracks[name] = _tracks(frame, steps)
        assets[name] = _asset_summary(frame)
        thresholds[name] = numeric_or_none(frame.data["stress_volatility_threshold"].iloc[0])

    if not assets:
        return _unavailable("No reported asset has a price series to compute crisis diagnostics from.")

    return {
        "available": True,
        "message": None,
        "step_axis": series.get("step_axis"),
        "definitions": list(STRESS_DEFINITIONS),
        "default_definition": STRESS_DEFINITIONS[0],
        "rule": {
            "rolling_window": DEFAULT_STRESS_ROLLING_WINDOW,
            "volatility_quantile": DEFAULT_STRESS_VOLATILITY_QUANTILE,
            "drawdown_threshold": DEFAULT_STRESS_DRAWDOWN_THRESHOLD,
            "volatility_threshold": thresholds,
        },
        "minimum_regime_observations": MINIMUM_REGIME_OBSERVATIONS,
        "metrics": [
            {"key": key, "label": label, "format": number_format}
            for key, label, number_format in REGIME_METRICS
        ],
        "warmup_end": _warmup_end(analysed, series),
        "tracks": tracks,
        "assets": assets,
    }


def _unavailable(message: str) -> dict[str, Any]:
    """Return the payload for a run whose crisis diagnostics cannot be shown."""

    return {
        "available": False,
        "message": message,
        "tracks": {},
        "assets": {},
        "metrics": [],
    }


def _stress_frames(
    run_path: Path,
    analysed: pd.DataFrame,
    phase: str,
    price_column: str,
    context: AssetContext,
) -> dict[str, StressFrame]:
    """Annotate each reported asset, from the same artefact the charts read.

    The artefact is chosen by ``context`` — the one place that decides whether a
    run is read per asset or through its primary-asset projection — so the stress
    windows are drawn over the series they were computed from.
    """

    if context.uses_asset_timeseries:
        return build_asset_stress_frames(run_path, phase=phase, price_column=price_column)
    if analysed.empty:
        return {}
    return {
        context.names[0]: build_step_stress_frame(
            analysed,
            asset=context.names[0],
            price_column=price_column,
        )
    }


def _tracks(frame: StressFrame, steps: pd.Index) -> dict[str, list[float | None]]:
    """Reindex one asset's stress rows onto the chart's (thinned) step axis."""

    keyed = frame.data.copy()
    keyed.index = pd.Index(pd.to_numeric(keyed[frame.step_column], errors="coerce"))
    keyed = keyed[~keyed.index.duplicated(keep="last")]
    aligned = keyed.reindex(steps)
    return {
        "log_mispricing": values_of(aligned["log_mispricing"]),
        "rolling_volatility": values_of(aligned["rolling_volatility"]),
        "drawdown": values_of(aligned["drawdown"]),
    }


def _stress_flags(data: pd.DataFrame, definition: str) -> pd.Series:
    """Return the boolean stress flag for one definition of stress.

    The flags are rebuilt from the annotated columns and thresholds the
    statistics module attached, never re-derived from the raw series, so the
    ``either`` flag is exactly the module's own ``stress_regime``.
    """

    threshold = data["stress_volatility_threshold"].iloc[0] if len(data) else np.nan
    if definition == "volatility":
        if not np.isfinite(threshold):
            return pd.Series(False, index=data.index)
        return (data["rolling_volatility"] >= threshold).fillna(False)
    if definition == "drawdown":
        return (data["drawdown"] >= DEFAULT_STRESS_DRAWDOWN_THRESHOLD).fillna(False)
    return data["stress_regime"].astype(bool)


def _asset_summary(frame: StressFrame) -> dict[str, Any]:
    """Build one asset's stress windows and regime table under each definition."""

    data = frame.data
    definitions: dict[str, Any] = {}
    for definition in STRESS_DEFINITIONS:
        flags = _stress_flags(data, definition)
        rows = summarise_stress_regimes(
            data.assign(stress_regime=flags),
            series_id=frame.asset,
            source_type="simulation",
        )
        by_regime = {str(row["regime"]): row for row in rows}
        definitions[definition] = {
            "share": numeric_or_none(flags.mean()) if len(flags) else None,
            "intervals": [
                [first, last]
                for first, last in find_stress_intervals(flags, data[frame.step_column])
            ],
            "regimes": {
                regime: {
                    key: numeric_or_none(by_regime.get(regime, {}).get(key))
                    for key, _label, _format in REGIME_METRICS
                }
                for regime in REGIMES
            },
        }
    return {"definitions": definitions}


def _warmup_end(analysed: pd.DataFrame, series: dict[str, Any]) -> float | None:
    """Return the x position where the simulation phase begins, if warm-up is shown.

    Only a single-asset run analysed over several phases has warm-up rows on its
    axis. Marking where they end keeps a reader from taking the volatility of
    initial price formation for a market crisis.
    """

    if series.get("step_axis") != "row_index" or "phase" not in analysed.columns:
        return None
    phases = analysed["phase"].astype(str).str.lower()
    simulation_rows = analysed[phases == "simulation"]
    if simulation_rows.empty or (phases != "simulation").sum() == 0:
        return None
    first_simulation = numeric_or_none(simulation_rows["row_index"].iloc[0])
    return None if first_simulation is None else first_simulation - 0.5
