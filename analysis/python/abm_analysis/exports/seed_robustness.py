"""Cross-seed robustness tables for a replicated experiment.

An experiment whose runs differ only in the random seed answers one question:
are the headline results a property of the model, or of the draw? This module
writes the machine-readable answer — eight CSV files covering the per-run
diagnostics, the k-sample and pairwise distribution tests, per-seed stationarity,
seed-count convergence, and the pass/borderline/fail verdict table.

Nothing here computes a statistic of its own. Every table comes from
``abm_analysis.statistics``, the same functions the dashboard recomputes its
panels with, so a number quoted from a CSV and the same number read on screen
cannot disagree. What this module adds is the file layout and the run labelling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from abm_analysis.archive.data import build_runs_index, discover_run_directories
from abm_analysis.statistics.diagnostics import (
    build_pairwise_ks_table,
    build_return_series_by_run,
    build_stylised_fact_diagnostics,
)
from abm_analysis.statistics.robustness import build_seed_robustness_summary
from abm_analysis.statistics.robustness_tests import (
    build_adf_stationarity_table,
    build_cross_seed_distribution_tests,
    summarise_adf_rejections,
    summarise_pairwise_ks,
)
from abm_analysis.statistics.robustness_verdicts import build_robustness_verdicts
from abm_analysis.statistics.seed_convergence import build_seed_convergence_table

from .labels import add_pairwise_simulation_labels, add_simulation_labels


@dataclass(frozen=True)
class SeedRobustnessTables:
    """Paths written by one seed-robustness export."""

    output_dir: Path
    runs_index_csv_path: Path
    diagnostics_csv_path: Path
    pairwise_ks_csv_path: Path
    seed_robustness_csv_path: Path
    distribution_tests_csv_path: Path
    adf_stationarity_csv_path: Path
    seed_convergence_csv_path: Path
    verdicts_csv_path: Path


def write_seed_robustness_tables(
    experiment_dir: Path | str,
    *,
    output_dir: Path | str | None = None,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> SeedRobustnessTables:
    """Compute and write the cross-seed robustness tables for an experiment.

    Works on any archived experiment folder — the output of
    ``abm_analysis replicate``, or a calibration study's ``best_runs`` — without
    re-running the simulator.
    """

    experiment_path = Path(experiment_dir).expanduser().resolve()
    run_dirs = discover_run_directories(experiment_path)
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found under {experiment_path}")

    tables_dir = _robustness_output_dir(experiment_path, output_dir)
    tables_dir.mkdir(parents=True, exist_ok=True)

    runs_index = build_runs_index(experiment_path)
    diagnostics = build_stylised_fact_diagnostics(
        run_dirs,
        phase=phase,
        price_column=price_column,
    )
    return_series_by_run = build_return_series_by_run(
        run_dirs,
        phase=phase,
        price_column=price_column,
    )
    pairwise_ks = build_pairwise_ks_table(return_series_by_run)

    run_labels = _seed_run_labels(runs_index)
    seed_by_run = _seed_by_run(runs_index)
    seed_count = _distinct_seed_count(runs_index)

    seed_robustness = build_seed_robustness_summary(runs_index, diagnostics)
    ks_summary = summarise_pairwise_ks(pairwise_ks)
    distribution_tests = build_cross_seed_distribution_tests(return_series_by_run)
    adf_table = build_adf_stationarity_table(return_series_by_run, seed_by_run)
    adf_summary = summarise_adf_rejections(adf_table)
    convergence_table = build_seed_convergence_table(runs_index, diagnostics)
    verdicts = build_robustness_verdicts(
        seed_robustness,
        distribution_tests,
        ks_summary,
        adf_summary,
        convergence_table,
        seed_count=seed_count,
    )

    tables = SeedRobustnessTables(
        output_dir=tables_dir,
        runs_index_csv_path=tables_dir / "runs_index.csv",
        diagnostics_csv_path=tables_dir / "stylised_fact_diagnostics.csv",
        pairwise_ks_csv_path=tables_dir / "pairwise_ks_log_returns.csv",
        seed_robustness_csv_path=tables_dir / "seed_robustness_summary.csv",
        distribution_tests_csv_path=tables_dir / "cross_seed_distribution_tests.csv",
        adf_stationarity_csv_path=tables_dir / "adf_stationarity_by_seed.csv",
        seed_convergence_csv_path=tables_dir / "seed_convergence.csv",
        verdicts_csv_path=tables_dir / "robustness_verdicts.csv",
    )

    add_simulation_labels(runs_index, run_labels).to_csv(tables.runs_index_csv_path, index=False)
    add_simulation_labels(diagnostics, run_labels).to_csv(
        tables.diagnostics_csv_path, index=False
    )
    add_pairwise_simulation_labels(pairwise_ks, run_labels).to_csv(
        tables.pairwise_ks_csv_path, index=False
    )
    seed_robustness.to_csv(tables.seed_robustness_csv_path, index=False)
    distribution_tests.to_csv(tables.distribution_tests_csv_path, index=False)
    add_simulation_labels(adf_table, run_labels).to_csv(
        tables.adf_stationarity_csv_path, index=False
    )
    convergence_table.to_csv(tables.seed_convergence_csv_path, index=False)
    verdicts.to_csv(tables.verdicts_csv_path, index=False)

    return tables


def _robustness_output_dir(experiment_path: Path, output_dir: Path | str | None) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return experiment_path / "robustness_reports" / timestamp


def _seed_run_labels(runs_index: pd.DataFrame) -> dict[str, str]:
    """Label each run by its seed, the natural label for replicates.

    Falls back to the run identifier when the seed is unavailable so that
    labels never collapse to an empty string.
    """

    labels: dict[str, str] = {}
    if runs_index.empty or "run_id" not in runs_index.columns:
        return labels
    seeds = runs_index.get("seed")
    for position, run_id in enumerate(runs_index["run_id"].astype(str)):
        seed = seeds.iloc[position] if seeds is not None else None
        seed_number = pd.to_numeric(pd.Series([seed]), errors="coerce").iloc[0]
        if pd.isna(seed_number):
            labels[run_id] = run_id
        else:
            labels[run_id] = f"Seed {int(seed_number)}"
    return labels


def _seed_by_run(runs_index: pd.DataFrame) -> dict[str, object]:
    if runs_index.empty or not {"run_id", "seed"}.issubset(runs_index.columns):
        return {}
    return dict(zip(runs_index["run_id"].astype(str), runs_index["seed"], strict=True))


def _distinct_seed_count(runs_index: pd.DataFrame) -> int:
    if runs_index.empty:
        return 0
    if "seed" not in runs_index.columns:
        return int(len(runs_index))
    return int(pd.to_numeric(runs_index["seed"], errors="coerce").nunique())
