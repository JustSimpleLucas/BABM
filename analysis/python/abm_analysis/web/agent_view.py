"""Agent-level statistics for the dashboard.

The market panels say what the price did; this one says who traded it. The
strategy mix is the model's central experimental lever — a run of 1,000 noise
traders and a run of 340 fundamentalists against 300 chartists produce different
markets by construction — so the dashboard reports outcomes broken down by the
strategy each agent was running at the end of the simulation.

The per-strategy aggregation is
``statistics.agents.build_agent_summary_statistics``, the same function that
writes the exported agent tables, so the two cannot disagree. No Gini is
computed here: the authoritative implementation is the simulator's, and its
result is read from ``summary_metrics.csv``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from abm_analysis.archive.archives import RunArchive
from abm_analysis.statistics.agents import (
    AGENT_STRATEGY_COLUMN_CANDIDATES,
    build_agent_summary_statistics,
    strategy_family,
)
from abm_analysis.web.metrics import (
    SIMULATOR_SUMMARY_SOURCE,
    density_histogram,
    density_on_edges,
    finite_values,
    metric,
    values_of,
)


#: Columns of the per-strategy table, as (payload key, heading, number format).
#: A deliberate subset of the forty-odd columns
#: ``build_agent_summary_statistics`` produces: enough to compare strategies,
#: few enough to read without scrolling.
STRATEGY_TABLE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("agent_count", "Agents", "integer"),
    ("final_wealth_mean", "Mean wealth", "amount"),
    ("final_wealth_median", "Median wealth", "amount"),
    ("final_wealth_std", "Wealth s.d.", "amount"),
    ("wealth_change_mean", "Mean change", "amount"),
    ("number_of_trades_mean", "Mean trades", "amount"),
    ("traded_volume_mean", "Mean volume", "amount"),
)

#: Bins for the wealth density. Fewer than the return histogram uses, because
#: agent populations are smaller than return series and a strategy with a
#: handful of agents should not be drawn as a comb.
WEALTH_DISTRIBUTION_BINS = 40


def build_agent_view(
    archive: RunArchive,
    agents: pd.DataFrame,
    summary_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Build the agent panel for one run.

    ``metrics`` is populated even when the run has no ``agents_final.csv``, so
    the panel still shows the wealth Gini and states why the rest is missing.
    A panel that silently disappears leaves a reader unable to tell an absent
    artefact from a run with no agents.

    ``agents`` is the frame ``metrics.read_agent_snapshot`` produced, passed in
    rather than read here so that this panel and the protagonist panel describe
    exactly the same population.
    """

    gini = metric(
        "Wealth Gini (final)",
        summary_metrics.get("final_wealth_gini_coefficient"),
        format="decimal",
        source=SIMULATOR_SUMMARY_SOURCE,
        emphasis=True,
    )

    if agents.empty:
        return {
            "available": False,
            "message": (
                "This run has no agents_final.csv, so per-agent statistics are unavailable."
            ),
            "agent_count": None,
            "strategy_column": None,
            "metrics": [gini],
            "columns": [],
            "rows": [],
            "wealth_distribution": {"available": False},
            "social_map": {"available": False},
        }

    strategy_column = _strategy_column(agents)
    summary = build_agent_summary_statistics(archive.run_dir.parent, [archive.run_id])

    return {
        "available": True,
        "message": None,
        "agent_count": int(len(agents)),
        "strategy_column": strategy_column,
        "metrics": _agent_metrics(agents, strategy_column, gini),
        "columns": [
            {"key": key, "label": label, "format": number_format}
            for key, label, number_format in STRATEGY_TABLE_COLUMNS
        ],
        "rows": _strategy_rows(summary, strategy_column),
        "wealth_distribution": _wealth_distribution(agents, strategy_column),
        "social_map": _social_map(agents, strategy_column),
    }


def _strategy_column(agents: pd.DataFrame) -> str | None:
    """Return the column naming each agent's strategy, preferring the final one.

    An agent's strategy can change during a run, so the end-of-run strategy is
    what its final wealth should be attributed to.
    """

    for candidate in AGENT_STRATEGY_COLUMN_CANDIDATES:
        if candidate in agents.columns:
            return candidate
    return None


