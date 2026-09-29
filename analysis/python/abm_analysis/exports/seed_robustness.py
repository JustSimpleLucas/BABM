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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from abm_analysis.archive.data import (
    build_runs_index_from_run_dirs,
    discover_run_directories,
)
from abm_analysis.statistics.diagnostics import (
    build_asset_stylised_fact_diagnostics,
    build_pairwise_ks_table,
    build_return_series_by_asset,
    build_return_series_by_run,
    build_stylised_fact_diagnostics,
)
from abm_analysis.statistics.multi_asset import asset_series_id
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


@dataclass(frozen=True)
class SeedRobustnessFrames:
    """The computed tables of one seed-robustness pass, before they are written.

    Splitting the frames out of :func:`write_seed_robustness_tables` is what
    lets the dashboard show cross-seed evidence without a second implementation:
    the CSV export and the cohort panel are handed the *same* objects, so a
    number quoted from a file and the same number read on screen cannot drift
    apart.
    """

    runs_index: pd.DataFrame
    diagnostics: pd.DataFrame
    pairwise_ks: pd.DataFrame
    seed_robustness: pd.DataFrame
    distribution_tests: pd.DataFrame
    adf_stationarity: pd.DataFrame
    seed_convergence: pd.DataFrame
    verdicts: pd.DataFrame
    return_series: dict[str, pd.Series]
    run_labels: dict[str, str]
    seed_count: int
    per_asset: bool


def build_seed_robustness_frames(
    run_dirs: Sequence[Path],
    *,
    phase: str = "simulation",
    price_column: str = "market_price",
    manifest_dir: Path | str | None = None,
    per_asset: bool = False,
    diagnostics: pd.DataFrame | None = None,
    return_series: dict[str, pd.Series] | None = None,
) -> SeedRobustnessFrames:
    """Compute every cross-seed table for a set of runs, writing nothing.

    Args:
        run_dirs: The archived runs forming the cohort. They need not share a
            parent directory.
        phase: Step phase analysed, as elsewhere in the analysis layer.
        price_column: Price column log returns are computed from. Ignored by the
            per-asset diagnostics, which use the simulator's own ``log_return``
            column — see the caveat in ``README`` §5.1.
        manifest_dir: Directory whose ``experiment_manifest.csv`` supplements the
            runs index, or ``None`` when the cohort spans folders.
        per_asset: Diagnose each traded market separately rather than the
            primary asset's projection. The dashboard sets this so a cohort
            panel keeps the one-column-per-market shape of the single-run view;
            the CSV export leaves it off so its files keep their current schema.
        diagnostics: Already-computed stylised-fact rows for exactly these runs.
            The dashboard memoises them per run — each carries a GARCH(1,1) fit,
            and a cohort re-requested with one more run selected would otherwise
            refit every run it already had. Supplying them is a promise that they
            were produced with this ``phase``, ``price_column`` and ``per_asset``;
            nothing here re-derives or checks them.
        return_series: Already-computed log-return series, keyed as
            ``build_return_series_by_asset`` keys them when ``per_asset`` is set
            and by run id otherwise. Memoised by the same caller for the same
            reason.

    Returns:
        Every frame the export writes, plus the seed labelling used for them.
    """

    directories = [Path(run_dir).expanduser().resolve() for run_dir in run_dirs]
    runs_index = build_runs_index_from_run_dirs(directories, manifest_dir=manifest_dir)

    if diagnostics is None:
        diagnostics = (
            build_asset_stylised_fact_diagnostics(
                directories,
                phase=phase,
                price_column=price_column,
            )
            if per_asset
            else build_stylised_fact_diagnostics(
                directories,
                phase=phase,
                price_column=price_column,
            )
        )
    if return_series is None:
        return_series = (
            build_return_series_by_asset(
                directories,
                phase=phase,
                price_column=price_column,
            )
            if per_asset
            else build_return_series_by_run(
                directories,
                phase=phase,
                price_column=price_column,
            )
        )

    run_labels = _seed_run_labels(runs_index)
    seed_by_run = _seed_by_series(runs_index, diagnostics, per_asset=per_asset)
    seed_count = _distinct_seed_count(runs_index)

    pairwise_ks = build_pairwise_ks_table(return_series)
    seed_robustness = build_seed_robustness_summary(runs_index, diagnostics)
    ks_summary = summarise_pairwise_ks(pairwise_ks)
    distribution_tests = build_cross_seed_distribution_tests(return_series)
    adf_table = build_adf_stationarity_table(return_series, seed_by_run)
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

    return SeedRobustnessFrames(
        runs_index=runs_index,
        diagnostics=diagnostics,
        pairwise_ks=pairwise_ks,
        seed_robustness=seed_robustness,
        distribution_tests=distribution_tests,
        adf_stationarity=adf_table,
        seed_convergence=convergence_table,
        verdicts=verdicts,
        return_series=return_series,
        run_labels=run_labels,
        seed_count=seed_count,
        per_asset=per_asset,
    )


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

    frames = build_seed_robustness_frames(
        run_dirs,
        phase=phase,
        price_column=price_column,
        manifest_dir=experiment_path,
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

    labels = frames.run_labels
    add_simulation_labels(frames.runs_index, labels).to_csv(
        tables.runs_index_csv_path, index=False
    )
    add_simulation_labels(frames.diagnostics, labels).to_csv(
        tables.diagnostics_csv_path, index=False
    )
    add_pairwise_simulation_labels(frames.pairwise_ks, labels).to_csv(
        tables.pairwise_ks_csv_path, index=False
    )
    frames.seed_robustness.to_csv(tables.seed_robustness_csv_path, index=False)
    frames.distribution_tests.to_csv(tables.distribution_tests_csv_path, index=False)
    add_simulation_labels(frames.adf_stationarity, labels).to_csv(
        tables.adf_stationarity_csv_path, index=False
    )
    frames.seed_convergence.to_csv(tables.seed_convergence_csv_path, index=False)
    frames.verdicts.to_csv(tables.verdicts_csv_path, index=False)

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


def _seed_by_series(
    runs_index: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    per_asset: bool,
) -> dict[str, object]:
    """Map every return-series key to the seed of the run that produced it.

    In per-asset mode the series are keyed by ``asset_series_id(run, asset)``
    rather than by run, so run-id keys alone would leave the ADF table's seed
    column empty. The composite keys are rebuilt from the diagnostics frame,
    which carries the run and asset of every series, rather than guessed from
    the key text. Plain run-id keys are kept too: a run archived before the
    multi-asset extension falls back to one, and both forms can appear in the
    same cohort.
    """

    if runs_index.empty or not {"run_id", "seed"}.issubset(runs_index.columns):
        return {}
    by_run = dict(zip(runs_index["run_id"].astype(str), runs_index["seed"], strict=True))
    if not per_asset or diagnostics.empty or "asset" not in diagnostics.columns:
        return by_run

    resolved: dict[str, object] = dict(by_run)
    for _, row in diagnostics.iterrows():
        run_id = str(row.get("run_id", ""))
        asset = str(row.get("asset", "") or "").strip()
        if not run_id or not asset or run_id not in by_run:
            continue
        resolved[asset_series_id(run_id, asset)] = by_run[run_id]
    return resolved


def _distinct_seed_count(runs_index: pd.DataFrame) -> int:
    if runs_index.empty:
        return 0
    if "seed" not in runs_index.columns:
        return int(len(runs_index))
    return int(pd.to_numeric(runs_index["seed"], errors="coerce").nunique())
