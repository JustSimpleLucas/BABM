"""Agent-level aggregation of a run's end-of-run snapshot.

The market diagnostics next door describe the price series; this module
describes the traders who produced it. ``agents_final.csv`` holds one row per
agent, and the research question is asked of *groups* of agents rather than
individuals: a run of 1,000 noise traders and a run of 340 fundamentalists
against 300 chartists are different experiments, so outcomes are aggregated by
the strategy each agent was running when the simulation ended.

The strategy column is discovered rather than assumed. Archives written before
mid-course strategy switching recorded only ``initial_strategy_type``, so the
candidates are tried in order and a run with neither column aggregates to a
single population-wide row instead of failing.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from abm_analysis.archive.data import read_csv_if_exists, resolve_artifact_path


#: Snapshot columns naming an agent's strategy, most specific first. The first
#: one present in the frame is the one grouped on.
AGENT_STRATEGY_COLUMN_CANDIDATES = ("current_strategy_type", "initial_strategy_type")

#: Strategy families in display order. This is the stacking order of every
#: per-strategy chart and the slot order of the dashboard's strategy colours,
#: which were validated as an *ordered* set (neighbouring slots are the pairs
#: that touch), so it must never be re-sorted by population size.
STRATEGY_FAMILIES = ("fundamentalist", "chartist", "noise_trader", "buy_and_hold")

#: Snapshot columns summarised per group. Each contributes five output columns
#: (mean, median, std, min, max); columns absent from an archive are skipped
#: rather than filled, so a legacy run yields fewer columns, never NaN ones.
AGENT_SUMMARY_METRICS = [
    "final_wealth",
    "final_cash",
    "final_stock",
    "wealth_change",
    "number_of_trades",
    "traded_volume",
    "average_entry_price",
    "recent_peak_wealth",
    "last_prospect_reference_point",
]


def build_agent_summary_statistics(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Aggregate agent-level diagnostics by run and behavioural strategy."""

    agents = load_agent_snapshots(experiment_dir, run_ids, run_labels)
    if agents.empty:
        return pd.DataFrame()

    strategy_column = agent_strategy_column(agents)
    group_columns = ["simulation_label", "run_id"]
    if strategy_column is not None:
        group_columns.append(strategy_column)

    available_metrics = [column for column in AGENT_SUMMARY_METRICS if column in agents.columns]
    for column in available_metrics:
        agents[column] = pd.to_numeric(agents[column], errors="coerce")

    rows: list[dict[str, float | int | str]] = []
    for group_key, group in agents.groupby(group_columns, dropna=False):
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        row: dict[str, float | int | str] = {"agent_count": int(len(group))}
        for column, value in zip(group_columns, group_values, strict=True):
            row[column] = value

        for metric in available_metrics:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                continue
            row[f"{metric}_mean"] = float(values.mean())
            row[f"{metric}_median"] = float(values.median())
            row[f"{metric}_std"] = float(values.std(ddof=1)) if len(values) > 1 else 0.0
            row[f"{metric}_min"] = float(values.min())
            row[f"{metric}_max"] = float(values.max())

        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(group_columns).reset_index(drop=True)


def load_agent_snapshots(
    experiment_dir: Path,
    run_ids: list[str],
    run_labels: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Read and concatenate the end-of-run agent snapshots of several runs.

    ``wealth_change`` is derived here rather than read, because the simulator
    records start and end wealth but not the difference. Deriving it in one
    place is what lets the dashboard's column and this table mean the same
    thing.
    """

    frames = []
    for run_id in run_ids:
        agents = read_csv_if_exists(
            resolve_artifact_path(experiment_dir / run_id, "agents_final.csv")
        )
        if agents.empty:
            continue
        agents["run_id"] = run_id
        agents["simulation_label"] = _run_label(run_id, run_labels)
        if "initial_wealth" in agents.columns and "final_wealth" in agents.columns:
            agents["wealth_change"] = (
                pd.to_numeric(agents["final_wealth"], errors="coerce")
                - pd.to_numeric(agents["initial_wealth"], errors="coerce")
            )
        frames.append(agents)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def agent_strategy_column(agents: pd.DataFrame) -> str | None:
    """Return the snapshot's strategy column, or ``None`` if it records none."""

    for column in AGENT_STRATEGY_COLUMN_CANDIDATES:
        if column in agents.columns:
            return column
    return None


def strategy_family(strategy_label: object) -> str:
    """Collapse a recorded strategy label to the family it belongs to.

    The simulator names the chartist rule an agent runs — ``chartist_momentum``,
    ``chartist_mean_reversion``, ``chartist_breakout`` and so on — but the
    behavioural-finance question is asked of the family: do fundamentalists,
    trend-followers and noise traders push the price in different directions?
    Four colours can carry four families legibly; six cannot, so the dashboard
    groups by family by default and offers the variants as an opt-in split.

    A label outside the known families is returned unchanged rather than merged
    into one of them, so a strategy added to the model later appears as its own
    group instead of silently inflating a neighbour's numbers.
    """

    label = str(strategy_label).strip()
    if label == "chartist" or label.startswith("chartist_"):
        return "chartist"
    return label


def _run_label(run_id: str, run_labels: dict[str, str] | None = None) -> str:
    if run_labels is None:
        return str(run_id)
    return run_labels.get(str(run_id), str(run_id))
