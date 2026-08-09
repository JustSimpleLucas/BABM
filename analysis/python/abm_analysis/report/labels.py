"""Simulation-label helpers for report tables and chart notes."""

from __future__ import annotations

import pandas as pd

def _add_simulation_labels(data: pd.DataFrame, run_labels: dict[str, str]) -> pd.DataFrame:
    if data.empty or "run_id" not in data.columns:
        return data
    labelled = data.copy()
    run_ids = labelled["run_id"].astype(str)
    labels = run_ids.map(run_labels).fillna(run_ids)
    labelled.insert(0, "simulation_label", labels)
    return labelled

def _add_pairwise_simulation_labels(
    data: pd.DataFrame,
    run_labels: dict[str, str],
) -> pd.DataFrame:
    if data.empty or not {"run_id_a", "run_id_b"}.issubset(data.columns):
        return data
    labelled = data.copy()
    run_id_a = labelled["run_id_a"].astype(str)
    run_id_b = labelled["run_id_b"].astype(str)
    label_a = run_id_a.map(run_labels).fillna(run_id_a)
    label_b = run_id_b.map(run_labels).fillna(run_id_b)
    labelled.insert(0, "simulation_label_a", label_a)
    labelled.insert(1, "simulation_label_b", label_b)
    return labelled

def _simulation_label_table(runs_index: pd.DataFrame, run_labels: dict[str, str]) -> str:
    """Build the visible mapping from short chart labels to simulation data."""

    if runs_index.empty or "run_id" not in runs_index.columns:
        return ""

    rows = []
    for data_index, (_, row) in enumerate(runs_index.iterrows(), start=1):
        run_id = str(row["run_id"])
        rows.append(
            {
                "chart_label": run_labels.get(run_id, f"Data {data_index}"),
                "folder_name": row.get("run_directory", run_id),
                "run_label": row.get("run_label", ""),
                "created_at_local": row.get("created_at_local", ""),
                "seed": row.get("seed", ""),
                "num_fundamentalists": row.get("num_fundamentalists", ""),
                "num_chartists": row.get("num_chartists", ""),
                "num_noise_traders": row.get("num_noise_traders", ""),
                "num_buy_and_hold_agents": row.get("num_buy_and_hold_agents", ""),
                "time_steps": row.get("time_steps", ""),
            }
        )

    return pd.DataFrame(rows).to_html(
        index=False,
        border=0,
        classes=["data-table"],
        na_rep="",
        escape=True,
    )
