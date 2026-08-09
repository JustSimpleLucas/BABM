"""Command-line entry point for Python-only ABM experiment analysis."""

from __future__ import annotations

from abm_analysis.benchmarks import default_benchmark_dir
from abm_analysis.calibration import (
    CalibrationOptions,
    default_calibration_output_dir,
    parse_seed_list,
    run_calibration,
)
from abm_analysis.database import (
    DEFAULT_DATABASE_URL_ENV,
    import_all_data,
    import_benchmark_directory,
    import_experiment_archives,
    import_run_archive,
    inspect_database_run,
    initialise_database,
    validate_database_imports,
)
from abm_analysis.replication import (
    SeedReplicationOptions,
    SeedReplicationResult,
    parse_seed_spec,
    run_seed_replication,
)
from abm_analysis.report import (
    build_comparison_report,
    build_run_report,
    build_seed_robustness_report,
)

from .cli_handlers import (
    _print_import_summaries,
    _print_optional_outputs,
    _resolve_benchmark_dir,
    _timestamped_calibration_name,
)
from .cli_parser import (
    _add_benchmark_arguments,
    _add_calibration_benchmark_arguments,
    _add_database_arguments,
    _add_source_arguments,
    build_parser,
)


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the selected command handler."""

    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


_build_parser = build_parser


__all__ = [
    "_add_benchmark_arguments",
    "_add_calibration_benchmark_arguments",
    "_add_database_arguments",
    "_add_source_arguments",
    "_build_parser",
    "_print_import_summaries",
    "_print_optional_outputs",
    "_resolve_benchmark_dir",
    "_timestamped_calibration_name",
    "CalibrationOptions",
    "DEFAULT_DATABASE_URL_ENV",
    "SeedReplicationOptions",
    "SeedReplicationResult",
    "build_parser",
    "build_comparison_report",
    "build_run_report",
    "build_seed_robustness_report",
    "default_benchmark_dir",
    "default_calibration_output_dir",
    "import_all_data",
    "import_benchmark_directory",
    "import_experiment_archives",
    "import_run_archive",
    "initialise_database",
    "inspect_database_run",
    "main",
    "parse_seed_list",
    "parse_seed_spec",
    "run_calibration",
    "run_seed_replication",
    "validate_database_imports",
]
