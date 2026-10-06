"""Order-flow payload: who pushed the price, read from the trade ledger.

The market stack shows what the price did and the crisis lens shows when it was in
trouble. This module supplies the third reading — *who* was trading while it
happened — as the net order flow of each strategy at every step, the matrix of
who bought from whom, and the protagonist's own fills. The market story no longer
draws those fills as markers on the price line, but they are still served.

Nothing here computes a research statistic. The flows, the counterparty volumes
and the zero-sum check are ``statistics.order_flow``'s; this module decides how
they are keyed to the chart's x-axis and which cell becomes which payload field.

**Both groupings are shipped.** Whether the four chartist rules are drawn as one
family or as four variants is the reader's choice, and the interface must not
make it by summing arrays itself — the browser holds no analysis logic. So each
grouping is aggregated here, once, and the toggle only selects between them.

**Flows follow the chart's own axis.** A run longer than the chart's point cap is
thinned before it is drawn. A flow is an *amount per step*, so thinning it by
taking every k-th step would silently discard (k−1)/k of the volume. Each flow is
instead added into the bar of the last drawn step at or before it, which keeps
the total on screen equal to the total traded.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from abm_analysis.archive.archives import RunArchive
from abm_analysis.statistics.agents import STRATEGY_FAMILIES, strategy_family
from abm_analysis.statistics.order_flow import (
    GROUPINGS,
    UNKNOWN_GROUP,
    build_group_lookup,
    counterparty_volume,
    maximum_net_flow_residual,
    net_flow_by_strategy,
    protagonist_fills,
    read_trade_ledger,
)
from abm_analysis.web.asset_view import AssetContext
from abm_analysis.web.protagonist_view import protagonist_agent_id
from abm_analysis.web.serialisation import numeric_or_none


#: Relative size of the net-flow residual below which a ledger counts as balanced.
#: Floating-point summation of many fills leaves dust; a ledger missing a side
#: leaves a residual of the order of the volume itself.
BALANCE_TOLERANCE = 1.0e-6


def build_order_flow_view(
    archive: RunArchive,
    agents: pd.DataFrame,
    context: AssetContext,
    *,
    series: dict[str, Any],
    analysed: pd.DataFrame,
) -> dict[str, Any]:
    """Build the order-flow panel's payload for one run.

    Args:
        archive: The run being displayed.
        agents: End-of-run agent snapshot; it is what attributes a ledger row's
            agent to a strategy, so a run without it has no order-flow view.
        context: Which assets are reported. Ledger rows are kept only for these.
        series: The chart series already built for the run, whose step axis the
            flows are keyed to.
        analysed: The phase-restricted primary-asset step series, used to turn a
            simulation step into a row index when the axis is the row index.

    Returns:
        A payload with ``available`` false and a ``message`` saying which of the
        several reasons applies. A missing ledger is an archiving choice rather
        than a broken run, so the panel says so instead of disappearing.
    """

    if archive.trade_ledger_csv is None:
        return _absent(
            "This run was archived without a trade ledger (trade_ledger_enabled = 0), "
            "so order-flow views are unavailable."
        )
    ledger = read_trade_ledger(archive.trade_ledger_csv)
    if ledger.empty:
        return _absent("The trade ledger holds no usable rows.")
    if agents.empty:
        return _absent(
            "This run has no agents_final.csv, which attributes each ledger row to a "
            "strategy, so order-flow views are unavailable."
        )

    alias = _asset_alias(ledger, context)
    if not alias:
        return _absent(
            "The trade ledger names assets "
            f"({', '.join(sorted(set(ledger['asset'])) or ['none'])}) that do not match the run's "
            f"({', '.join(context.names)}), so its fills cannot be placed on the charts."
        )
    ledger = ledger[ledger["asset"].isin(alias)].copy()
    ledger["asset"] = ledger["asset"].map(alias)

    to_x = _x_mapper(series, analysed)
    sampled_x = np.asarray(
        pd.to_numeric(pd.Series(series.get("step", [])), errors="coerce"), dtype=float
    )

    groupings: dict[str, Any] = {}
    residual = 0.0
    for grouping in GROUPINGS:
        lookup = build_group_lookup(agents, grouping)
        flows = net_flow_by_strategy(ledger, lookup)
        if grouping == GROUPINGS[0]:
            residual = maximum_net_flow_residual(flows)
        groupings[grouping] = _grouping_payload(
            flows,
            counterparty_volume(ledger, lookup),
            context,
            to_x,
            sampled_x,
        )

    purchases = ledger[ledger["side"] == "BUY"]
    total_volume = float(purchases["qty"].sum())
    return {
        "available": True,
        "message": None,
        "groupings": groupings,
        "protagonist": _protagonist_block(ledger, agents, to_x, sampled_x),
        "checks": {
            "ledger_rows": int(len(ledger)),
            "trades": int(len(purchases)),
            "traded_quantity": numeric_or_none(total_volume),
            "net_flow_residual": numeric_or_none(residual),
            "balanced": bool(residual <= BALANCE_TOLERANCE * max(1.0, total_volume)),
        },
    }


def _absent(message: str) -> dict[str, Any]:
    """Return the payload for a run whose order-flow views cannot be shown."""

    return {
        "available": False,
        "message": message,
        "groupings": {},
        "protagonist": {"available": False},
        "checks": None,
    }


def _asset_alias(ledger: pd.DataFrame, context: AssetContext) -> dict[str, str]:
    """Map the ledger's asset labels onto the assets the run reports.

    A single-market run may name its asset differently in the ledger and in
    ``config.json`` — or in no config at all — so when both sides name exactly one
    market the two are taken to be the same market. With several markets the
    names are the only evidence there is, so only exact matches are kept.
    """

    ledger_assets = list(dict.fromkeys(ledger["asset"].astype(str)))
    if context.count == 1 and len(ledger_assets) == 1:
        return {ledger_assets[0]: context.names[0]}
    return {name: name for name in ledger_assets if name in context.names}


def _x_mapper(
    series: dict[str, Any],
    analysed: pd.DataFrame,
) -> Callable[[pd.Series], pd.Series]:
    """Return a function turning ledger times into positions on the chart's axis.

    The ledger's ``time`` is the simulation step. When the chart is drawn against
    the row index instead — a single-asset run with warm-up in view — a step has
    to be looked up in the analysed rows; a step with no row has no position and
    comes back ``NaN``, so it is dropped rather than drawn in the wrong place.
    """

    if series.get("step_axis") != "row_index" or "simulation_step" not in analysed.columns:
        return lambda times: pd.to_numeric(times, errors="coerce")

    steps = pd.to_numeric(analysed["simulation_step"], errors="coerce")
    rows = pd.to_numeric(analysed["row_index"], errors="coerce")
    position_of_step = {float(s): float(r) for s, r in zip(steps, rows) if np.isfinite(s)}
    return lambda times: pd.to_numeric(times, errors="coerce").map(position_of_step)


def _drawn_range(sampled_x: np.ndarray) -> tuple[float, float]:
    """Return the half-open interval of positions the drawn steps stand for.

    The upper end is one drawn-step spacing past the last drawn step, because
    thinning leaves that step standing for the rest of the run.
    """

    spacing = float(np.median(np.diff(sampled_x))) if sampled_x.size > 1 else 1.0
    return float(sampled_x[0]), float(sampled_x[-1]) + spacing


def _bin_to_drawn_steps(positions: pd.Series, sampled_x: np.ndarray) -> pd.Series:
    """Move each position to the last drawn step at or before it.

    The final drawn step stands for the rest of the run when the series has been
    thinned, so a position up to one drawn-step spacing past it still belongs to
    that bar; without that allowance the last partial bin would lose its volume.
    Positions before the first drawn step, or beyond that allowance, come back
    ``NaN``: a bar placed at the nearest end of the chart would claim volume
    traded somewhere else.
    """

    values = pd.to_numeric(positions, errors="coerce").to_numpy(dtype=float)
    if sampled_x.size == 0:
        return pd.Series(np.nan, index=positions.index)
    lower, upper = _drawn_range(sampled_x)
    inside = np.isfinite(values) & (values >= lower) & (values < upper)
    binned = np.full(values.shape, np.nan)
    index = np.searchsorted(sampled_x, values[inside], side="right") - 1
    binned[inside] = sampled_x[np.clip(index, 0, sampled_x.size - 1)]
    return pd.Series(binned, index=positions.index)


def _ordered_groups(present: set[str]) -> list[str]:
    """Order groups as the stack and the legend draw them.

    Families keep the fixed family order so a strategy sits in the same place in
    every run, and variants follow their family. A label outside the known
    families comes after them, and the group of agents the snapshot does not list
    comes last of all.
    """

    def rank(group: str) -> tuple[int, str]:
        if group == UNKNOWN_GROUP:
            return (len(STRATEGY_FAMILIES) + 1, group)
        family = strategy_family(group)
        position = (
            STRATEGY_FAMILIES.index(family)
            if family in STRATEGY_FAMILIES
            else len(STRATEGY_FAMILIES)
        )
        return (position, group)

    return sorted(present, key=rank)


def _grouping_payload(
    flows: pd.DataFrame,
    matrix: pd.DataFrame,
    context: AssetContext,
    to_x: Callable[[pd.Series], pd.Series],
    sampled_x: np.ndarray,
) -> dict[str, Any]:
    """Build one grouping's per-asset flow bars and counterparty matrix."""

    groups = _ordered_groups(set(flows["group"]) if not flows.empty else set())
    assets: dict[str, Any] = {}
    for asset in context.names:
        asset_flows = flows[flows["asset"] == asset]
        if asset_flows.empty:
            continue
        positioned = asset_flows.assign(
            x=_bin_to_drawn_steps(to_x(asset_flows["time"]), sampled_x)
        ).dropna(subset=["x"])
        if positioned.empty:
            continue
        pivot = positioned.pivot_table(
            index="x", columns="group", values="net_quantity", aggfunc="sum", fill_value=0.0
        )
        assets[asset] = {
            "x": [float(value) for value in pivot.index],
            "net": {
                group: [float(value) for value in pivot[group]]
                for group in groups
                if group in pivot.columns
            },
            "counterparty": _counterparty_block(matrix[matrix["asset"] == asset], groups),
        }
    return {
        "groups": groups,
        "family_of_group": {group: strategy_family(group) for group in groups},
        "assets": assets,
    }


