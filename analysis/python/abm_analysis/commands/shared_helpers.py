"""Helpers shared by more than one command handler.

The handlers themselves live in the command modules beside this one. What
remains here is the small amount of logic several of them need in common:
resolving which benchmark directory to read, naming a calibration study, and
printing the summary of a database import.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from abm_analysis.archive.benchmarks import default_benchmark_dir


def resolve_benchmark_dir(args: argparse.Namespace) -> Path | None:
    """Resolve benchmark inputs from the CLI switches, or fall back to the repo copy."""

    if args.benchmark_dir is not None:
        return args.benchmark_dir
    candidate = default_benchmark_dir()
    return candidate if candidate.is_dir() else None


def print_import_summaries(summaries: list[object]) -> None:
    """Print a compact summary for one or more import operations."""

    if not summaries:
        print("No data was imported.")
        return
    total_rows = sum(int(getattr(summary, "rows_imported", 0)) for summary in summaries)
    for summary in summaries:
        print(
            f"Imported {summary.item_type} {summary.identifier}: "
            f"{summary.rows_imported} rows"
        )
    print(f"Total imported rows: {total_rows}")


def timestamped_calibration_name() -> str:
    """Return the default calibration study name used by the CLI."""

    return f"calibration_{datetime.now().strftime('%Y%m%d%H%M%S')}"
