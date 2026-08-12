"""Single-run report command: parser and handler."""

from __future__ import annotations

import argparse
from pathlib import Path
from .shared_arguments import add_benchmark_arguments, add_source_arguments
from .shared_helpers import print_optional_outputs, resolve_benchmark_dir
from abm_analysis.report import build_run_report


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``run`` command."""

    run_parser = subparsers.add_parser(
        "run",
        help="Generate diagnostics and a compact report for one run directory.",
    )
    run_parser.add_argument(
        "run",
        type=str,
        help="Run ID when --source database is used, or path to one run directory with --source files.",
    )
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to <run_dir>/python_analysis.",
    )
    run_parser.add_argument(
        "--phase",
        default="simulation",
        help="Phase to analyse for returns. Use 'all' to include initial and warmup rows.",
    )
    run_parser.add_argument(
        "--price-column",
        default="market_price",
        help="Price column used to compute log returns.",
    )
    add_benchmark_arguments(run_parser)
    add_source_arguments(run_parser)
    run_parser.set_defaults(handler=handle_run)


def handle_run(args: argparse.Namespace) -> int:
    """Generate a single-run report from file or database inputs."""

    benchmark_dir = resolve_benchmark_dir(args)
    result = build_run_report(
        args.run,
        output_dir=args.output_dir,
        phase=args.phase,
        price_column=args.price_column,
        benchmark_dir=benchmark_dir,
        benchmark_series=args.benchmark_series,
        export_images=args.export_images,
        figure_formats=args.figure_formats,
        source=args.source,
        database_url=args.database_url,
        database_url_env=args.database_url_env,
    )
    print(f"Run analysis report: {result.report_path}")
    print(f"Diagnostics CSV: {result.diagnostics_csv_path}")
    print(f"Computed returns CSV: {result.returns_csv_path}")
    print_optional_outputs(result)
    if result.agent_summary_csv_path is not None:
        print(f"Agent summary CSV: {result.agent_summary_csv_path}")
    return 0
