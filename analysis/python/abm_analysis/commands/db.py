"""PostgreSQL command group: parser and handlers for every db subcommand."""

from __future__ import annotations

import argparse
from pathlib import Path
from abm_analysis.archive.benchmarks import default_benchmark_dir
from .shared_arguments import add_database_arguments
from .shared_helpers import print_import_summaries
from abm_analysis.database import import_all_data
from abm_analysis.database import import_benchmark_directory
from abm_analysis.database import import_experiment_archives
from abm_analysis.database import import_run_archive
from abm_analysis.database import initialise_database
from abm_analysis.database import inspect_database_run
from abm_analysis.database import validate_database_imports


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``db`` command."""

    db_parser = subparsers.add_parser(
        "db",
        help="Initialise PostgreSQL and import ABM experiment data.",
    )
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)

    db_init = db_subparsers.add_parser("init", help="Create or update the PostgreSQL schema.")
    add_database_arguments(db_init)
    db_init.set_defaults(handler=handle_db_init)

    db_import_run = db_subparsers.add_parser(
        "import-run",
        help="Import one staged run directory into PostgreSQL.",
    )
    db_import_run.add_argument("run_dir", type=Path, help="Path to one staged run directory.")
    db_import_run.add_argument(
        "--prune-source",
        action="store_true",
        help="Delete staging CSV/JSON/log artefacts after a successful import.",
    )
    add_database_arguments(db_import_run)
    db_import_run.set_defaults(handler=handle_db_import_run)

    db_import_experiment = db_subparsers.add_parser(
        "import-experiment",
        help="Import every run under one experiment directory.",
    )
    db_import_experiment.add_argument(
        "experiment_dir",
        type=Path,
        help="Path to data/experiments/<experiment_name>.",
    )
    db_import_experiment.add_argument(
        "--prune-source",
        action="store_true",
        help="Delete staging CSV/JSON/log artefacts after successful per-run imports.",
    )
    add_database_arguments(db_import_experiment)
    db_import_experiment.set_defaults(handler=handle_db_import_experiment)

    db_import_benchmarks = db_subparsers.add_parser(
        "import-benchmarks",
        help="Import empirical benchmark CSVs into PostgreSQL.",
    )
    db_import_benchmarks.add_argument(
        "--benchmark-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing empirical benchmark CSVs. Defaults to the "
            "repository-local data/stock_data/candle_chart directory."
        ),
    )
    db_import_benchmarks.add_argument(
        "--benchmark-series",
        default=None,
        help="Comma-separated benchmark IDs to include, for example SPX,NAQ.",
    )
    add_database_arguments(db_import_benchmarks)
    db_import_benchmarks.set_defaults(handler=handle_db_import_benchmarks)

    db_import_all = db_subparsers.add_parser(
        "import-all",
        help="Import all experiment runs and empirical benchmark CSVs.",
    )
    db_import_all.add_argument(
        "--experiments-root",
        type=Path,
        default=Path("data/experiments"),
        help="Root containing experiment directories.",
    )
    db_import_all.add_argument(
        "--benchmark-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing empirical benchmark CSVs. Defaults to the "
            "repository-local data/stock_data/candle_chart directory when present."
        ),
    )
    db_import_all.add_argument(
        "--benchmark-series",
        default=None,
        help="Comma-separated benchmark IDs to include, for example SPX,NAQ.",
    )
    db_import_all.add_argument(
        "--prune-source",
        action="store_true",
        help="Delete staging CSV/JSON/log artefacts after successful run imports.",
    )
    add_database_arguments(db_import_all)
    db_import_all.set_defaults(handler=handle_db_import_all)

    db_validate = db_subparsers.add_parser(
        "validate",
        help="Compare source CSV row counts with PostgreSQL row counts.",
    )
    db_validate.add_argument(
        "--experiments-root",
        type=Path,
        default=Path("data/experiments"),
        help="Root containing experiment directories.",
    )
    db_validate.add_argument(
        "--benchmark-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing empirical benchmark CSVs. Defaults to the "
            "repository-local data/stock_data/candle_chart directory when present."
        ),
    )
    db_validate.add_argument(
        "--benchmark-series",
        default=None,
        help="Comma-separated benchmark IDs to include, for example SPX,NAQ.",
    )
    add_database_arguments(db_validate)
    db_validate.set_defaults(handler=handle_db_validate)

    db_inspect_run = db_subparsers.add_parser(
        "inspect-run",
        help="Show provenance, row counts, and import metadata for one SQL run.",
    )
    db_inspect_run.add_argument("run_id", type=str, help="Run ID imported into PostgreSQL.")
    add_database_arguments(db_inspect_run)
    db_inspect_run.set_defaults(handler=handle_db_inspect_run)


def handle_db_init(args: argparse.Namespace) -> int:
    """Initialise or migrate the PostgreSQL analysis schema."""

    initialise_database(args.database_url, database_url_env=args.database_url_env)
    print("PostgreSQL schema is ready.")
    return 0

def handle_db_import_run(args: argparse.Namespace) -> int:
    """Import one staged simulator run archive into PostgreSQL."""

    summary = import_run_archive(
        args.run_dir,
        args.database_url,
        database_url_env=args.database_url_env,
        prune_source=args.prune_source,
    )
    print(f"Imported {summary.item_type} {summary.identifier}: {summary.rows_imported} rows")
    return 0

def handle_db_import_experiment(args: argparse.Namespace) -> int:
    """Import every run archive under one experiment directory."""

    summaries = import_experiment_archives(
        args.experiment_dir,
        args.database_url,
        database_url_env=args.database_url_env,
        prune_source=args.prune_source,
    )
    print_import_summaries(summaries)
    return 0

def handle_db_import_benchmarks(args: argparse.Namespace) -> int:
    """Import selected empirical benchmark series into PostgreSQL."""

    benchmark_dir = args.benchmark_dir or default_benchmark_dir()
    summaries = import_benchmark_directory(
        benchmark_dir,
        args.database_url,
        database_url_env=args.database_url_env,
        benchmark_series=args.benchmark_series,
    )
    print_import_summaries(summaries)
    return 0

def handle_db_import_all(args: argparse.Namespace) -> int:
    """Import all experiment archives and selected benchmark series."""

    benchmark_dir = args.benchmark_dir
    if benchmark_dir is None:
        candidate = default_benchmark_dir()
        benchmark_dir = candidate if candidate.is_dir() else None
    summaries = import_all_data(
        args.experiments_root,
        benchmark_dir,
        args.database_url,
        database_url_env=args.database_url_env,
        benchmark_series=args.benchmark_series,
        prune_source=args.prune_source,
    )
    print_import_summaries(summaries)
    return 0

def handle_db_validate(args: argparse.Namespace) -> int:
    """Compare source archive row counts against imported PostgreSQL row counts."""

    benchmark_dir = args.benchmark_dir
    if benchmark_dir is None:
        candidate = default_benchmark_dir()
        benchmark_dir = candidate if candidate.is_dir() else None
    validation = validate_database_imports(
        args.database_url,
        database_url_env=args.database_url_env,
        experiments_root=args.experiments_root,
        benchmark_dir=benchmark_dir,
        benchmark_series=args.benchmark_series,
    )
    if validation.empty:
        print("No source data was found to validate.")
        return 0
    print(validation.to_string(index=False))
    return 0 if (validation["status"] == "matched").all() else 1

def handle_db_inspect_run(args: argparse.Namespace) -> int:
    """Print provenance and row-count diagnostics for one imported SQL run."""

    inspection = inspect_database_run(
        args.run_id,
        args.database_url,
        database_url_env=args.database_url_env,
    )
    run = inspection["run"]
    audit = inspection["latest_import_audit"]
    row_counts = inspection["row_counts"]
    benchmarks = inspection["available_benchmarks"]

    print(f"Run ID: {run['run_id']}")
    print(f"Experiment: {run['experiment_name']}")
    print(f"Run label: {run.get('run_label') or ''}")
    print(f"Status: {run.get('status') or ''}")
    print(f"Created at local: {run.get('created_at_local') or ''}")
    print(f"Config hash: {run.get('config_hash') or ''}")
    print(f"Source archive SHA-256: {run.get('source_archive_sha256') or ''}")
    print(f"Database schema version: {inspection['schema_version']}")
    if audit:
        print(f"Rows imported: {audit.get('rows_imported') or 0}")
        print(f"Importer version: {audit.get('importer_version') or ''}")
        print(f"Importer git commit: {audit.get('git_commit') or ''}")
        print(f"Import status: {audit.get('status') or ''}")
        print(f"Import message: {audit.get('message') or ''}")
    print("Row counts:")
    for table_name, count in row_counts.items():
        print(f"  {table_name}: {count}")
    print(
        "Available benchmark metadata: "
        + (", ".join(benchmarks) if benchmarks else "none")
    )
    return 0
