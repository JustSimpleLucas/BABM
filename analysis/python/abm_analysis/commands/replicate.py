"""Seed-replication command: parser and handler."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from ..cli_arguments import _figure_formats_argument
from ..cli_handlers import _run_seed_replication_from_public_cli
from abm_analysis.report.static_export import STATIC_EXPORT_FORMATS
from abm_analysis.replication import SeedReplicationOptions
from abm_analysis.replication import parse_seed_spec


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``replicate`` command."""

    replicate_parser = subparsers.add_parser(
        "replicate",
        help="Run one fixed simulation config across deterministic random seeds.",
    )
    replicate_parser.add_argument(
        "--base-config",
        type=Path,
        default=Path("config/simulation.cfg"),
        help="Base key=value simulation config used as the replication template.",
    )
    replicate_parser.add_argument(
        "--simulator",
        type=Path,
        default=Path("build/release/simulate"),
        help=(
            "Path to the compiled C++ simulator executable. Defaults to the "
            "optimised release build; build it with 'cmake --preset release "
            "&& cmake --build --preset release'."
        ),
    )
    replicate_parser.add_argument(
        "--seeds",
        default="1:30",
        help="Comma-separated seeds or inclusive ranges, for example 1:30 or 55,66,77.",
    )
    replicate_parser.add_argument(
        "--experiment-name",
        default=None,
        help="Experiment folder name. Defaults to seed_robustness_<YYYYMMDDHHMMSS>.",
    )
    replicate_parser.add_argument(
        "--experiment-root",
        type=Path,
        default=None,
        help="Root directory for experiment archives. Defaults to repository data/experiments.",
    )
    replicate_parser.add_argument(
        "--phase",
        default="simulation",
        help="Phase used for return diagnostics.",
    )
    replicate_parser.add_argument(
        "--price-column",
        default="market_price",
        help="Price column used to compute simulated log returns.",
    )
    replicate_parser.add_argument(
        "--max-runs",
        type=int,
        default=8,
        help="Maximum number of runs shown in high-density report panels.",
    )
    replicate_parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=None,
        help="Optional directory containing empirical benchmark CSVs.",
    )
    replicate_parser.add_argument(
        "--benchmark-series",
        default=None,
        help="Optional comma-separated benchmark IDs to include, for example SPX,NAQ.",
    )
    replicate_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=None,
        help="Optional timeout for each simulator execution.",
    )
    replicate_parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help=(
            "Concurrent simulator runs. 0 (default) launches one per CPU "
            "core, capped at the seed count; 1 restores sequential "
            "execution. Parallel runs disable the live progress bar."
        ),
    )
    replicate_parser.add_argument(
        "--export-images",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Export publication-ready PNG, PDF, and SVG figures through "
            "Kaleido (requires Chrome; disable with --no-export-images)."
        ),
    )
    replicate_parser.add_argument(
        "--figure-formats",
        type=_figure_formats_argument,
        default=STATIC_EXPORT_FORMATS,
        help=(
            "Comma-separated static figure formats to export, e.g. png,pdf. "
            f"Supported: {', '.join(STATIC_EXPORT_FORMATS)} (default: all three)."
        ),
    )
    replicate_parser.add_argument(
        "--quiet-simulation-progress",
        action="store_true",
        help="Hide the C++ per-step progress bar for each replication simulation.",
    )
    replicate_parser.add_argument(
        "--with-comparison-report",
        action="store_true",
        help=(
            "Also build the full experiment-comparison report. Replication "
            "batches build the dedicated seed-robustness report by default "
            "because their runs differ only in the random seed."
        ),
    )
    replicate_parser.set_defaults(handler=handle_replicate)


def handle_replicate(args: argparse.Namespace) -> int:
    """Run one fixed simulation configuration across many random seeds."""

    options = SeedReplicationOptions(
        base_config=args.base_config,
        simulator=args.simulator,
        seeds=parse_seed_spec(args.seeds),
        experiment_name=args.experiment_name,
        experiment_root=args.experiment_root,
        phase=args.phase,
        price_column=args.price_column,
        max_runs=args.max_runs,
        benchmark_dir=args.benchmark_dir,
        benchmark_series=args.benchmark_series,
        timeout_seconds=args.timeout_seconds,
        export_images=args.export_images,
        figure_formats=args.figure_formats,
        show_simulation_progress=not args.quiet_simulation_progress,
        generate_comparison_report=args.with_comparison_report,
        jobs=args.jobs,
    )
    result = _run_seed_replication_from_public_cli(options)
    print(f"Seed replication experiment: {result.experiment_dir}")
    print(f"Replication run ledger: {result.replication_runs_csv_path}")
    print(f"Replication summary: {result.replication_summary_json_path}")
    if result.robustness_report_path is not None:
        print(f"Seed robustness report: {result.robustness_report_path}")
    if result.comparison_report_path is not None:
        print(f"Comparison report: {result.comparison_report_path}")
    if result.seed_robustness_csv_path is not None:
        print(f"Seed robustness CSV: {result.seed_robustness_csv_path}")
    if result.failed_count:
        print(
            f"Replication completed with {result.failed_count} failed seed(s) "
            f"and {result.completed_count} completed seed(s).",
            file=sys.stderr,
        )
        return 1
    return 0
