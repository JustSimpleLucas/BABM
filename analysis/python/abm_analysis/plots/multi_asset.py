"""Per-asset and cross-asset figures for multi-asset ABM runs.

Two families of builder live here. The cross-asset figures (correlation, price
ratio, portfolio composition) only carry information once a second risky asset
exists. The per-asset figures replace their run-level counterparts in a
multi-asset report so that every market gets the same price, liquidity,
order-flow, and efficiency panels rather than only the nominated primary asset.

Each builder returns an explanatory placeholder when its inputs are absent, so
the report never fails, and the report layer omits sections rather than showing
empty panels.

Panels are laid out as stacked subplots rather than as a single panel with an
interactive asset toggle. The report exports publication figures to static
PNG/PDF/SVG via Kaleido, and a Plotly ``updatemenus`` toggle would export only
whichever asset happened to be selected, silently dropping the others from the
thesis-ready output.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from abm_analysis.multi_asset import (
    DEFAULT_ROLLING_WINDOW,
    compute_portfolio_composition,
    compute_price_ratio,
    compute_realised_volatility,
    compute_rolling_correlation,
    list_assets,
    load_asset_panel,
    load_multi_asset_configuration,
)

from .common import COLOUR_SEQUENCE, PLOT_TEMPLATE, REPORT_COLOURS, _empty_figure

# Cash is drawn in a deliberately neutral grey so the risky assets carry the
# categorical colours and the eye reads composition shifts between them.
_CASH_COLOUR = "#98a2b3"

_SINGLE_ASSET_MESSAGE = (
    "Only one risky asset traded in this run. Enable a second asset to populate "
    "this panel."
)


def _asset_colour(index: int) -> str:
    return COLOUR_SEQUENCE[index % len(COLOUR_SEQUENCE)]


def make_asset_price_fundamental_figure(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot realised market price against latent fundamental value, per asset.

    One subplot per asset, each with its own y-axis, because assets trade at
    different price levels and a shared axis would flatten the cheaper one.
    The market/fundamental gap is the mispricing fundamentalists trade against,
    so the two series are always drawn together.
    """

    assets = list_assets(run_dir)
    if not assets:
        return _empty_figure("No per-asset time series is available for this run.")

    prices = load_asset_panel(run_dir, "market_price", phase=phase)
    fundamentals = load_asset_panel(run_dir, "fundamental_price", phase=phase)
    if prices.empty:
        return _empty_figure("No per-asset price series is available for this run.")

    figure = make_subplots(
        rows=len(assets),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=[f"{name}: market price vs fundamental value" for name in assets],
    )

    for position, name in enumerate(assets):
        row = position + 1
        colour = _asset_colour(position)
        if name in prices.columns:
            figure.add_trace(
                go.Scatter(
                    x=prices.index,
                    y=prices[name],
                    name=f"{name} market",
                    legendgroup=name,
                    line=dict(color=colour, width=1.6),
                ),
                row=row,
                col=1,
            )
        if name in fundamentals.columns:
            figure.add_trace(
                go.Scatter(
                    x=fundamentals.index,
                    y=fundamentals[name],
                    name=f"{name} fundamental",
                    legendgroup=name,
                    line=dict(color=colour, width=1.4, dash="dot"),
                ),
                row=row,
                col=1,
            )
        figure.update_yaxes(title_text="Price", row=row, col=1)

    figure.update_xaxes(title_text="Simulation step", row=len(assets), col=1)
    figure.update_layout(
        title="Price and Fundamental Value by Asset",
        template=PLOT_TEMPLATE,
        height=max(420, 280 * len(assets)),
        hovermode="x unified",
    )
    return figure


