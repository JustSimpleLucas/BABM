"""Argument groups shared by more than one CLI command.

These live apart from both the top-level parser and the command modules so
that a command can add a shared option group without importing the parser
that will eventually register it."""

from __future__ import annotations

import argparse
from pathlib import Path

from abm_analysis.database import DEFAULT_DATABASE_URL_ENV
from abm_analysis.report.static_export import STATIC_EXPORT_FORMATS, parse_figure_formats


def _figure_formats_argument(value: str) -> tuple[str, ...]:
    try:
        return parse_figure_formats(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error

def add_benchmark_arguments(parser: argparse.ArgumentParser) -> None:
    """Add empirical benchmark options used by report commands."""

    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing empirical benchmark CSVs. Defaults to the "
            "repository-local data/stock_data/candle_chart directory when present."
        ),
    )
    parser.add_argument(
        "--benchmark-series",
        default=None,
        help="Comma-separated benchmark IDs to include, for example SPX,NAQ.",
    )
    parser.add_argument(
        "--no-benchmark",
        action="store_true",
        help="Disable empirical benchmark loading and simulation-vs-market comparison.",
    )
    parser.add_argument(
        "--export-images",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Export publication-ready PNG, PDF, and SVG figures through "
            "Kaleido (requires Chrome; disable with --no-export-images)."
        ),
    )
    parser.add_argument(
        "--figure-formats",
        type=_figure_formats_argument,
        default=STATIC_EXPORT_FORMATS,
        help=(
            "Comma-separated static figure formats to export, e.g. png,pdf. "
            f"Supported: {', '.join(STATIC_EXPORT_FORMATS)} (default: all three)."
        ),
    )

def add_calibration_benchmark_arguments(parser: argparse.ArgumentParser) -> None:
    """Add benchmark options used by calibration commands."""

    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing empirical benchmark CSVs. Defaults to the "
            "repository-local data/stock_data/candle_chart directory when present."
        ),
    )
    parser.add_argument(
        "--benchmark-series",
        default=None,
        help="Comma-separated benchmark IDs to include, for example SPX,NAQ.",
    )

def add_database_arguments(parser: argparse.ArgumentParser) -> None:
    """Add PostgreSQL connection options."""

    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL SQLAlchemy URL. Prefer ABM_DATABASE_URL for normal use.",
    )
    parser.add_argument(
        "--database-url-env",
        default=DEFAULT_DATABASE_URL_ENV,
        help="Environment variable containing the PostgreSQL URL.",
    )

def add_source_arguments(parser: argparse.ArgumentParser) -> None:
    """Add file-vs-database source selection options."""

    parser.add_argument(
        "--source",
        choices=["database", "files"],
        default="database",
        help="Read analysis inputs from PostgreSQL by default, or from legacy files.",
    )
    add_database_arguments(parser)

