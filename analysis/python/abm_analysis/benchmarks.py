"""Empirical benchmark loading for thesis-grade ABM validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd

from abm_analysis.data import compute_log_returns
from abm_analysis.diagnostics import diagnose_return_series


DEFAULT_BENCHMARK_RELATIVE_PATH = Path("data") / "stock_data" / "candle_chart"

# Directory layout used before 2026-07-08; retained so older local checkouts
# with the space-separated folder names keep working without re-downloading.
LEGACY_BENCHMARK_RELATIVE_PATH = Path("data") / "Stock Data" / "Candle Chart"


@dataclass(frozen=True)
class BenchmarkSeries:
    """Normalised empirical market series used as a simulation benchmark."""

    benchmark_id: str
    source_file: str
    data: pd.DataFrame


def default_benchmark_dir() -> Path:
    """Return the repository-local benchmark directory used by the CLI."""

    repository_root = Path(__file__).resolve().parents[3]
    preferred = repository_root / DEFAULT_BENCHMARK_RELATIVE_PATH
    if preferred.is_dir():
        return preferred
    legacy = repository_root / LEGACY_BENCHMARK_RELATIVE_PATH
    if legacy.is_dir():
        return legacy
    return preferred


def parse_benchmark_series(value: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    """Parse a comma-separated benchmark selection into normalised identifiers."""

    if value is None:
        return None
    raw_values: list[str] = []
    if isinstance(value, str):
        raw_values = value.split(",")
    else:
        raw_values = list(value)
    parsed = [_normalise_benchmark_id(item) for item in raw_values if str(item).strip()]
    return parsed or None


def discover_benchmark_files(
    benchmark_dir: Path | str,
    benchmark_series: str | list[str] | tuple[str, ...] | None = None,
) -> list[Path]:
    """Discover benchmark CSV files, optionally filtered by benchmark ID."""

    benchmark_path = Path(benchmark_dir).expanduser().resolve()
    if not benchmark_path.exists():
        raise FileNotFoundError(f"Benchmark directory does not exist: {benchmark_path}")
    if not benchmark_path.is_dir():
        raise NotADirectoryError(f"Benchmark path is not a directory: {benchmark_path}")

    selected_ids = parse_benchmark_series(benchmark_series)
    selected_set = set(selected_ids) if selected_ids else None
    files = sorted(path for path in benchmark_path.glob("*.csv") if path.is_file())
    if selected_set is None:
        return files
    return [
        path
        for path in files
        if infer_benchmark_id(path) in selected_set
    ]


def infer_benchmark_id(path: Path | str) -> str:
    """Infer a compact benchmark ID from files such as ``02_SPX.csv``."""

    stem = Path(path).stem
    without_prefix = re.sub(r"^\d+[\s_-]*", "", stem)
    return _normalise_benchmark_id(without_prefix)


def load_benchmark_timeseries(path: Path | str) -> BenchmarkSeries:
    """Load one empirical OHLC benchmark and compute close-to-close log returns.

    Benchmark CSVs exported from spreadsheet tools often include a UTF-8 byte
    order mark and are commonly ordered newest-first. The loader handles both
    cases explicitly so empirical comparisons are reproducible across Mac and
    Windows spreadsheet exports.
    """

    csv_path = Path(path).expanduser().resolve()
    data = pd.read_csv(csv_path, encoding="utf-8-sig")
    data.columns = [str(column).strip() for column in data.columns]
    required_columns = {"Date", "Close"}
    missing = required_columns.difference(data.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise KeyError(f"Benchmark file {csv_path.name} is missing required columns: {missing_text}")

    normalised = data.copy()
    normalised["Date"] = pd.to_datetime(normalised["Date"], errors="coerce")
    normalised = normalised[normalised["Date"].notna()].sort_values("Date").reset_index(drop=True)
    normalised["Close"] = pd.to_numeric(normalised["Close"], errors="coerce")
    normalised["market_price"] = normalised["Close"]
    if "Volume" in normalised.columns:
        normalised["traded_volume"] = pd.to_numeric(normalised["Volume"], errors="coerce")
    normalised["computed_log_return"] = compute_log_returns(normalised["Close"])
    normalised["benchmark_id"] = infer_benchmark_id(csv_path)
    normalised["source_file"] = csv_path.name
    return BenchmarkSeries(
        benchmark_id=infer_benchmark_id(csv_path),
        source_file=csv_path.name,
        data=normalised,
    )


def load_benchmark_timeseries_map(
    benchmark_dir: Path | str,
    benchmark_series: str | list[str] | tuple[str, ...] | None = None,
) -> dict[str, BenchmarkSeries]:
    """Load every selected benchmark series from a benchmark directory."""

    benchmarks: dict[str, BenchmarkSeries] = {}
    for path in discover_benchmark_files(benchmark_dir, benchmark_series):
        benchmark = load_benchmark_timeseries(path)
        benchmarks[benchmark.benchmark_id] = benchmark
    return benchmarks


def build_benchmark_return_series(
    benchmarks: dict[str, BenchmarkSeries],
) -> dict[str, pd.Series]:
    """Return finite empirical log-return series keyed by benchmark ID."""

    result: dict[str, pd.Series] = {}
    for benchmark_id, benchmark in benchmarks.items():
        returns = pd.to_numeric(benchmark.data["computed_log_return"], errors="coerce")
        result[benchmark_id] = returns[np.isfinite(returns)].reset_index(drop=True)
    return result


def build_benchmark_diagnostics(benchmarks: dict[str, BenchmarkSeries]) -> pd.DataFrame:
    """Run the same stylised-fact diagnostics used for simulated returns."""

    rows: list[dict[str, object]] = []
    for benchmark_id, benchmark in benchmarks.items():
        returns = pd.to_numeric(benchmark.data["computed_log_return"], errors="coerce")
        row = diagnose_return_series(
            benchmark_id,
            returns,
            phase="empirical",
            price_column="Close",
        )
        row["benchmark_id"] = row.pop("run_id")
        row["source_file"] = benchmark.source_file
        row["source_type"] = "benchmark"
        rows.append(row)
    return pd.DataFrame(rows)


def _normalise_benchmark_id(value: object) -> str:
    text = str(value).strip().upper()
    text = re.sub(r"\s+", "_", text)
    return text