def make_asset_volume_volatility_figure(
    run_dir: Path | str,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot traded volume and rolling realised volatility for each asset.

    Volume and volatility are shown together because their co-movement is the
    volume-volatility relation, one of the stylised facts the model targets.
    """

    assets = list_assets(run_dir)
    if not assets:
        return _empty_figure("No per-asset time series is available for this run.")

    volume = load_asset_panel(run_dir, "traded_volume", phase=phase)
    volatility = compute_realised_volatility(run_dir, window=window, phase=phase)
    if volume.empty and volatility.empty:
        return _empty_figure("No per-asset volume or volatility series is available.")

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.11,
        subplot_titles=(
            "Traded volume by asset",
            f"Realised volatility by asset ({window}-step rolling s.d. of log returns)",
        ),
    )

    for position, name in enumerate(assets):
        colour = _asset_colour(position)
        if name in volume.columns:
            figure.add_trace(
                go.Scatter(
                    x=volume.index,
                    y=volume[name],
                    name=name,
                    legendgroup=name,
                    line=dict(color=colour, width=1.3),
                ),
                row=1,
                col=1,
            )
        if name in volatility.columns:
            figure.add_trace(
                go.Scatter(
                    x=volatility.index,
                    y=volatility[name],
                    name=name,
                    legendgroup=name,
                    showlegend=False,
                    line=dict(color=colour, width=1.3),
                ),
                row=2,
                col=1,
            )

    figure.update_yaxes(title_text="Volume", row=1, col=1)
    figure.update_yaxes(title_text="Realised volatility", row=2, col=1)
    figure.update_xaxes(title_text="Simulation step", row=2, col=1)
    figure.update_layout(
        title="Per-Asset Volume and Realised Volatility",
        template=PLOT_TEMPLATE,
        height=620,
        hovermode="x unified",
    )
    return figure


def make_cross_asset_figure(
    run_dir: Path | str,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot rolling cross-asset return correlation and the relative price ratio.

    The correlation panel also draws the configured fundamental correlation
    ``rho_AB`` as a reference line. The gap between the two is economically
    meaningful: fundamentals co-move by construction, whereas realised prices
    co-move only to the extent that order flow transmits that co-movement, so a
    persistent gap indicates trading behaviour amplifying or dampening the
    underlying relationship.
    """

    assets = list_assets(run_dir)
    if len(assets) < 2:
        return _empty_figure(_SINGLE_ASSET_MESSAGE)

    correlation = compute_rolling_correlation(run_dir, window=window, phase=phase)
    ratio = compute_price_ratio(run_dir, phase=phase)
    if correlation.empty and ratio.empty:
        return _empty_figure("No cross-asset series could be derived for this run.")

    first, second = assets[0], assets[1]
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.11,
        subplot_titles=(
            f"Rolling return correlation, {first} vs {second} ({window}-step window)",
            f"Price ratio {first} / {second}",
        ),
    )

    if not correlation.empty:
        figure.add_trace(
            go.Scatter(
                x=correlation.index,
                y=correlation,
                name="Realised return correlation",
                line=dict(color=REPORT_COLOURS["blue"], width=1.5),
            ),
            row=1,
            col=1,
        )

        configuration = load_multi_asset_configuration(run_dir)
        if configuration.fundamental_correlation is not None:
            figure.add_hline(
                y=configuration.fundamental_correlation,
                line=dict(color=REPORT_COLOURS["amber"], width=1.4, dash="dash"),
                annotation_text=(
                    f"configured fundamental ρ = "
                    f"{configuration.fundamental_correlation:.2f}"
                ),
                annotation_position="top left",
                row=1,
                col=1,
            )
        figure.add_hline(
            y=0.0,
            line=dict(color=REPORT_COLOURS["line"], width=1),
            row=1,
            col=1,
        )

    if not ratio.empty:
        figure.add_trace(
            go.Scatter(
                x=ratio.index,
                y=ratio,
                name=f"{first} / {second}",
                line=dict(color=REPORT_COLOURS["teal"], width=1.5),
            ),
            row=2,
            col=1,
        )

    figure.update_yaxes(title_text="Correlation", range=[-1.05, 1.05], row=1, col=1)
    figure.update_yaxes(title_text="Price ratio", row=2, col=1)
    figure.update_xaxes(title_text="Simulation step", row=2, col=1)
    figure.update_layout(
        title="Cross-Asset Dependence and Relative Valuation",
        template=PLOT_TEMPLATE,
        height=620,
        hovermode="x unified",
    )
    return figure


