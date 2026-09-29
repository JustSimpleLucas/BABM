"""Experiment manifest and run-index handling for ABM archive reports."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from abm_analysis.archive.archives import build_run_archive, discover_run_directories
from abm_analysis.archive.run_ids import parse_run_id
from abm_analysis.archive.timeseries import read_csv_if_exists


def normalise_manifest_schema(manifest_data: pd.DataFrame) -> pd.DataFrame:
    """Normalise historical and current manifest column names.

    Earlier exports used shorter flag names. Current C++ exports use explicit
    ``control_*`` fields. The comparison workflow exposes the current names
    while preserving any additional columns for traceability.
    """

    if manifest_data.empty:
        return manifest_data

    normalised = manifest_data.copy()
    rename_map = {
        "prospect_theory_enabled": "control_prospect_theory_enabled",
        "prospect_heterogeneity_enabled": "control_prospect_heterogeneity_enabled",
        "short_sale": "short_selling_enabled",
    }
    for old_name, new_name in rename_map.items():
        if old_name in normalised.columns and new_name not in normalised.columns:
            normalised[new_name] = normalised[old_name]

    for column in [
        "control_prospect_theory_enabled",
        "control_prospect_theory_agent_fraction",
        "control_prospect_heterogeneity_enabled",
        "social_enabled",
        "short_selling_enabled",
        "num_noise_traders",
        "num_buy_and_hold_agents",
        "buy_hold_target_risky_weight",
    ]:
        if column not in normalised.columns:
            normalised[column] = pd.NA

    if "run_id" in normalised.columns:
        run_id_frame = pd.DataFrame([parse_run_id(str(run_id)) for run_id in normalised["run_id"]])
        for source_column, target_column in [
            ("run_id_prospect_theory_enabled", "control_prospect_theory_enabled"),
            ("run_id_prospect_heterogeneity_enabled", "control_prospect_heterogeneity_enabled"),
            ("run_id_social_enabled", "social_enabled"),
            ("run_id_short_selling_enabled", "short_selling_enabled"),
            ("run_id_num_noise_traders", "num_noise_traders"),
            ("run_id_num_buy_and_hold_agents", "num_buy_and_hold_agents"),
        ]:
            missing = normalised[target_column].isna().to_numpy()
            if not missing.any() or source_column not in run_id_frame.columns:
                continue
            normalised.loc[missing, target_column] = run_id_frame.loc[
                missing,
                source_column,
            ].to_numpy()

    return normalised.drop(columns=[c for c in rename_map if c in normalised.columns])


def read_experiment_manifest(experiment_dir: Path | str) -> pd.DataFrame:
    """Read and normalise ``experiment_manifest.csv`` when available."""

    manifest_path = Path(experiment_dir).expanduser().resolve() / "experiment_manifest.csv"
    if not manifest_path.is_file():
        return pd.DataFrame()
    return normalise_manifest_schema(pd.read_csv(manifest_path))


def build_runs_index(experiment_dir: Path | str) -> pd.DataFrame:
    """Build the experiment-level index used by reports and CSV exports."""

    experiment_path = Path(experiment_dir).expanduser().resolve()
    return build_runs_index_from_run_dirs(
        discover_run_directories(experiment_path),
        manifest_dir=experiment_path,
    )


def build_runs_index_from_run_dirs(
    run_dirs: Sequence[Path | str],
    *,
    manifest_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Build a runs index for an explicit set of run directories.

    ``build_runs_index`` covers the common case of one experiment folder. This
    variant exists because a comparison cohort is chosen run by run and may span
    several folders — an experiment alongside a calibration study's
    ``best_runs`` — so there is no single directory to discover from.

    Args:
        run_dirs: Archived run directories, in the order they should be indexed.
        manifest_dir: Directory whose ``experiment_manifest.csv`` supplements the
            per-run summaries. ``None`` when the runs span folders and no single
            manifest describes them all; the index is then built from each run's
            own ``summary_metrics.csv`` and its parsed run-id.
    """

    run_archives = [build_run_archive(run_dir) for run_dir in run_dirs]
    manifest = pd.DataFrame() if manifest_dir is None else read_experiment_manifest(manifest_dir)

    if not run_archives:
        return pd.DataFrame()

    summary_rows: list[pd.Series] = []
    for archive in run_archives:
        summary = read_csv_if_exists(archive.summary_metrics_csv)
        if summary.empty:
            row = pd.Series({"run_id": archive.run_id})
        else:
            row = summary.iloc[0].copy()
            row["run_id"] = _summary_run_id_or_directory(row, archive.run_id)
        row["run_directory"] = archive.run_id
        summary_rows.append(row)

    summaries = pd.DataFrame(summary_rows).reset_index(drop=True)
    summaries = normalise_manifest_schema(summaries)

    parsed_ids = pd.DataFrame([parse_run_id(archive.run_id) for archive in run_archives])
    runs_index = parsed_ids.merge(summaries, on="run_id", how="left", suffixes=("", "_summary"))

    if not manifest.empty and "run_id" in manifest.columns:
        manifest_columns = [column for column in manifest.columns if column != "run_id"]
        runs_index = runs_index.merge(
            manifest[["run_id", *manifest_columns]],
            on="run_id",
            how="left",
            suffixes=("", "_manifest"),
        )
        runs_index = _coalesce_duplicate_columns(runs_index)

    return _order_runs_index_columns(runs_index)


def _summary_run_id_or_directory(summary_row: pd.Series, directory_name: str) -> str:
    """Return a usable run identifier for index joins.

    ``data/latest`` is a convenience output directory rather than a numeric
    archive run-id, so its summary CSV can contain a blank run_id. The analysis
    index should still join those metrics by the directory that was actually
    discovered.
    """

    value = summary_row.get("run_id", directory_name)
    if pd.isna(value) or str(value).strip() == "":
        return directory_name
    return str(value)


def _coalesce_duplicate_columns(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    duplicate_suffixes = ["_summary", "_manifest"]
    for column in list(result.columns):
        for suffix in duplicate_suffixes:
            if column.endswith(suffix):
                base_column = column[: -len(suffix)]
                if base_column in result.columns:
                    result[base_column] = result[base_column].combine_first(result[column])
                    result = result.drop(columns=[column])
    return result


def _order_runs_index_columns(runs_index: pd.DataFrame) -> pd.DataFrame:
    preferred_columns = [
        "run_id",
        "experiment_name",
        "run_label",
        "created_at_local",
        "status",
        "seed",
        "time_steps",
        "warmup_steps",
        "fundamental_shock_std_dev",
        "fundamental_drift_per_step",
        "minimum_fundamental_value",
        "num_fundamentalists",
        "num_chartists",
        "num_noise_traders",
        "num_buy_and_hold_agents",
        "buy_hold_target_risky_weight",
        "control_prospect_theory_enabled",
        "control_prospect_theory_agent_fraction",
        "control_prospect_heterogeneity_enabled",
        "social_enabled",
        "short_selling_enabled",
        "final_market_price",
        "final_fundamental_price",
        "final_wealth_gini_coefficient",
        "total_traded_volume",
        "mean_allocative_efficiency",
        "allocative_efficiency_observations",
        "mean_log_return",
        "log_return_std_dev",
        "excess_kurtosis",
        "max_drawdown",
        "lag1_return_autocorrelation",
        "lag1_abs_return_autocorrelation",
        "lag1_squared_return_autocorrelation",
        "run_directory",
    ]
    ordered_columns = [
        *[column for column in preferred_columns if column in runs_index.columns],
        *[column for column in runs_index.columns if column not in preferred_columns],
    ]
    return runs_index[ordered_columns]
