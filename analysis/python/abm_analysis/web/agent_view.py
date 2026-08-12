"""Agent-level statistics for the dashboard.

The market panels say what the price did; this one says who traded it. The
strategy mix is the model's central experimental lever — a run of 1,000 noise
traders and a run of 340 fundamentalists against 300 chartists produce different
markets by construction — so the dashboard reports outcomes broken down by the
strategy each agent was running at the end of the simulation.

The per-strategy aggregation is ``plots.agents.build_agent_summary_statistics``,
the same function behind the static report's Agent Summary Statistics table, so
the two cannot disagree. No Gini is computed here: the authoritative
implementation is the simulator's, and its result is read from
``summary_metrics.csv``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from abm_analysis.archive.archives import RunArchive
from abm_analysis.archive.data import read_csv_if_exists
from abm_analysis.plots.agents import build_agent_summary_statistics
from abm_analysis.plots.common import AGENT_STRATEGY_COLUMN_CANDIDATES
from abm_analysis.web.metrics import (
    SIMULATOR_SUMMARY_SOURCE,
    density_histogram,
    density_on_edges,
    finite_values,
    metric,
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
    summary_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Build the agent panel for one run.

    ``metrics`` is populated even when the run has no ``agents_final.csv``, so
    the panel still shows the wealth Gini and states why the rest is missing.
    A panel that silently disappears leaves a reader unable to tell an absent
    artefact from a run with no agents.
    """

    agents = _agent_snapshot(archive)
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
    }


def _agent_snapshot(archive: RunArchive) -> pd.DataFrame:
    """Read one run's end-of-run agent snapshot, with the derived wealth change.

    ``wealth_change`` is derived the same way ``plots.agents`` derives it, so
    the dashboard's column and the report's column mean the same thing.
    """

    agents = read_csv_if_exists(archive.agents_final_csv)
    if agents.empty:
        return agents
    if "initial_wealth" in agents.columns and "final_wealth" in agents.columns:
        agents["wealth_change"] = pd.to_numeric(
            agents["final_wealth"], errors="coerce"
        ) - pd.to_numeric(agents["initial_wealth"], errors="coerce")
    return agents


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
        groups: list[tuple[str, pd.Series]] = [("all agents", agents["final_wealth"])]
    else:
        groups = [
            (str(label), group["final_wealth"])
            for label, group in agents.groupby(strategy_column, dropna=False)
        ]

    strategies = [
        {
            "strategy": label,
            "count": int(finite_values(values).size),
            "density": density_on_edges(values, shared["bin_edges"]),
        }
        for label, values in groups
    ]
    strategies.sort(key=lambda entry: -entry["count"])

    return {
        "available": True,
        "bin_centre": shared["bin_centre"],
        "bin_width": shared["bin_width"],
        "strategies": strategies,
    }
