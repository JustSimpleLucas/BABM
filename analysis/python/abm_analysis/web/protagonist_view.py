"""Where one identified trader ended up inside the market he traded in.

The agent panel next door answers "how did each strategy do?". This one answers
a different question, and the one a behavioural-finance case study actually
asks: what happened to *this* investor. The model gives him no advantage — he
runs an ordinary strategy through the same clearing machinery as everyone else —
so his outcome is only meaningful relative to the population he traded against.
Every figure here is therefore reported as a standing rather than a level: his
rank among all agents, his wealth beside the population median, his marker
placed on the distribution the agent panel already draws.

Two sources feed the panel, and they answer different halves of the question.
``agents_final.csv`` says where he finished, and the rank is recomputed here
from that frame rather than read from ``summary_metrics.csv``, so the number
shown always describes the archive on screen. ``protagonist_timeseries.csv``
says how he got there — the distinction between an investor who traded well and
one who merely held a rising asset is invisible in a final wealth figure and
obvious in a path drawn against the median.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from abm_analysis.archive.archives import RunArchive
from abm_analysis.archive.data import read_csv_if_exists
from abm_analysis.web.metrics import (
    SIMULATOR_SUMMARY_SOURCE,
    finite_values,
    metric,
    series_values,
    stride_for,
)


#: Column the simulator writes to mark the protagonist in the agent snapshot.
PROTAGONIST_FLAG_COLUMN = "is_protagonist"

#: Series carried into the trajectory chart, as (payload key, CSV column).
TRAJECTORY_SERIES: tuple[tuple[str, str], ...] = (
    ("wealth", "wealth"),
    ("population_median_wealth", "population_median_wealth"),
    ("population_mean_wealth", "population_mean_wealth"),
    ("wealth_percentile_rank", "wealth_percentile_rank"),
    ("risky_weight", "risky_weight"),
)


def build_protagonist_view(
    archive: RunArchive,
    agents: pd.DataFrame,
    summary_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Build the protagonist panel for one run.

    Args:
        archive: The run being displayed.
        agents: End-of-run agent snapshot, already carrying ``wealth_change``.
        summary_metrics: The simulator's headline scalars, used only for the
            configured strategy label.

    Returns:
        A payload with ``available`` false and an explanatory ``message`` when
        the run had no protagonist. An absent protagonist is a modelling choice,
        not a broken archive, so the panel says which of the two it is rather
        than disappearing and leaving the reader to guess.
    """

    row = _protagonist_row(agents)
    if row is None:
        return {
            "available": False,
            "message": _absence_message(archive, agents, summary_metrics),
            "identity": None,
            "metrics": [],
            "standing": None,
            "wealth_marker": None,
            "trajectory": {"available": False},
        }

    wealth = finite_values(agents.get("final_wealth", pd.Series(dtype="float64")))
    standing = _standing(row, wealth)

    return {
        "available": True,
        "message": None,
        "identity": _identity(row, summary_metrics),
        "metrics": _metrics(row, standing),
        "standing": standing,
        "wealth_marker": _numeric(row.get("final_wealth")),
        "trajectory": _trajectory(archive),
    }


def _protagonist_row(agents: pd.DataFrame) -> pd.Series | None:
    """Return the protagonist's snapshot row, or ``None`` when there is none.

    Matching is on the ``is_protagonist`` flag alone. His agent id is the
    highest in the population, which would make an id-based fallback tempting,
    but that ordering is an implementation detail of population construction
    rather than a contract — an archive written before the flag existed simply
    has no protagonist to find, which is the correct answer for it anyway.
    """

    if agents.empty or PROTAGONIST_FLAG_COLUMN not in agents.columns:
        return None
    flags = pd.to_numeric(agents[PROTAGONIST_FLAG_COLUMN], errors="coerce").fillna(0)
    matches = agents[flags != 0]
    if matches.empty:
        return None
    return matches.iloc[0]


def _absence_message(
    archive: RunArchive,
    agents: pd.DataFrame,
    summary_metrics: dict[str, Any],
) -> str:
    """Explain which kind of absence this is, in the reader's terms."""

    if agents.empty:
        return (
            "This run has no agents_final.csv, so the protagonist panel is unavailable."
        )
    if PROTAGONIST_FLAG_COLUMN not in agents.columns:
        return (
            f"{archive.run_id} was archived before the protagonist existed, so no agent "
            "is marked as one."
        )
    if _numeric(summary_metrics.get("protagonist_enabled")):
        return (
            "This run records protagonist_enabled = 1 but no agent carries the flag, "
            "which means the agent snapshot and the summary disagree."
        )
    return "This run was configured without a protagonist (protagonist_enabled = 0)."


