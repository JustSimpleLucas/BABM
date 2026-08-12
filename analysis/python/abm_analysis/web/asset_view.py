"""Per-asset statistics for the dashboard, and the cross-asset panel.

``step_timeseries.csv`` records only the primary asset's projection of a run.
For a two-asset market that hides half the model: on the project's own demo run
the step series is bit-identical to ``alpha`` while ``beta`` ends at a different
price with a different return volatility. This module reads the authoritative
long-format ``asset_timeseries.csv`` instead, so every traded asset gets its own
column in the metrics table, its own stylised-fact verdict, and its own line in
each chart.

Which source a run uses is decided in exactly one place, :func:`resolve_asset_context`,
and the gate is the count of *recorded* assets rather than the mere presence of
the per-asset artefact. That distinction is load-bearing — see the docstring
there for the archive it protects.

Nothing here computes a statistic of its own: the diagnostics come from
``abm_analysis.statistics.diagnostics`` and the panels from
``abm_analysis.statistics.multi_asset``, which are the same functions the static
reports use.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import acf

from abm_analysis.statistics.diagnostics import (
    diagnose_return_series,
    run_asset_stylised_fact_diagnostics,
)
from abm_analysis.statistics.multi_asset import (
    DEFAULT_ROLLING_WINDOW,
    build_asset_return_series,
    compute_price_ratio,
    compute_rolling_correlation,
    list_assets,
    load_asset_panel,
    load_multi_asset_configuration,
)
from abm_analysis.web.metrics import (
    column_mean,
    column_sum,
    finite_values,
    first_finite,
    maximum_drawdown,
    metric,
    numeric_column,
    series_values,
    stride_for,
    values_of,
)


#: Lags shown in the autocorrelation panel. Thirty is enough to see the decay
#: of |r| and r² against the flat profile of raw returns.
AUTOCORRELATION_LAGS = 30

#: Label used for the single series of a run analysed through
#: ``step_timeseries.csv`` when nothing names the asset.
UNNAMED_ASSET = "market"

#: Source tokens reported in the payload so the interface can say which
#: artefact the numbers on screen were computed from.
ASSET_TIMESERIES_SOURCE = "asset_timeseries"
STEP_TIMESERIES_SOURCE = "step_timeseries"


@dataclass(frozen=True)
class AssetContext:
    """Which assets a run's statistics are reported for, and from which artefact."""

    names: tuple[str, ...]
    primary: str
    source: str
    return_source: str
    fundamental_correlation: float | None = None
    covariance_window: int | None = None
    configuration: tuple[dict[str, Any], ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        """Return how many assets are reported. Always at least one."""

        return len(self.names)

    @property
    def is_multi_asset(self) -> bool:
        """Return ``True`` when the run's statistics cover more than one market."""

        return self.count > 1

    @property
    def uses_asset_timeseries(self) -> bool:
        """Return ``True`` when per-asset artefacts drive the statistics."""

        return self.source == ASSET_TIMESERIES_SOURCE

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON payload describing the asset dimension."""

        return {
            "names": list(self.names),
            "primary": self.primary,
            "count": self.count,
            "is_multi_asset": self.is_multi_asset,
            "source": self.source,
            "return_source": self.return_source,
            "fundamental_correlation": self.fundamental_correlation,
            "covariance_window": self.covariance_window,
            "configuration": list(self.configuration),
            "notes": list(self.notes),
        }


def resolve_asset_context(
    run_path: Path,
    *,
    phase: str,
    price_column: str,
) -> AssetContext:
    """Decide which assets to report for one run, and from which artefact.

    The gate is ``len(list_assets(run_dir)) >= 2`` — the number of assets the
    per-asset artefact actually records — and not ``has_asset_timeseries()``.
    The difference matters for archives whose ``asset_timeseries.csv``
    disagrees with the rest of the run: the project's own ``data/latest`` holds
    eight per-asset rows beside a hundred and twenty step rows, under an asset
    name its ``config.json`` does not mention. The diagnostics module falls back
    to the single-asset path when the artefact is *absent*, not when it is
    *inconsistent*, so gating on presence would silently reduce that run to
    "insufficient observations". Gating on the asset count leaves every
    single-asset run reading exactly as it did before.

    Two limitations of the artefact are recorded in ``notes`` rather than
    papered over, because a dashboard that quietly analyses a different window
    than its own controls claim is worse than one that says so:

    * The simulator leaves ``simulation_step`` blank on initial and warm-up
      rows, and ``load_asset_panel`` indexes on that column. Asking for the
      warm-up phase therefore yields empty per-asset panels, so this falls back
      to the primary-asset view instead of rendering a blank page.
    * For the same reason the ``all`` phase silently narrows to the simulation
      phase for per-asset panels, while the single-asset series does include
      warm-up.
    """

    configuration = load_multi_asset_configuration(run_path)
    recorded = list_assets(run_path)
    notes: list[str] = []

    if configuration.primary_asset and recorded and configuration.primary_asset not in recorded:
        notes.append(
            f"config.json names '{configuration.primary_asset}' as the primary asset, but "
            f"asset_timeseries.csv records {', '.join(repr(name) for name in recorded)}. "
            "Per-asset statistics were not used for this run."
        )

    context_fields: dict[str, Any] = {
        "primary": configuration.primary_asset or (recorded[0] if recorded else UNNAMED_ASSET),
        "fundamental_correlation": configuration.fundamental_correlation,
        "covariance_window": configuration.covariance_window,
        "configuration": build_configuration_rows(configuration),
    }

    if len(recorded) < 2:
        return AssetContext(
            names=(context_fields["primary"] or UNNAMED_ASSET,),
            source=STEP_TIMESERIES_SOURCE,
            return_source=f"computed from {price_column}",
            notes=tuple(notes),
            **context_fields,
        )

    panel = load_asset_panel(run_path, price_column, phase=phase)
    if panel.empty or panel.shape[1] < 2:
        notes.append(
            "The per-asset artefact leaves simulation_step blank outside the simulation phase, "
            f"so the '{phase}' phase is shown for the primary asset only."
        )
        return AssetContext(
            names=(context_fields["primary"] or UNNAMED_ASSET,),
            source=STEP_TIMESERIES_SOURCE,
            return_source=f"computed from {price_column}",
            notes=tuple(notes),
            **context_fields,
        )

    if phase.lower() == "all":
        notes.append(
            "Per-asset panels are indexed by simulation_step, which the simulator leaves blank "
            "for initial and warm-up rows, so they cover the simulation phase only."
        )
    if price_column != "market_price":
        notes.append(
            f"Per-asset return diagnostics use the simulator's own log_return column, so the "
            f"'{price_column}' selection changes the price chart but not the return statistics."
        )

    return AssetContext(
        names=tuple(str(name) for name in panel.columns),
        source=ASSET_TIMESERIES_SOURCE,
        return_source="simulator log_return",
        notes=tuple(notes),
        **context_fields,
    )


def build_configuration_rows(configuration: Any) -> tuple[dict[str, Any], ...]:
    """Return the resolved per-asset generating parameters as JSON rows.

    The dataclasses from ``load_multi_asset_configuration`` are used directly
    rather than ``plots.multi_asset.build_asset_configuration_table``, whose
    cells are display strings (``"yes"``/``"no"``) built for a static HTML
    table. The interface needs typed values.
    """

    rows: list[dict[str, Any]] = []
    for asset in (*configuration.assets, *configuration.disabled_assets):
        rows.append(
            {
                "asset": asset.name,
                "enabled": bool(asset.enabled),
                "primary": asset.name == configuration.primary_asset,
                "process": asset.process_label,
                "drift_per_step": _finite_or_none(asset.fundamental_drift_per_step),
                "shock_std_dev": _finite_or_none(asset.fundamental_shock_std_dev),
                "units": asset.parameter_units,
                "initial_price": _finite_or_none(asset.initial_price),
                "initial_stock": _finite_or_none(asset.initial_stock),
                "tick_size": _finite_or_none(asset.price_tick_size),
                "minimum_fundamental": _finite_or_none(asset.minimum_fundamental_value),
            }
        )
    return tuple(rows)


def build_diagnostic_rows(
    run_path: Path,
    analysed: pd.DataFrame,
    *,
    phase: str,
    price_column: str,
    context: AssetContext,
) -> dict[str, dict[str, Any]]:
    """Return the stylised-fact diagnostics for each reported asset.

    Multi-asset runs go through ``run_asset_stylised_fact_diagnostics``, the
    same entry point the static reports use, which already merges each asset's
    maximum drawdown and traded volume into its row. Single-asset runs keep
    today's path exactly: ``diagnose_return_series`` over the phase-filtered
    step series.
    """

    if not context.uses_asset_timeseries:
        returns = finite_values(analysed.get("computed_log_return", pd.Series(dtype="float64")))
        return {
            context.names[0]: diagnose_return_series(
                run_path.name,
                returns.reset_index(drop=True),
                phase=phase,
                price_column=price_column,
            )
        }

    rows = run_asset_stylised_fact_diagnostics(run_path, phase=phase, price_column=price_column)
    by_asset = {str(row.get("asset", "")): row for row in rows}
    return {name: by_asset.get(name, {}) for name in context.names}


def build_return_series(
    run_path: Path,
    analysed: pd.DataFrame,
    *,
    phase: str,
    context: AssetContext,
) -> dict[str, pd.Series]:
    """Return the finite log-return series backing the charts, per asset."""

    if not context.uses_asset_timeseries:
        returns = finite_values(analysed.get("computed_log_return", pd.Series(dtype="float64")))
        return {context.names[0]: returns.reset_index(drop=True)}

    series_by_asset = build_asset_return_series(run_path, phase=phase)
    return {name: series_by_asset.get(name, pd.Series(dtype="float64")) for name in context.names}


def build_market_metrics(
    run_path: Path,
    analysed: pd.DataFrame,
    *,
    phase: str,
    price_column: str,
    context: AssetContext,
    diagnostics_by_asset: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float | None]]:
    """Return price-path and microstructure statistics for each reported asset.

    These are recomputed over the analysed window rather than read from
    ``summary_metrics.csv`` so that a drawdown or volume figure describes
    exactly the window the moments beside it describe. The simulator's own
    scalars cover the whole run including warm-up.
    """

    if not context.uses_asset_timeseries:
        return {context.names[0]: _step_series_metrics(analysed, price_column)}

    panels = {
        key: load_asset_panel(run_path, column, phase=phase)
        for key, column in (
            ("price", price_column),
            ("fundamental", "fundamental_price"),
            ("volume", "traded_volume"),
            ("spread", "bid_ask_spread"),
            ("efficiency", "allocative_efficiency"),
        )
    }

    metrics: dict[str, dict[str, float | None]] = {}
    for name in context.names:
        diagnostics = diagnostics_by_asset.get(name, {})
        final_price = _panel_last(panels["price"], name)
        final_fundamental = _panel_last(panels["fundamental"], name)
        metrics[name] = {
            "final_price": final_price,
            "final_fundamental": final_fundamental,
            "mispricing_percent": _mispricing(final_price, final_fundamental),
            # Drawdown and volume come from the diagnostics row so the dashboard
            # and the report's stylised_fact_diagnostics.csv cannot disagree.
            "max_drawdown": _finite_or_none(diagnostics.get("max_drawdown")),
            "total_traded_volume": _finite_or_none(diagnostics.get("total_traded_volume")),
            "mean_traded_volume": _panel_mean(panels["volume"], name),
            "mean_bid_ask_spread": _panel_mean(panels["spread"], name),
            "mean_allocative_efficiency": _panel_mean(panels["efficiency"], name),
        }
    return metrics


def build_series(
    run_path: Path,
    analysed: pd.DataFrame,
    *,
    phase: str,
    price_column: str,
    context: AssetContext,
) -> dict[str, Any]:
    """Build the chart series: one shared step axis, one track per asset.

    A single stride is applied across every asset so the tracks stay
    index-aligned with each other and with the step axis. ``base_price`` is each
    asset's first finite market price, which the interface divides by when the
    reader indexes the price chart — assets priced at 100 and at 40 cannot
    otherwise share one axis.
    """

    if not context.uses_asset_timeseries:
        return _step_series_payload(analysed, price_column, context)

    panels = {
        key: load_asset_panel(run_path, column, phase=phase)
        for key, column in (
            ("price", price_column),
            ("fundamental", "fundamental_price"),
            ("log_return", "log_return"),
            ("traded_volume", "traded_volume"),
            ("bid_ask_spread", "bid_ask_spread"),
        )
    }
    index = panels["price"].index
    stride = stride_for(len(index))
    sampled_index = index[::stride]

    assets: dict[str, Any] = {}
    for name in context.names:
        track = {
            key: values_of(_panel_column(panel, name).reindex(sampled_index))
            for key, panel in panels.items()
        }
        track["base_price"] = first_finite(_panel_column(panels["price"], name))
        assets[name] = track

    return {
        "stride": stride,
        "downsampled": stride > 1,
        "point_count": int(len(sampled_index)),
        "step": values_of(pd.Series(sampled_index)),
        "assets": assets,
    }


def build_return_distributions(returns_by_asset: dict[str, pd.Series]) -> dict[str, Any]:
    """Build each asset's return histogram with a fitted Gaussian reference.

    The reference is a normal density with that asset's own sample mean and
    standard deviation. Plotted together, the gap at the centre and in the tails
    is the visual form of the excess-kurtosis number in the metrics table.
    """

    assets = {name: _distribution(returns) for name, returns in returns_by_asset.items()}
    return {
        "available": any(entry["available"] for entry in assets.values()),
        "assets": assets,
    }


def build_autocorrelations(returns_by_asset: dict[str, pd.Series]) -> dict[str, Any]:
    """Build autocorrelation functions for raw, absolute, and squared returns.

    Showing the three together is what separates the two dependence facts: raw
    returns should fall inside the confidence band while |r| and r² stay outside
    it and decay slowly. The shared band is the widest across assets, so the one
    shaded region on the chart is the conservative one.
    """

    assets = {name: _autocorrelation(returns) for name, returns in returns_by_asset.items()}
    bands = [
        entry["confidence_band"] for entry in assets.values() if entry.get("confidence_band")
    ]
    return {
        "available": any(entry["available"] for entry in assets.values()),
        "confidence_band": max(bands) if bands else None,
        "assets": assets,
    }


def build_cross_asset_view(
    run_path: Path,
    *,
    phase: str,
    context: AssetContext,
) -> dict[str, Any]:
    """Build the cross-asset panel: realised return correlation and price ratio.

    The configured ``fundamental_correlation`` is carried through as a reference
    line. Realised return correlation is a different quantity — prices are set
    by order flow, so trading behaviour can amplify or dampen the underlying
    fundamental co-movement, and comparing the two is the point of the panel.
    """

    if not context.is_multi_asset:
        return {"available": False}

    asset_a, asset_b = context.names[0], context.names[1]
    window = context.covariance_window or DEFAULT_ROLLING_WINDOW
    correlation = compute_rolling_correlation(
        run_path, asset_a, asset_b, window=window, phase=phase
    )
    ratio = compute_price_ratio(run_path, asset_a, asset_b, phase=phase)
    if correlation.empty and ratio.empty:
        return {"available": False}

    index = correlation.index if not correlation.empty else ratio.index
    stride = stride_for(len(index))
    sampled_index = index[::stride]
    finite_correlation = finite_values(correlation)

    return {
        "available": True,
        "asset_a": asset_a,
        "asset_b": asset_b,
        "window": int(window),
        "configured_correlation": context.fundamental_correlation,
        "step": values_of(pd.Series(sampled_index)),
        "rolling_correlation": values_of(correlation.reindex(sampled_index)),
        "price_ratio": values_of(ratio.reindex(sampled_index)),
        "metrics": [
            metric(
                "Mean realised correlation",
                None if finite_correlation.empty else float(finite_correlation.mean()),
                format="decimal",
                emphasis=True,
            ),
            metric(
                "Configured fundamental ρ",
                context.fundamental_correlation,
                format="decimal",
                source="run configuration",
            ),
            metric(
                "Minimum correlation",
                None if finite_correlation.empty else float(finite_correlation.min()),
                format="decimal",
            ),
            metric(
                "Maximum correlation",
                None if finite_correlation.empty else float(finite_correlation.max()),
                format="decimal",
            ),
            metric("Final price ratio", _last_finite(ratio), format="decimal"),
            metric("Rolling window", window, format="integer", source="run configuration"),
        ],
    }


def _step_series_metrics(analysed: pd.DataFrame, price_column: str) -> dict[str, float | None]:
    """Return price-path metrics from the single-asset step series."""

    prices = numeric_column(analysed, price_column)
    fundamentals = numeric_column(analysed, "fundamental_price")
    final_price = float(prices.iloc[-1]) if not prices.empty else None
    final_fundamental = float(fundamentals.iloc[-1]) if not fundamentals.empty else None

    return {
        "final_price": final_price,
        "final_fundamental": final_fundamental,
        "mispricing_percent": _mispricing(final_price, final_fundamental),
        "max_drawdown": maximum_drawdown(prices),
        "total_traded_volume": column_sum(analysed, "traded_volume"),
        "mean_traded_volume": column_mean(analysed, "traded_volume"),
        "mean_bid_ask_spread": column_mean(analysed, "bid_ask_spread"),
        "mean_allocative_efficiency": column_mean(analysed, "allocative_efficiency"),
    }


def _step_series_payload(
    analysed: pd.DataFrame,
    price_column: str,
    context: AssetContext,
) -> dict[str, Any]:
    """Build the chart series from the single-asset step series."""

    stride = stride_for(len(analysed))
    sampled = analysed.iloc[::stride]

    steps = series_values(sampled, "simulation_step")
    if not steps or all(value is None for value in steps):
        steps = series_values(sampled, "row_index")

    return {
        "stride": stride,
        "downsampled": stride > 1,
        "point_count": int(len(sampled)),
        "step": steps,
        "assets": {
            context.names[0]: {
                "price": series_values(sampled, price_column),
                "fundamental": series_values(sampled, "fundamental_price"),
                "log_return": series_values(sampled, "computed_log_return"),
                "traded_volume": series_values(sampled, "traded_volume"),
                "bid_ask_spread": series_values(sampled, "bid_ask_spread"),
                "base_price": first_finite(numeric_column(sampled, price_column)),
            }
        },
    }


def _distribution(returns: pd.Series) -> dict[str, Any]:
    """Build one asset's return histogram and Gaussian reference curve."""

    values = finite_values(returns).to_numpy(dtype=float)
    if values.size < 2:
        return {"available": False}

    bin_count = int(min(80, max(20, round(math.sqrt(values.size)))))
    density, edges = np.histogram(values, bins=bin_count, density=True)
    centres = (edges[:-1] + edges[1:]) / 2.0

    mean = float(np.mean(values))
    standard_deviation = float(np.std(values, ddof=1))
    if standard_deviation > 0:
        grid = np.linspace(float(edges[0]), float(edges[-1]), 200)
        reference_density = stats.norm.pdf(grid, loc=mean, scale=standard_deviation)
    else:
        grid = np.array([])
        reference_density = np.array([])

    return {
        "available": True,
        "bin_centre": [float(value) for value in centres],
        "bin_width": float(edges[1] - edges[0]),
        "density": [float(value) for value in density],
        "normal_grid": [float(value) for value in grid],
        "normal_density": [float(value) for value in reference_density],
        "mean": mean,
        "standard_deviation": standard_deviation,
    }


def _autocorrelation(returns: pd.Series) -> dict[str, Any]:
    """Build one asset's raw, absolute, and squared return autocorrelations."""

    values = finite_values(returns).to_numpy(dtype=float)
    observation_count = values.size
    if observation_count < 20:
        return {"available": False}

    maximum_lags = min(AUTOCORRELATION_LAGS, max(1, observation_count // 4))
    raw = acf(values, nlags=maximum_lags, fft=True)
    absolute = acf(np.abs(values), nlags=maximum_lags, fft=True)
    squared = acf(np.square(values), nlags=maximum_lags, fft=True)

    return {
        "available": True,
        "lag": list(range(1, maximum_lags + 1)),
        "raw": [float(value) for value in raw[1:]],
        "absolute": [float(value) for value in absolute[1:]],
        "squared": [float(value) for value in squared[1:]],
        # Bartlett's large-sample band for white noise; points outside it are
        # the conventional screening signal for significant autocorrelation.
        "confidence_band": 1.96 / math.sqrt(observation_count),
    }


def _panel_column(panel: pd.DataFrame, asset: str) -> pd.Series:
    """Return one asset's column of a panel, or an empty series when absent."""

    if panel.empty or asset not in panel.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(panel[asset], errors="coerce")


def _panel_last(panel: pd.DataFrame, asset: str) -> float | None:
    """Return the last finite value of one asset's panel column."""

    finite = finite_values(_panel_column(panel, asset))
    return None if finite.empty else float(finite.iloc[-1])


def _panel_mean(panel: pd.DataFrame, asset: str) -> float | None:
    """Return the mean of one asset's finite panel values."""

    finite = finite_values(_panel_column(panel, asset))
    return None if finite.empty else float(finite.mean())


def _last_finite(values: pd.Series) -> float | None:
    """Return the last finite value of a series, or ``None``."""

    finite = finite_values(values)
    return None if finite.empty else float(finite.iloc[-1])


def _mispricing(final_price: float | None, final_fundamental: float | None) -> float | None:
    """Return the final price's percentage deviation from the fundamental."""

    if final_price is None or not final_fundamental:
        return None
    return (final_price / final_fundamental - 1.0) * 100.0


def _finite_or_none(value: Any) -> float | None:
    """Return ``value`` as a finite float, or ``None``."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
