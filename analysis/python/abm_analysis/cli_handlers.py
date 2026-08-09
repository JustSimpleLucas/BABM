"""Command handlers for the ABM analysis command-line interface."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from abm_analysis.benchmarks import default_benchmark_dir
from abm_analysis.calibration import CalibrationOptions, run_calibration
from abm_analysis.replication import SeedReplicationOptions, run_seed_replication
from abm_analysis.report import build_seed_robustness_report


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


def _run_calibration_from_public_cli(options: CalibrationOptions) -> Path:
    """Respect the historic ``abm_analysis.cli.run_calibration`` patch point."""

    cli_module = sys.modules.get("abm_analysis.cli")
    runner = getattr(cli_module, "run_calibration", run_calibration)
    return runner(options)


def _run_seed_replication_from_public_cli(options: SeedReplicationOptions):
    """Respect the public ``abm_analysis.cli.run_seed_replication`` patch point."""

    cli_module = sys.modules.get("abm_analysis.cli")
    runner = getattr(cli_module, "run_seed_replication", run_seed_replication)
    return runner(options)


def _build_seed_robustness_report_from_public_cli(experiment, **kwargs):
    """Respect the public ``abm_analysis.cli.build_seed_robustness_report`` patch point."""

    cli_module = sys.modules.get("abm_analysis.cli")
    builder = getattr(cli_module, "build_seed_robustness_report", build_seed_robustness_report)
    return builder(experiment, **kwargs)


_resolve_benchmark_dir = resolve_benchmark_dir
_print_import_summaries = print_import_summaries
_timestamped_calibration_name = timestamped_calibration_name
_print_optional_outputs = print_optional_outputs