def make_portfolio_composition_figure(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot mean agent portfolio weights in each asset and cash as stacked areas.

    Weights are cross-sectional means over agents with strictly positive
    wealth, so the bands sum to one by construction. Shifts between bands show
    the population rotating between risky assets and into or out of cash, which
    is the portfolio-choice channel a single-asset model cannot express.
    """

    composition = compute_portfolio_composition(run_dir, phase=phase)
    if composition.empty:
        return _empty_figure(
            "No portfolio-composition series is available. Runs archived before the "
            "two-asset extension do not record per-asset agent weights."
        )

    asset_columns = [column for column in composition.columns if column != "cash"]
    figure = go.Figure()
    for position, name in enumerate(asset_columns):
        figure.add_trace(
            go.Scatter(
                x=composition.index,
                y=composition[name],
                name=name,
                mode="lines",
                line=dict(width=0.8, color=_asset_colour(position)),
                stackgroup="composition",
                fillcolor=_asset_colour(position),
                hovertemplate=f"{name}: %{{y:.3f}}<extra></extra>",
            )
        )
    if "cash" in composition.columns:
        figure.add_trace(
            go.Scatter(
                x=composition.index,
                y=composition["cash"],
                name="cash",
                mode="lines",
                line=dict(width=0.8, color=_CASH_COLOUR),
                stackgroup="composition",
                fillcolor=_CASH_COLOUR,
                hovertemplate="cash: %{y:.3f}<extra></extra>",
            )
        )

    figure.update_layout(
        title="Mean Agent Portfolio Composition",
        template=PLOT_TEMPLATE,
        height=460,
        hovermode="x unified",
        xaxis_title="Simulation step",
        yaxis_title="Mean portfolio weight",
    )
    return figure


def make_asset_return_path_figure(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot realised market and fundamental log returns for each asset.

    Both series are drawn on one axis per asset because the question the panel
    answers is whether traded returns track the fundamental innovations that
    generate them. Fundamental returns come from differencing the fundamental
    path: the simulator records the level, and the level is what the two
    processes are defined on.
    """

    assets = list_assets(run_dir)
    if not assets:
        return _empty_figure("No per-asset time series is available for this run.")

    market_returns = load_asset_panel(run_dir, "log_return", phase=phase)
    fundamentals = load_asset_panel(run_dir, "fundamental_price", phase=phase)
    if market_returns.empty and fundamentals.empty:
        return _empty_figure("No per-asset return series is available for this run.")

    figure = make_subplots(
        rows=len(assets),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=[f"{name}: market vs fundamental log returns" for name in assets],
    )

    for position, name in enumerate(assets):
        row = position + 1
        colour = _asset_colour(position)
        if name in market_returns.columns:
            figure.add_trace(
                go.Scatter(
                    x=market_returns.index,
                    y=pd.to_numeric(market_returns[name], errors="coerce"),
                    name=f"{name} market",
                    legendgroup=name,
                    line=dict(color=colour, width=1.1),
                ),
                row=row,
                col=1,
            )
        if name in fundamentals.columns:
            figure.add_trace(
                go.Scatter(
                    x=fundamentals.index,
                    y=_log_differences(fundamentals[name]),
                    name=f"{name} fundamental",
                    legendgroup=name,
                    line=dict(color=REPORT_COLOURS["graphite"], width=1.0, dash="dot"),
                ),
                row=row,
                col=1,
            )
        figure.update_yaxes(title_text="Log return", row=row, col=1)

    figure.update_xaxes(title_text="Simulation step", row=len(assets), col=1)
    figure.update_layout(
        title="Market and Fundamental Log Returns by Asset",
        template=PLOT_TEMPLATE,
        height=max(420, 280 * len(assets)),
        hovermode="x unified",
    )
    return figure


def make_asset_microstructure_quotes_figure(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot each asset's best quotes, midquote, market price, and last trade.

    Each asset has its own order book, so quote formation is an independent
    process per market and gets its own axis. Non-positive values mark steps
    with an empty book side and are masked rather than plotted as zero, which
    would otherwise read as a collapse in price.
    """

    assets = list_assets(run_dir)
    if not assets:
        return _empty_figure("No per-asset LOB quote diagnostics are available.")

    quote_styles = [
        ("market_price", "Market price", REPORT_COLOURS["graphite"], "solid", "lines"),
        ("best_bid", "Best bid", REPORT_COLOURS["green"], "solid", "lines"),
        ("best_ask", "Best ask", REPORT_COLOURS["red"], "solid", "lines"),
        ("mid_quote", "Midquote", REPORT_COLOURS["blue"], "dash", "lines"),
        ("last_trade_price", "Last trade", REPORT_COLOURS["amber"], "dot", "markers"),
    ]
    panels = {
        column: load_asset_panel(run_dir, column, phase=phase)
        for column, _, _, _, _ in quote_styles
    }
    if all(panel.empty for panel in panels.values()):
        return _empty_figure("No per-asset LOB quote diagnostics are available.")

    figure = make_subplots(
        rows=len(assets),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=[f"{name}: quotes and transaction prices" for name in assets],
    )

    for position, name in enumerate(assets):
        row = position + 1
        for column, label, colour, dash, mode in quote_styles:
            panel = panels[column]
            if name not in panel.columns:
                continue
            values = pd.to_numeric(panel[name], errors="coerce")
            visible_values = values.where(values > 0)
            if visible_values.notna().sum() == 0:
                continue
            figure.add_trace(
                go.Scatter(
                    x=panel.index,
                    y=visible_values,
                    mode=mode,
                    name=label,
                    legendgroup=label,
                    showlegend=row == 1,
                    line=dict(color=colour, width=1.4, dash=dash),
                    marker=dict(color=colour, size=4),
                ),
                row=row,
                col=1,
            )
        figure.update_yaxes(title_text="Price", row=row, col=1)

    if not figure.data:
        return _empty_figure("No per-asset LOB quote diagnostics are available.")
    figure.update_xaxes(title_text="Simulation step", row=len(assets), col=1)
    figure.update_layout(
        title="Limit Order Book Quotes and Transaction Prices by Asset",
        template=PLOT_TEMPLATE,
        height=max(420, 330 * len(assets)),
        legend_title="Series",
    )
    return figure


def make_asset_microstructure_liquidity_figure(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot spread, visible depth, and depth imbalance for each asset.

    Assets share one axis per diagnostic rather than getting one panel each:
    liquidity is the quantity a reader most wants to compare directly between
    markets, and spread and depth are already expressed in units that make that
    comparison meaningful.
    """

    assets = list_assets(run_dir)
    if not assets:
        return _empty_figure("No per-asset LOB liquidity diagnostics are available.")

    spread = load_asset_panel(run_dir, "bid_ask_spread", phase=phase)
    bid_depth = load_asset_panel(run_dir, "bid_depth", phase=phase)
    ask_depth = load_asset_panel(run_dir, "ask_depth", phase=phase)
    if spread.empty and bid_depth.empty and ask_depth.empty:
        return _empty_figure("No per-asset LOB liquidity diagnostics are available.")

    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        subplot_titles=["Bid-Ask Spread", "Visible Book Depth", "Depth Imbalance"],
        vertical_spacing=0.08,
    )

    for position, name in enumerate(assets):
        colour = _asset_colour(position)
        if name in spread.columns:
            figure.add_trace(
                go.Scatter(
                    x=spread.index,
                    y=pd.to_numeric(spread[name], errors="coerce"),
                    mode="lines",
                    name=name,
                    legendgroup=name,
                    line=dict(color=colour, width=1.4),
                ),
                row=1,
                col=1,
            )
        if name not in bid_depth.columns or name not in ask_depth.columns:
            continue

        bids = pd.to_numeric(bid_depth[name], errors="coerce").fillna(0.0)
        asks = pd.to_numeric(ask_depth[name], errors="coerce").fillna(0.0)
        total_depth = bids + asks
        figure.add_trace(
            go.Scatter(
                x=bid_depth.index,
                y=total_depth,
                mode="lines",
                name=name,
                legendgroup=name,
                showlegend=False,
                line=dict(color=colour, width=1.4),
            ),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=bid_depth.index,
                y=(bids - asks) / total_depth.replace(0.0, np.nan),
                mode="lines",
                name=name,
                legendgroup=name,
                showlegend=False,
                line=dict(color=colour, width=1.4),
            ),
            row=3,
            col=1,
        )

    if not figure.data:
        return _empty_figure("No per-asset LOB liquidity diagnostics are available.")
    figure.update_layout(
        title="Limit Order Book Liquidity by Asset",
        template=PLOT_TEMPLATE,
        height=780,
        legend_title="Asset",
    )
    figure.update_xaxes(title_text="Simulation step", row=3, col=1)
    figure.update_yaxes(title_text="Spread", row=1, col=1)
    figure.update_yaxes(title_text="Depth", row=2, col=1)
    figure.update_yaxes(title_text="(Bid - Ask) / Total", row=3, col=1)
    return figure


