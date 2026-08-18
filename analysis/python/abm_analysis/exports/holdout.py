"""Holdout validation of a calibrated configuration.

Calibration fits the model to one set of empirical series, which makes a good
score on those same series uninformative — the parameters were chosen to produce
it. This export re-screens the winner's runs against benchmark series held back
from the search, so the comparison is out-of-sample.

Two tables come out of it: the stylised-fact diagnostics of each holdout series
on its own terms, and the winner's simulated returns measured against them
(quantile error and autocorrelation distance, from
``statistics.comparisons``).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from abm_analysis.archive.benchmarks import (
    build_benchmark_diagnostics,
    build_benchmark_return_series,
    load_benchmark_timeseries_map,
    parse_benchmark_series,
)
from abm_analysis.archive.data import build_runs_index, discover_run_directories
from abm_analysis.statistics.comparisons import build_simulation_benchmark_comparison
from abm_analysis.statistics.diagnostics import build_return_series_by_asset


@dataclass(frozen=True)
class HoldoutTables:
    """Paths written by one holdout validation export."""

    output_dir: Path
    summary_json_path: Path
    benchmark_diagnostics_csv_path: Path | None
    simulation_vs_benchmark_csv_path: Path | None


def write_holdout_validation(
    runs_dir: Path | str,
    *,
    output_dir: Path | str,
    benchmark_dir: Path | str,
    benchmark_series: str | list[str] | tuple[str, ...] | None,
    phase: str = "simulation",
    price_column: str = "market_price",
) -> HoldoutTables:
    """Measure a calibrated configuration's runs against held-back benchmarks.

    With no holdout series requested the directory is still written, carrying a
    ``status: "not_run"`` summary: the absence of the check has to be visible in
    the archive rather than inferred from a missing folder.
    """

    holdout_dir = Path(output_dir).expanduser().resolve()
    holdout_dir.mkdir(parents=True, exist_ok=True)
    summary_json_path = holdout_dir / "summary.json"

    if not benchmark_series:
        _write_summary(
            summary_json_path,
            {
                "status": "not_run",
                "reason": "No holdout benchmark series was supplied.",
            },
        )
        return HoldoutTables(
            output_dir=holdout_dir,
            summary_json_path=summary_json_path,
            benchmark_diagnostics_csv_path=None,
            simulation_vs_benchmark_csv_path=None,
        )

    selected_series = parse_benchmark_series(benchmark_series)
    benchmarks = load_benchmark_timeseries_map(benchmark_dir, selected_series)
    benchmark_returns = build_benchmark_return_series(benchmarks)
    benchmark_diagnostics = build_benchmark_diagnostics(benchmarks)

    runs_path = Path(runs_dir).expanduser().resolve()
    run_dirs = discover_run_directories(runs_path)
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found under {runs_path}")
    return_series_by_run = build_return_series_by_asset(
        run_dirs,
        phase=phase,
        price_column=price_column,
    )
    simulation_vs_benchmark = build_simulation_benchmark_comparison(
        return_series_by_run,
        benchmark_returns,
    )

    benchmark_diagnostics_csv_path = holdout_dir / "benchmark_diagnostics.csv"
    simulation_vs_benchmark_csv_path = holdout_dir / "simulation_vs_benchmark.csv"
    benchmark_diagnostics.to_csv(benchmark_diagnostics_csv_path, index=False)
    simulation_vs_benchmark.to_csv(simulation_vs_benchmark_csv_path, index=False)

    runs_index = build_runs_index(runs_path)
    _write_summary(
        summary_json_path,
        {
            "status": "run",
            "holdout_benchmark_series": sorted(benchmarks),
            "validated_run_count": int(len(runs_index)),
            "phase": phase,
            "price_column": price_column,
            "outputs": {
                "benchmark_diagnostics_csv": benchmark_diagnostics_csv_path.name,
                "simulation_vs_benchmark_csv": simulation_vs_benchmark_csv_path.name,
            },
        },
    )
    return HoldoutTables(
        output_dir=holdout_dir,
        summary_json_path=summary_json_path,
        benchmark_diagnostics_csv_path=benchmark_diagnostics_csv_path,
        simulation_vs_benchmark_csv_path=simulation_vs_benchmark_csv_path,
    )


def _write_summary(path: Path, summary: dict[str, object]) -> None:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
