"""Report output paths and benchmark-loading helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from abm_analysis.benchmarks import BenchmarkSeries, load_benchmark_timeseries_map, parse_benchmark_series

def _default_database_comparison_output_dir(experiment_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return Path("data") / "sql_reports" / experiment_name / "comparison_reports" / timestamp

def _default_database_run_output_dir(run_id: str) -> Path:
    return Path("data") / "sql_reports" / "runs" / run_id / "python_analysis"

def _load_benchmarks(
    benchmark_dir: Path | str | None,
    benchmark_series: str | list[str] | tuple[str, ...] | None,
) -> dict[str, BenchmarkSeries]:
    if benchmark_dir is None:
        return {}
    selected_series = parse_benchmark_series(benchmark_series)
    return load_benchmark_timeseries_map(benchmark_dir, selected_series)

def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True, sort=False)

def _comparison_output_dir(experiment_path: Path, output_dir: Path | str | None) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return experiment_path / "comparison_reports" / timestamp

def _robustness_output_dir(experiment_path: Path, output_dir: Path | str | None) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return experiment_path / "robustness_reports" / timestamp