def make_asset_order_flow_figure(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot order-style composition, lifecycle events, and executions per asset.

    Lifecycle events sum every way a resting order leaves the book without
    executing — random cancellation, expiry, and the feasibility checks applied
    at execution time — because they are alternative routes to the same outcome.
    """

    assets = list_assets(run_dir)
    if not assets:
        return _empty_figure("No per-asset LOB order-flow diagnostics are available.")

    limit_orders = load_asset_panel(run_dir, "submitted_limit_orders", phase=phase)
    market_orders = load_asset_panel(run_dir, "submitted_market_orders", phase=phase)
    executed = load_asset_panel(run_dir, "executed_trades", phase=phase)
    lifecycle_columns = [
        "stale_cancelled_orders",
        "expired_orders",
        "infeasible_resting_cancellations",
        "infeasible_incoming_cancellations",
    ]
    lifecycle_panels = [
        load_asset_panel(run_dir, column, phase=phase) for column in lifecycle_columns
    ]

    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "Market-Order Share",
            "Cancelled and Expired Resting Orders",
            "Executed Trades",
        ],
        vertical_spacing=0.08,
    )

    for position, name in enumerate(assets):
        colour = _asset_colour(position)
        if name in limit_orders.columns and name in market_orders.columns:
            limits = pd.to_numeric(limit_orders[name], errors="coerce").fillna(0.0)
            markets = pd.to_numeric(market_orders[name], errors="coerce").fillna(0.0)
            submitted_total = (limits + markets).replace(0.0, np.nan)
            figure.add_trace(
                go.Scatter(
                    x=limit_orders.index,
                    y=markets / submitted_total,
                    mode="lines",
                    name=name,
                    legendgroup=name,
                    line=dict(color=colour, width=1.4),
                ),
                row=1,
                col=1,
            )

        lifecycle_events: pd.Series | None = None
        for panel in lifecycle_panels:
            if name not in panel.columns:
                continue
            values = pd.to_numeric(panel[name], errors="coerce").fillna(0.0)
            lifecycle_events = values if lifecycle_events is None else lifecycle_events + values
        if lifecycle_events is not None:
            figure.add_trace(
                go.Scatter(
                    x=lifecycle_events.index,
                    y=lifecycle_events,
                    mode="lines",
                    name=name,
                    legendgroup=name,
                    showlegend=False,
                    line=dict(color=colour, width=1.4),
                ),
                row=2,
                col=1,
            )

        if name in executed.columns:
            figure.add_trace(
                go.Scatter(
                    x=executed.index,
                    y=pd.to_numeric(executed[name], errors="coerce").fillna(0.0),
                    mode="lines",
                    name=name,
                    legendgroup=name,
                    showlegend=False,
                    line=dict(color=colour, width=1.4),
                ),
                row=3,
                col=1,
            )

    if not figure.data:
        return _empty_figure("No per-asset LOB order-flow diagnostics are available.")
    figure.update_layout(
        title="Order Flow and Book Lifecycle by Asset",
        template=PLOT_TEMPLATE,
        height=780,
        legend_title="Asset",
    )
    figure.update_xaxes(title_text="Simulation step", row=3, col=1)
    figure.update_yaxes(title_text="Share", range=[0, 1], row=1, col=1)
    figure.update_yaxes(title_text="Orders", row=2, col=1)
    figure.update_yaxes(title_text="Trades", row=3, col=1)
    return figure


def make_asset_allocative_efficiency_figure(
    run_dir: Path | str,
    *,
    phase: str | None = "simulation",
) -> go.Figure:
    """Plot gross double-auction allocative efficiency for each asset.

    Steps with no positive-surplus match are masked rather than plotted as zero
    efficiency, matching the run-level mean convention: no opportunity to
    allocate is not the same as allocating badly.
    """

    assets = list_assets(run_dir)
    if not assets:
        return _empty_figure("No per-asset allocative-efficiency diagnostics are available.")

    efficiency = load_asset_panel(run_dir, "allocative_efficiency", phase=phase)
    maximum_surplus = load_asset_panel(run_dir, "maximum_allocative_surplus", phase=phase)
    realized_surplus = load_asset_panel(run_dir, "realized_allocative_surplus", phase=phase)
    if efficiency.empty and maximum_surplus.empty:
        return _empty_figure(
            "No per-asset allocative-efficiency diagnostics are available. Runs archived "
            "before the per-asset surplus columns existed do not record them."
        )

    has_surplus_schedule = not maximum_surplus.empty
    subplot_titles = ["Allocative Efficiency"]
    if has_surplus_schedule:
        subplot_titles.append("Gross Allocative Surplus")
    figure = make_subplots(
        rows=len(subplot_titles),
        cols=1,
        shared_xaxes=True,
        subplot_titles=subplot_titles,
        vertical_spacing=0.10,
    )

    for position, name in enumerate(assets):
        colour = _asset_colour(position)
        if name in efficiency.columns:
            values = pd.to_numeric(efficiency[name], errors="coerce")
            if name in maximum_surplus.columns:
                opportunity = pd.to_numeric(maximum_surplus[name], errors="coerce")
                values = values.where(opportunity > 0.0)
            figure.add_trace(
                go.Scatter(
                    x=efficiency.index,
                    y=values,
                    mode="lines",
                    name=name,
                    legendgroup=name,
                    line=dict(color=colour, width=1.5),
                    hovertemplate=(
                        f"Step=%{{x}}<br>Allocative efficiency=%{{y:.4f}}<extra>{name}</extra>"
                    ),
                ),
                row=1,
                col=1,
            )
        if not has_surplus_schedule:
            continue
        if name in maximum_surplus.columns:
            figure.add_trace(
                go.Scatter(
                    x=maximum_surplus.index,
                    y=pd.to_numeric(maximum_surplus[name], errors="coerce"),
                    mode="lines",
                    name=f"{name} maximum surplus",
                    legendgroup=name,
                    showlegend=False,
                    line=dict(color=colour, width=1.2),
                ),
                row=2,
                col=1,
            )
        if name in realized_surplus.columns:
            figure.add_trace(
                go.Scatter(
                    x=realized_surplus.index,
                    y=pd.to_numeric(realized_surplus[name], errors="coerce"),
                    mode="lines",
                    name=f"{name} realized surplus",
                    legendgroup=name,
                    showlegend=False,
                    line=dict(color=colour, width=1.1, dash="dash"),
                ),
                row=2,
                col=1,
            )

    if not figure.data:
        return _empty_figure("No per-asset allocative-efficiency diagnostics are available.")
    figure.update_layout(
        title="Double-Auction Allocative Efficiency by Asset",
        template=PLOT_TEMPLATE,
        height=680 if has_surplus_schedule else 420,
        legend_title="Asset",
    )
    figure.update_xaxes(title_text="Simulation step", row=len(subplot_titles), col=1)
    figure.update_yaxes(title_text="Efficiency", range=[0, 1], row=1, col=1)
    if has_surplus_schedule:
        figure.update_yaxes(title_text="Gross Surplus", row=2, col=1)
    return figure


def _log_differences(levels: pd.Series) -> pd.Series:
    """Return ``log(x_t / x_{t-1})``, leaving non-positive levels missing."""

    values = pd.to_numeric(levels, errors="coerce")
    previous = values.shift(1)
    valid = np.isfinite(values) & np.isfinite(previous) & (values > 0) & (previous > 0)
    returns = pd.Series(np.nan, index=values.index, dtype="float64")
    returns.loc[valid] = np.log(values.loc[valid] / previous.loc[valid])
    return returns


def build_asset_configuration_table(run_dir: Path | str) -> pd.DataFrame:
    """Return the resolved per-asset configuration as a display table.

    Surfacing the generating parameters next to the figures makes each panel
    self-contained for a reader who does not have the ``.cfg`` file to hand,
    and records the units, which differ between the arithmetic and geometric
    processes.
    """

    configuration = load_multi_asset_configuration(run_dir)
    if not configuration.has_configuration:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for asset in (*configuration.assets, *configuration.disabled_assets):
        rows.append(
            {
                "Asset": asset.name,
                "Enabled": "yes" if asset.enabled else "no",
                "Primary": "yes" if asset.name == configuration.primary_asset else "no",
                "Fundamental process": asset.process_label,
                "Drift / step": asset.fundamental_drift_per_step,
                "Shock s.d.": asset.fundamental_shock_std_dev,
                "Drift & shock units": asset.parameter_units,
                "Initial price": asset.initial_price,
                "Supply per agent": asset.initial_stock,
                "Tick size": asset.price_tick_size,
                "Min fundamental": asset.minimum_fundamental_value,
            }
        )
    return pd.DataFrame(rows)