def _agent_metrics(
    agents: pd.DataFrame,
    strategy_column: str | None,
    gini: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the headline cells shown above the per-strategy table."""

    wealth = finite_values(agents.get("final_wealth", pd.Series(dtype="float64")))
    strategy_count = (
        int(agents[strategy_column].nunique(dropna=False)) if strategy_column else None
    )

    return [
        metric("Agents", len(agents), format="integer"),
        metric("Strategies", strategy_count, format="integer"),
        gini,
        metric(
            "Mean final wealth",
            None if wealth.empty else float(wealth.mean()),
            format="amount",
        ),
        metric(
            "Median final wealth",
            None if wealth.empty else float(wealth.median()),
            format="amount",
        ),
        metric(
            "Total trades",
            finite_values(agents.get("number_of_trades", pd.Series(dtype="float64"))).sum(),
            format="integer",
        ),
    ]


def _strategy_rows(summary: pd.DataFrame, strategy_column: str | None) -> list[dict[str, Any]]:
    """Select the display columns from the full per-strategy summary frame."""

    if summary.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, record in summary.iterrows():
        row: dict[str, Any] = {
            "strategy": str(record[strategy_column])
            if strategy_column and strategy_column in summary.columns
            else "all agents"
        }
        for key, _label, _format in STRATEGY_TABLE_COLUMNS:
            row[key] = record[key] if key in summary.columns else None
        rows.append(row)
    rows.sort(key=lambda entry: -(entry.get("agent_count") or 0))
    return rows


def _wealth_distribution(agents: pd.DataFrame, strategy_column: str | None) -> dict[str, Any]:
    """Build final-wealth densities per strategy over one shared set of bins.

    Shared bins are what make the curves comparable: binned to their own ranges,
    two strategies with different wealth levels would be drawn on top of each
    other as if they overlapped.
    """

    wealth = finite_values(agents.get("final_wealth", pd.Series(dtype="float64")))
    if wealth.size < 2:
        return {"available": False}

    shared = density_histogram(
        wealth.to_numpy(dtype=float), maximum_bins=WEALTH_DISTRIBUTION_BINS
    )
    if not shared["available"]:
        return {"available": False}

    if strategy_column is None:
        labels = pd.Series("all agents", index=agents.index)
    else:
        labels = agents[strategy_column].astype(str).str.strip()
    families = labels.map(strategy_family)

    def densities(keys: pd.Series) -> list[dict[str, Any]]:
        entries = [
            {
                "strategy": str(key),
                "family": strategy_family(key),
                "count": int(finite_values(values).size),
                "density": density_on_edges(values, shared["bin_edges"]),
            }
            for key, values in agents["final_wealth"].groupby(keys, dropna=False)
        ]
        entries.sort(key=lambda entry: -entry["count"])
        return entries

    return {
        "available": True,
        "bin_centre": shared["bin_centre"],
        "bin_width": shared["bin_width"],
        # Exact labels, kept for the split view and for archives whose labels
        # carry information the family discards (the chartist rule).
        "strategies": densities(labels),
        # The same agents merged into families, on the same bins, so the two
        # views can be toggled without the curves changing scale.
        "families": densities(families),
    }


def _social_map(agents: pd.DataFrame, strategy_column: str | None) -> dict[str, Any]:
    """Build the per-agent arrays behind the social-space map.

    Agents sit at fixed coordinates in the model's social space, and the social
    channel moves an agent's opinion towards its neighbours'. Whether that channel
    does anything shows up as structure on this map: opinions that cluster in
    space mean the neighbourhood is shaping them, and opinions scattered at random
    mean it is not. The same map coloured by wealth change asks whether
    neighbours fare alike, and coloured by loss aversion whether the prospect
    heterogeneity is spread evenly or clumped.

    Columns an archive lacks are shipped as ``null`` per agent rather than
    omitted, so the interface can offer only the colourings that have data.
    """

    coordinates = {
        axis: pd.to_numeric(agents.get(column), errors="coerce")
        for axis, column in (("x", "x_coordinate"), ("y", "y_coordinate"))
        if column in agents.columns
    }
    if len(coordinates) < 2:
        return {"available": False}
    located = coordinates["x"].notna() & coordinates["y"].notna()
    if int(located.sum()) < 2:
        return {"available": False}
    mapped = agents[located]

    def column(name: str) -> list[float | None]:
        if name not in mapped.columns:
            return [None] * len(mapped)
        return values_of(mapped[name])

    labels = (
        mapped[strategy_column].astype(str).str.strip()
        if strategy_column
        else pd.Series("all agents", index=mapped.index)
    )
    flags = (
        pd.to_numeric(mapped["is_protagonist"], errors="coerce").fillna(0) != 0
        if "is_protagonist" in mapped.columns
        else pd.Series(False, index=mapped.index)
    )
    return {
        "available": True,
        "agent_id": column("agent_id"),
        "x": values_of(coordinates["x"][located]),
        "y": values_of(coordinates["y"][located]),
        "opinion": column("final_opinion"),
        "wealth_change": column("wealth_change"),
        "loss_aversion": column("prospect_loss_aversion"),
        "strategy": [str(label) for label in labels],
        "family": [strategy_family(label) for label in labels],
        "is_protagonist": [bool(flag) for flag in flags],
    }
