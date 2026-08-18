"""Argument groups shared by more than one CLI command.

These sit beside the command modules rather than inside any one of them, so a
command can add a shared option group without importing a sibling command or
the parser that will eventually register it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from abm_analysis.database import DEFAULT_DATABASE_URL_ENV


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