def _identity(row: pd.Series, summary_metrics: dict[str, Any]) -> dict[str, Any]:
    """Describe who he is, so the reader can tie the panel to the configuration."""

    strategy = summary_metrics.get("protagonist_strategy")
    return {
        "agent_id": _numeric(row.get("agent_id")),
        "strategy": str(row.get("current_strategy_type", "")) or None,
        "configured_strategy": None if not isinstance(strategy, str) else strategy,
        "initial_cash": _numeric(row.get("initial_cash")),
        "initial_stock": _numeric(row.get("initial_stock")),
        "initial_wealth": _numeric(row.get("initial_wealth")),
        "prospect_theory_enabled": _flag(row.get("prospect_theory_enabled")),
        "loss_aversion": _numeric(row.get("prospect_loss_aversion")),
    }


def _standing(row: pd.Series, wealth: pd.Series) -> dict[str, Any]:
    """Locate his final wealth inside the population's.

    The percentile counts agents strictly poorer than he is, matching the
    simulator's per-step definition exactly, so the number in this panel and the
    one on the trajectory chart cannot drift apart. Ties count as "not poorer",
    which keeps a population of identical agents from reporting everyone as
    above average.
    """

    final_wealth = _numeric(row.get("final_wealth"))
    if final_wealth is None or wealth.empty:
        return {"percentile": None, "rank": None, "population": int(wealth.size) or None}

    poorer = int((wealth < final_wealth).sum())
    population = int(wealth.size)
    return {
        "percentile": poorer / population,
        # Rank counted from the top, so 1 is the wealthiest agent in the market.
        "rank": population - poorer,
        "population": population,
    }


def _metrics(row: pd.Series, standing: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the headline cells, leading with where he placed."""

    initial_wealth = _numeric(row.get("initial_wealth"))
    final_wealth = _numeric(row.get("final_wealth"))
    total_return = (
        None
        if initial_wealth in (None, 0.0) or final_wealth is None
        else (final_wealth / initial_wealth) - 1.0
    )

    return [
        metric(
            "Wealth percentile",
            standing.get("percentile"),
            format="percent_fraction",
            emphasis=True,
        ),
        metric("Rank (1 = wealthiest)", standing.get("rank"), format="integer"),
        metric("Agents in market", standing.get("population"), format="integer"),
        metric("Final wealth", final_wealth, format="amount", emphasis=True),
        metric("Wealth change", _numeric(row.get("wealth_change")), format="amount"),
        metric("Total return", total_return, format="percent_fraction"),
        metric("Final cash", _numeric(row.get("final_cash")), format="amount"),
        metric("Final stock", _numeric(row.get("final_stock")), format="amount"),
        metric("Trades", _numeric(row.get("number_of_trades")), format="integer"),
        metric("Traded volume", _numeric(row.get("traded_volume")), format="amount"),
        metric(
            "Transaction costs paid",
            _numeric(row.get("cumulative_transaction_costs_paid")),
            format="amount",
        ),
        metric(
            "Average entry price",
            _numeric(row.get("average_entry_price")),
            format="price",
            source=SIMULATOR_SUMMARY_SOURCE,
        ),
    ]


def _trajectory(archive: RunArchive) -> dict[str, Any]:
    """Build his wealth path against the population, thinned for rendering.

    Thinned with the same ``stride_for`` cap the market charts use, so a long
    run does not ship one point per step to the browser. The stride is reported
    alongside the series: a reader looking at a thinned chart should be able to
    tell that is what they are looking at.
    """

    series = read_csv_if_exists(archive.protagonist_timeseries_csv)
    if series.empty or "simulation_step" not in series.columns:
        return {"available": False}

    stride = stride_for(len(series))
    sampled = series.iloc[::stride] if stride > 1 else series

    return {
        "available": True,
        "stride": stride,
        "downsampled": stride > 1,
        "step": series_values(sampled, "simulation_step"),
        "series": {
            key: series_values(sampled, column)
            for key, column in TRAJECTORY_SERIES
            if column in sampled.columns
        },
    }


def _numeric(value: Any) -> float | None:
    """Return one snapshot cell as a finite float, or ``None``."""

    numbers = finite_values(pd.Series([value]))
    return None if numbers.empty else float(numbers.iloc[0])


def _flag(value: Any) -> bool | None:
    """Return one 1/0 snapshot cell as a boolean, or ``None`` when absent."""

    number = _numeric(value)
    return None if number is None else bool(number)