def _counterparty_block(matrix: pd.DataFrame, groups: list[str]) -> dict[str, Any]:
    """Arrange buyer × seller volumes as a square matrix over the groups.

    Rows are buyers and columns are sellers. ``share`` divides each row by its own
    total — of everything this group bought, how much came from each group — which
    removes the effect of some strategies simply trading more than others.
    """

    size = len(groups)
    position = {group: index for index, group in enumerate(groups)}
    volume = np.zeros((size, size))
    trades = np.zeros((size, size))
    for _, row in matrix.iterrows():
        buyer, seller = position.get(row["buyer_group"]), position.get(row["seller_group"])
        if buyer is None or seller is None:
            continue
        volume[buyer, seller] += float(row["quantity"])
        trades[buyer, seller] += float(row["trades"])

    totals = volume.sum(axis=1, keepdims=True)
    share = np.divide(volume, totals, out=np.zeros_like(volume), where=totals > 0)
    return {
        "volume": volume.tolist(),
        "share": share.tolist(),
        "trades": trades.tolist(),
    }


def _protagonist_block(
    ledger: pd.DataFrame,
    agents: pd.DataFrame,
    to_x: Callable[[pd.Series], pd.Series],
    sampled_x: np.ndarray,
) -> dict[str, Any]:
    """Build the protagonist's fills, per asset.

    The market story no longer draws these as markers on the price line, but they
    are still served. Fills are kept at their own step rather than binned: they
    are events, and a fill moved to a neighbouring step would misstate when he
    traded.
    """

    agent_id = protagonist_agent_id(agents)
    if agent_id is None:
        return {"available": False}

    fills = protagonist_fills(ledger, agent_id)
    assets: dict[str, Any] = {}
    for asset, rows in fills.groupby("asset", sort=False):
        positions = to_x(rows["time"])
        keep = positions.notna()
        if sampled_x.size:
            lower, upper = _drawn_range(sampled_x)
            keep &= (positions >= lower) & (positions < upper)
        rows, positions = rows[keep], positions[keep]
        if rows.empty:
            continue
        assets[str(asset)] = {
            "x": [float(value) for value in positions],
            "side": [str(value) for value in rows["side"]],
            "price": [numeric_or_none(value) for value in rows["price"]],
            "quantity": [numeric_or_none(value) for value in rows["qty"]],
        }
    return {"available": True, "agent_id": agent_id, "assets": assets}
