from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from abm_analysis.benchmarks import (
    build_benchmark_diagnostics,
    build_benchmark_return_series,
    load_benchmark_timeseries,
    load_benchmark_timeseries_map,
)


def test_benchmark_loader_handles_bom_reverse_dates_missing_volume_and_invalid_prices(
    tmp_path: Path,
) -> None:
    benchmark_dir = tmp_path / "benchmarks"
    benchmark_dir.mkdir()
    benchmark_path = benchmark_dir / "02_SPX.csv"
    rows = ["Date,Open,High,Low,Close"]
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    prices = 100.0 * np.exp(np.linspace(0.0, 0.12, len(dates)))
    for date, price in zip(reversed(dates), reversed(prices), strict=True):
        rows.append(f"{date.date()},{price - 1},{price + 1},{price - 2},{price}")
    rows.insert(12, "2026-01-15,100,101,99,0")
    benchmark_path.write_text("\ufeff" + "\n".join(rows), encoding="utf-8")

    benchmark = load_benchmark_timeseries(benchmark_path)
    benchmarks = load_benchmark_timeseries_map(benchmark_dir, "SPX")
    returns = build_benchmark_return_series(benchmarks)
    diagnostics = build_benchmark_diagnostics(benchmarks)

    assert benchmark.benchmark_id == "SPX"
    assert "traded_volume" not in benchmark.data.columns
    assert benchmark.data["Date"].is_monotonic_increasing
    assert np.isfinite(returns["SPX"]).all()
    assert len(returns["SPX"]) >= 50
    assert diagnostics.iloc[0]["benchmark_id"] == "SPX"
    assert diagnostics.iloc[0]["diagnostic_status"] == "completed"
