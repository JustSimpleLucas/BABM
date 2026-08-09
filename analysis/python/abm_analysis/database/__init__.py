"""PostgreSQL storage and import workflow for ABM experiment data.

The C++ simulator remains the deterministic model engine. This package treats
simulator CSV and JSON outputs as staging artefacts and imports them into
PostgreSQL so experiment comparison, calibration audit, and thesis reporting can
query one reproducible data store.
"""

from __future__ import annotations

from .constants import (
    AGENT_SNAPSHOT_COLUMNS,
    AGENT_STEP_DIAGNOSTIC_COLUMNS,
    BENCHMARK_METADATA_COLUMNS,
    BENCHMARK_METADATA_REQUIRED_FIELDS,
    ASSET_TIMESERIES_COLUMNS,
    BENCHMARK_PRICE_COLUMNS,
    BOOLEAN_TABLE_COLUMNS,
    CURRENT_SCHEMA_VERSION,
    DEFAULT_DATABASE_URL_ENV,
    IMPORTER_PACKAGE_NAME,
    JSONB_TABLE_COLUMNS,
    MECHANISM_DIAGNOSTIC_COLUMNS,
    PATH_LIKE_CONFIG_KEYS,
    PATH_LIKE_METADATA_KEYS,
    REQUIRED_SCHEMA_INDEXES,
    SCHEMA_TABLE_NAMES,
    STAGING_ARTIFACTS,
    STEP_TIMESERIES_COLUMNS,
    STYLISED_FACT_COLUMNS,
    SUMMARY_METRIC_COLUMNS,
    TRADE_LEDGER_COLUMNS,
    UNKNOWN_IMPORTER_VERSION,
)
from .exports import (
    build_runs_index_from_database,
    export_benchmarks_from_database,
    export_experiment_archive_from_database,
    export_run_archive_from_database,
    load_step_timeseries_from_database,
)
from .imports import (
    _build_benchmark_metadata_record,
    build_run_import_tables,
    import_all_data,
    import_benchmark_directory,
    import_experiment_archives,
    import_run_archive,
    prune_staging_artifacts,
)
from .inspection import inspect_database_run
from .models import ImportSummary
from .normalisation import sanitize_metadata_for_database
from .schema import (
    apply_schema,
    migration_001_initial_sql_statements,
    migration_002_indexes_and_metadata_sql_statements,
    schema_migrations,
    schema_sql_statements,
)
from .sql import create_database_engine, initialise_database, resolve_database_url
from .validation import _missing_benchmark_metadata_fields, validate_database_imports

__all__ = [
    "AGENT_SNAPSHOT_COLUMNS",
    "AGENT_STEP_DIAGNOSTIC_COLUMNS",
    "BENCHMARK_METADATA_COLUMNS",
    "BENCHMARK_METADATA_REQUIRED_FIELDS",
    "ASSET_TIMESERIES_COLUMNS",
    "BENCHMARK_PRICE_COLUMNS",
    "BOOLEAN_TABLE_COLUMNS",
    "CURRENT_SCHEMA_VERSION",
    "DEFAULT_DATABASE_URL_ENV",
    "IMPORTER_PACKAGE_NAME",
    "ImportSummary",
    "JSONB_TABLE_COLUMNS",
    "MECHANISM_DIAGNOSTIC_COLUMNS",
    "PATH_LIKE_CONFIG_KEYS",
    "PATH_LIKE_METADATA_KEYS",
    "REQUIRED_SCHEMA_INDEXES",
    "SCHEMA_TABLE_NAMES",
    "STAGING_ARTIFACTS",
    "STEP_TIMESERIES_COLUMNS",
    "STYLISED_FACT_COLUMNS",
    "SUMMARY_METRIC_COLUMNS",
    "TRADE_LEDGER_COLUMNS",
    "UNKNOWN_IMPORTER_VERSION",
    "_build_benchmark_metadata_record",
    "_missing_benchmark_metadata_fields",
    "apply_schema",
    "build_run_import_tables",
    "build_runs_index_from_database",
    "create_database_engine",
    "export_benchmarks_from_database",
    "export_experiment_archive_from_database",
    "export_run_archive_from_database",
    "import_all_data",
    "import_benchmark_directory",
    "import_experiment_archives",
    "import_run_archive",
    "initialise_database",
    "inspect_database_run",
    "load_step_timeseries_from_database",
    "migration_001_initial_sql_statements",
    "migration_002_indexes_and_metadata_sql_statements",
    "prune_staging_artifacts",
    "resolve_database_url",
    "sanitize_metadata_for_database",
    "schema_migrations",
    "schema_sql_statements",
    "validate_database_imports",
]
