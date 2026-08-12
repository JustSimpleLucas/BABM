"""Benchmark-conversion command: parser and handler.

Turning the empirical `.xlsx` workbooks under `data/stock_data/` into CSVs is a
step of the analysis pipeline, not a side errand, so it is a subcommand like
any other rather than a script run by hand from a remembered path.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from abm_analysis.archive.xlsx_conversion import convert_path


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``convert-benchmarks`` command."""

    convert_parser = subparsers.add_parser(
        "convert-benchmarks",
        help=(
            "Convert empirical .xlsx workbooks to the per-sheet CSVs the "
            "benchmark loader reads. Run this when new market data is added."
        ),
    )
    convert_parser.add_argument(
        "input_path",
        type=Path,
        help="Path to a .xlsx workbook, or a directory containing .xlsx workbooks.",
    )
    convert_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Optional output directory. Defaults to a directory beside each "
            "workbook; directory input creates one subdirectory per workbook."
        ),
    )
    convert_parser.set_defaults(handler=handle_convert_benchmarks)


def handle_convert_benchmarks(args: argparse.Namespace) -> int:
    """Convert the requested workbooks and report what was written."""

    input_path = Path(args.input_path).expanduser()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else None

    try:
        converted = convert_path(input_path, output_dir)
    except (FileNotFoundError, ValueError) as error:
        print(f"Conversion failed: {error}")
        return 1

    total_sheets = 0
    for workbook, csv_paths in converted.items():
        print(f"Converting: {workbook}")
        for csv_path in csv_paths:
            print(f"  Saved: {csv_path}")
        total_sheets += len(csv_paths)

    workbook_count = len(converted)
    workbook_label = "workbook" if workbook_count == 1 else "workbooks"
    sheet_label = "sheet" if total_sheets == 1 else "sheets"
    print(f"Converted {workbook_count} {workbook_label} and {total_sheets} {sheet_label}.")
    return 0
