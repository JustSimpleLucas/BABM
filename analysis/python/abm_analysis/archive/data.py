"""Compatibility facade for ABM archive data loading and normalisation."""

from __future__ import annotations

from abm_analysis.archive.archives import (
    COMPRESSED_ARTIFACT_SUFFIX,
    REQUIRED_AGENT_FINAL_COLUMNS,
    REQUIRED_ASSET_TIMESERIES_COLUMNS,
    REQUIRED_STEP_TIMESERIES_COLUMNS,
    REQUIRED_SUMMARY_METRICS_COLUMNS,
    REQUIRED_TRADE_LEDGER_COLUMNS,
    ArchiveValidationResult,
    RunArchive,
    _missing_column_messages,
    _read_output_flag,
    build_run_archive,
    discover_run_directories,
    ensure_valid_run_archive,
    resolve_artifact_path,
    validate_run_archive,
)
from abm_analysis.archive.manifests import (
    _coalesce_duplicate_columns,
    _order_runs_index_columns,
    build_runs_index,
    normalise_manifest_schema,
    read_experiment_manifest,
)
from abm_analysis.archive.run_ids import (
    LEGACY_RUN_ID_FIELDS,
    PRE_BUY_HOLD_RUN_ID_FIELDS,
    RUN_ID_FIELDS,
    parse_run_id,
)
from abm_analysis.archive.timeseries import (
    PRICE_COLUMN_CANDIDATES,
    compute_log_returns,
    load_step_timeseries,
    prepare_return_series,
    read_csv_if_exists,
    select_price_column,
)


__all__ = [
    "ArchiveValidationResult",
    "COMPRESSED_ARTIFACT_SUFFIX",
    "LEGACY_RUN_ID_FIELDS",
    "PRE_BUY_HOLD_RUN_ID_FIELDS",
    "PRICE_COLUMN_CANDIDATES",
    "REQUIRED_AGENT_FINAL_COLUMNS",
    "REQUIRED_ASSET_TIMESERIES_COLUMNS",
    "REQUIRED_STEP_TIMESERIES_COLUMNS",
    "REQUIRED_SUMMARY_METRICS_COLUMNS",
    "REQUIRED_TRADE_LEDGER_COLUMNS",
    "RUN_ID_FIELDS",
    "RunArchive",
    "_coalesce_duplicate_columns",
    "_missing_column_messages",
    "_order_runs_index_columns",
    "_read_output_flag",
    "build_run_archive",
    "build_runs_index",
    "compute_log_returns",
    "discover_run_directories",
    "ensure_valid_run_archive",
    "load_step_timeseries",
    "normalise_manifest_schema",
    "parse_run_id",
    "prepare_return_series",
    "read_csv_if_exists",
    "read_experiment_manifest",
    "resolve_artifact_path",
    "select_price_column",
    "validate_run_archive",
]
