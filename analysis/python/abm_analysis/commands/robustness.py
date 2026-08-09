"""Seed-robustness report command: parser and handler."""

from __future__ import annotations

import argparse
from pathlib import Path
from ..cli_arguments import _figure_formats_argument
from ..cli_handlers import _build_seed_robustness_report_from_public_cli
from abm_analysis.report.static_export import STATIC_EXPORT_FORMATS


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``robustness`` command."""

    robustness_parser = subparsers.add_parser(
        "robustness",
        help=(
            "Generate the dedicated seed-robustness HTML report for an archived "
            "experiment directory without re-running simulations."
        ),
    )
    robustness_parser.add_argument(
        "experiment",
        type=Path,
        help=(
            "Path to data/experiments/<experiment_name>. File archives only; "
            "database-backed robustness reports are not supported yet."
        ),
    )
    robustness_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Optional report directory. Defaults to "
            "<experiment_dir>/robustness_reports/<YYYYMMDDHHMMSS>."
        ),
    )
    robustness_parser.add_argument(
        "--phase",
        default="simulation",
        help="Phase to analyse for returns. Use 'all' to include initial and warmup rows.",
    )
    robustness_parser.add_argument(
        "--price-column",
        default="market_price",
        help="Price column used to compute log returns.",
    )
    robustness_parser.add_argument(
        "--max-runs",
        type=int,
        default=8,
        help="Maximum number of seeds shown in high-density overlay panels.",
    )
    robustness_parser.add_argument(
        "--export-images",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Export publication-ready PNG, PDF, and SVG figures through "
            "Kaleido (requires Chrome; disable with --no-export-images)."
        ),
    )
    robustness_parser.add_argument(
        "--figure-formats",
        type=_figure_formats_argument,
        default=STATIC_EXPORT_FORMATS,
        help=(
            "Comma-separated static figure formats to export, e.g. png,pdf. "
            f"Supported: {', '.join(STATIC_EXPORT_FORMATS)} (default: all three)."
        ),
    )
    robustness_parser.set_defaults(handler=handle_robustness)


def handle_robustness(args: argparse.Namespace) -> int:
    """Generate the dedicated seed-robustness report for an archived experiment."""

    result = _build_seed_robustness_report_from_public_cli(
        args.experiment,
        output_dir=args.output_dir,
        phase=args.phase,
        price_column=args.price_column,
        max_runs=args.max_runs,
        export_images=args.export_images,
        figure_formats=args.figure_formats,
    )
    print(f"Seed robustness report: {result.report_path}")
    print(f"Runs index CSV: {result.runs_index_csv_path}")
    print(f"Stylised-fact diagnostics CSV: {result.diagnostics_csv_path}")
    print(f"Pairwise K-S CSV: {result.pairwise_ks_csv_path}")
    print(f"Seed robustness CSV: {result.seed_robustness_csv_path}")
    print(f"Cross-seed distribution tests CSV: {result.distribution_tests_csv_path}")
    print(f"ADF stationarity CSV: {result.adf_stationarity_csv_path}")
    print(f"Seed convergence CSV: {result.seed_convergence_csv_path}")
    print(f"Robustness verdicts CSV: {result.verdicts_csv_path}")
    print(f"Figure index CSV: {result.figure_index_csv_path}")
    return 0
