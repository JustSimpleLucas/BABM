"""Holdout validation of a calibrated configuration.

The seed-robustness export is covered end to end by ``test_replication.py`` and
the calibration tables by ``test_calibration.py``. What is tested here is the
out-of-sample check, whose whole point is that it can be skipped: a study run
without holdout series must still say so in the archive.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from abm_analysis.exports import write_holdout_validation

from abm_test_helpers import make_synthetic_benchmark_dir, make_synthetic_experiment


def test_holdout_validation_measures_runs_against_held_back_series(tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    benchmark_dir = make_synthetic_benchmark_dir(tmp_path)

    tables = write_holdout_validation(
        experiment_dir,
        output_dir=tmp_path / "holdout",
        benchmark_dir=benchmark_dir,
        benchmark_series="NAQ",
    )

    assert tables.benchmark_diagnostics_csv_path is not None
    assert tables.simulation_vs_benchmark_csv_path is not None

    comparison = pd.read_csv(tables.simulation_vs_benchmark_csv_path)
    assert not comparison.empty
    # Only the held-back series may appear: comparing against the series the
    # search already fitted would make the check circular.
    assert comparison["benchmark_id"].astype(str).unique().tolist() == ["NAQ"]

    diagnostics = pd.read_csv(tables.benchmark_diagnostics_csv_path)
    assert diagnostics["benchmark_id"].astype(str).tolist() == ["NAQ"]

    summary = json.loads(tables.summary_json_path.read_text(encoding="utf-8"))
    assert summary["status"] == "run"
    assert summary["holdout_benchmark_series"] == ["NAQ"]
    assert summary["validated_run_count"] > 0


def test_holdout_validation_records_that_it_was_skipped(tmp_path: Path) -> None:
    """No holdout series is a fact about the study, not a missing folder."""

    experiment_dir = make_synthetic_experiment(tmp_path)

    tables = write_holdout_validation(
        experiment_dir,
        output_dir=tmp_path / "holdout",
        benchmark_dir=tmp_path / "does_not_exist",
        benchmark_series=None,
    )

    summary = json.loads(tables.summary_json_path.read_text(encoding="utf-8"))
    assert summary["status"] == "not_run"
    assert tables.simulation_vs_benchmark_csv_path is None
    assert not list(tables.output_dir.glob("*.csv"))


def test_holdout_validation_rejects_a_directory_without_runs(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    benchmark_dir = make_synthetic_benchmark_dir(tmp_path)

    with pytest.raises(FileNotFoundError):
        write_holdout_validation(
            empty_dir,
            output_dir=tmp_path / "holdout",
            benchmark_dir=benchmark_dir,
            benchmark_series="SPX",
        )
