"""Command handlers for the ABM analysis command-line interface."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from abm_analysis.archive.benchmarks import default_benchmark_dir


def resolve_benchmark_dir(args: argparse.Namespace) -> Path | None:
    """Resolve benchmark inputs according to source mode and CLI switches."""

    if getattr(args, "no_benchmark", False):
        return None
    if args.benchmark_dir is not None:
        return args.benchmark_dir
    if getattr(args, "source", None) == "database":
        return None
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


def print_optional_outputs(result: object) -> None:
    """Print optional report artefact paths when a report builder produced them."""

    for label, attribute in [
        ("Benchmark diagnostics CSV", "benchmark_diagnostics_csv_path"),
        ("Simulation-vs-benchmark CSV", "simulation_vs_benchmark_csv_path"),
        ("Seed robustness CSV", "seed_robustness_csv_path"),
        ("Stress-regime diagnostics CSV", "stress_regime_csv_path"),
        ("Figure index CSV", "figure_index_csv_path"),
    ]:
        value = getattr(result, attribute, None)
        if value is not None:
            print(f"{label}: {value}")
