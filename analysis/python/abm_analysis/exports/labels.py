"""Simulation-label helpers for exported tables.

Reproducible run identifiers are long (``20260427143012_1_1_0_1_20_30_5_2_180_66``)
and carry the parameters in positional form, which is unreadable as a table key.
Every exported table therefore gains a leading human label column — "Seed 66"
for a replication batch — while keeping the raw ``run_id`` beside it so the row
stays joinable against the archive.
"""

from __future__ import annotations

import pandas as pd


def add_simulation_labels(data: pd.DataFrame, run_labels: dict[str, str]) -> pd.DataFrame:
    """Insert a leading ``simulation_label`` column keyed on ``run_id``."""

    if data.empty or "run_id" not in data.columns:
        return data
    labelled = data.copy()
    run_ids = labelled["run_id"].astype(str)
    labels = run_ids.map(run_labels).fillna(run_ids)
    labelled.insert(0, "simulation_label", labels)
    return labelled


def add_pairwise_simulation_labels(
    data: pd.DataFrame,
    run_labels: dict[str, str],
) -> pd.DataFrame:
    """Label both sides of a pairwise table, such as the K-S comparison grid."""

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
