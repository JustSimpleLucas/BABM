"""Experiment-comparison report command: parser and handler."""

from __future__ import annotations

import argparse
from pathlib import Path
from .shared_arguments import add_benchmark_arguments, add_source_arguments
from .shared_helpers import print_optional_outputs, resolve_benchmark_dir
from abm_analysis.report import build_comparison_report


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``compare`` command."""

    compare_parser = subparsers.add_parser(
        "compare",
        help="Generate a static HTML comparison report for an experiment directory.",
    )
    compare_parser.add_argument(
        "experiment",
        type=str,
        help=(
            "Experiment name when --source database is used, or path to "
            "data/experiments/<experiment_name> with --source files."
        ),
    )
    compare_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Optional report directory. Defaults to "
            "<experiment_dir>/comparison_reports/<YYYYMMDDHHMMSS>."
        ),
    )
    compare_parser.add_argument(
        "--phase",
        default="simulation",
        help="Phase to analyse for returns. Use 'all' to include initial and warmup rows.",
    )
    compare_parser.add_argument(
        "--price-column",
        default="market_price",
        help="Price column used to compute log returns.",
    )
    compare_parser.add_argument(
        "--max-runs",
        type=int,
        default=8,
        help="Maximum number of runs shown in high-density time-series panels.",
    )
    add_benchmark_arguments(compare_parser)
    add_source_arguments(compare_parser)
    compare_parser.set_defaults(handler=handle_compare)


def handle_compare(args: argparse.Namespace) -> int:
    """Generate an experiment-comparison report from file or database inputs."""

    benchmark_dir = resolve_benchmark_dir(args)
    result = build_comparison_report(
        args.experiment,
        output_dir=args.output_dir,
        phase=args.phase,
        price_column=args.price_column,
        max_runs=args.max_runs,
        benchmark_dir=benchmark_dir,
        benchmark_series=args.benchmark_series,
        export_images=args.export_images,
        figure_formats=args.figure_formats,
        source=args.source,
        database_url=args.database_url,
        database_url_env=args.database_url_env,
    )
    print(f"Comparison report: {result.report_path}")
    print(f"Runs index CSV: {result.runs_index_csv_path}")
    print(f"Stylised-fact diagnostics CSV: {result.diagnostics_csv_path}")
    print(f"Pairwise K-S CSV: {result.pairwise_ks_csv_path}")
    print_optional_outputs(result)
    if result.agent_summary_csv_path is not None:
        print(f"Agent summary CSV: {result.agent_summary_csv_path}")
    return 0
