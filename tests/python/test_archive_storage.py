"""Tests for archive storage behaviour: drift guard, caching, compression,
and chunked database inserts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from abm_analysis.archives import (
    build_run_archive,
    discover_run_directories,
    resolve_artifact_path,
    validate_run_archive,
)
from abm_analysis.compression import (
    COMPRESSIBLE_RUN_ARTIFACTS,
    compress_run_archive,
)
from abm_analysis.database import build_run_import_tables
from abm_analysis.database import table_builders
from abm_analysis.database.constants import ASSET_TIMESERIES_COLUMNS
from abm_analysis.database.normalisation import _normalise_table_record
from abm_analysis.database.table_builders import _insert_dataframe
from abm_analysis.timeseries import load_asset_timeseries, load_step_timeseries
from abm_test_helpers import write_synthetic_run


RUN_ID = "20260427143012_1_1_0_1_20_30_5_2_180_66"


class _RecordingConnection:
    """Capture executed statements without any real database."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> None:
        self.calls.append((str(statement), parameters or {}))


def _write_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / RUN_ID
    write_synthetic_run(run_dir, RUN_ID, seed=66, drift_adjustment=0.0)
    return run_dir


def test_import_rejects_unknown_simulator_columns(tmp_path: Path) -> None:
    """A CSV column unknown to the importer must fail loudly, not vanish."""

    run_dir = _write_run(tmp_path)
    step_path = run_dir / "step_timeseries.csv"
    step_data = pd.read_csv(step_path)
    step_data["new_experimental_diagnostic"] = 1.0
    step_data.to_csv(step_path, index=False)

    with pytest.raises(ValueError, match="new_experimental_diagnostic"):
        build_run_import_tables(run_dir)


def test_import_still_tolerates_missing_legacy_columns(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    step_path = run_dir / "step_timeseries.csv"
    step_data = pd.read_csv(step_path).drop(columns=["wealth_gini_coefficient"])
    step_data.to_csv(step_path, index=False)

    tables = build_run_import_tables(run_dir)

    assert tables["step_timeseries"]["wealth_gini_coefficient"].isna().all()


def test_insert_dataframe_batches_rows_into_multi_row_statements() -> None:
    connection = _RecordingConnection()
    data = pd.DataFrame(
        {
            "run_id": [RUN_ID] * 5,
            "stylised_row_index": range(5),
            "stylised_fact": [f"fact_{index}" for index in range(5)],
        }
    )

    inserted = _insert_dataframe(
        connection, "stylised_facts", data, tuple(data.columns)
    )

    assert inserted == 5
    assert len(connection.calls) == 1
    statement, parameters = connection.calls[0]
    assert statement.count("(:run_id_") == 5
    assert parameters["stylised_fact_4"] == "fact_4"
    assert len(parameters) == 15


def test_insert_dataframe_respects_bind_parameter_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(table_builders, "_MAX_BIND_PARAMETERS_PER_STATEMENT", 4)
    connection = _RecordingConnection()
    data = pd.DataFrame(
        {
            "run_id": [RUN_ID] * 5,
            "stylised_row_index": range(5),
            "stylised_fact": [f"fact_{index}" for index in range(5)],
        }
    )

    inserted = _insert_dataframe(
        connection, "stylised_facts", data, tuple(data.columns)
    )

    assert inserted == 5
    # Three columns with a budget of four parameters means one row per batch.
    assert len(connection.calls) == 5


def test_insert_dataframe_casts_jsonb_columns() -> None:
    connection = _RecordingConnection()
    data = pd.DataFrame(
        {
            "benchmark_id": ["SPX"],
            "row_index": [0],
            "raw_row_json": ['{"Close": 100.0}'],
        }
    )

    _insert_dataframe(connection, "benchmark_prices", data, tuple(data.columns))

    statement, _ = connection.calls[0]
    assert "CAST(:raw_row_json_0 AS JSONB)" in statement


def test_count_columns_are_normalised_to_exact_integers() -> None:
    record = _normalise_table_record(
        "step_timeseries",
        {"submitted_orders": 12.0, "executed_trades": float("nan"), "log_return": 0.5},
    )

    assert record["submitted_orders"] == 12
    assert isinstance(record["submitted_orders"], int)
    assert record["executed_trades"] is None
    assert record["log_return"] == 0.5


def _write_asset_timeseries(run_dir: Path, assets: tuple[str, ...]) -> pd.DataFrame:
    """Write a small long-format asset_timeseries.csv beside a synthetic run."""

    rows = []
    row_index = 0
    for step in range(1, 6):
        for asset_index, asset in enumerate(assets):
            rows.append(
                {
                    "row_index": row_index,
                    "phase": "simulation",
                    "simulation_step": step,
                    "asset": asset,
                    "market_price": 100.0 + step + asset_index,
                    "fundamental_price": 99.0 + step,
                    "raw_return": 0.001 * step,
                    "log_return": 0.001 * step,
                    "traded_volume": 10.0 * step,
                }
            )
            row_index += 1
    frame = pd.DataFrame(rows)
    frame.to_csv(run_dir / "asset_timeseries.csv", index=False)
    return frame


def test_archive_without_asset_timeseries_stays_valid(tmp_path: Path) -> None:
    """Archives created before the multi-asset extension must still validate."""

    run_dir = _write_run(tmp_path)
    assert not (run_dir / "asset_timeseries.csv").exists()

    validation = validate_run_archive(run_dir)

    assert validation.is_valid
    assert any("asset_timeseries.csv" in warning for warning in validation.warnings)
    assert build_run_archive(run_dir).asset_timeseries_csv is None


def test_declared_asset_timeseries_must_be_present(tmp_path: Path) -> None:
    """Metadata declaring the artefact makes a missing file an error."""

    run_dir = _write_run(tmp_path)
    metadata_path = run_dir / "metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.is_file()
        else {}
    )
    metadata.setdefault("outputs", {})["asset_timeseries_enabled"] = True
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    validation = validate_run_archive(run_dir)

    assert not validation.is_valid
    assert any("asset_timeseries_enabled" in error for error in validation.errors)


def test_load_asset_timeseries_filters_by_asset(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    _write_asset_timeseries(run_dir, ("alpha", "beta"))

    every_asset = load_asset_timeseries(run_dir)
    alpha_only = load_asset_timeseries(run_dir, asset="alpha")

    assert len(every_asset) == 10
    assert sorted(every_asset["asset"].unique()) == ["alpha", "beta"]
    assert len(alpha_only) == 5
    assert set(alpha_only["asset"].unique()) == {"alpha"}
    assert (alpha_only["run_id"] == RUN_ID).all()

    with pytest.raises(KeyError, match="gamma"):
        load_asset_timeseries(run_dir, asset="gamma")


def test_missing_asset_timeseries_loader_raises(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)

    with pytest.raises(FileNotFoundError, match="asset_timeseries.csv"):
        load_asset_timeseries(run_dir)


def test_asset_timeseries_import_table_is_built(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    _write_asset_timeseries(run_dir, ("alpha", "beta"))

    tables = build_run_import_tables(run_dir)
    asset_table = tables["asset_timeseries"]

    assert list(asset_table.columns) == list(ASSET_TIMESERIES_COLUMNS)
    assert len(asset_table) == 10
    assert (asset_table["run_id"] == RUN_ID).all()
    # Columns the writer omits in this fixture import as missing values.
    assert asset_table["self_trade_preventions"].isna().all()


def test_load_step_timeseries_returns_independent_copies(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)

    first = load_step_timeseries(run_dir)
    first["market_price"] = -1.0
    second = load_step_timeseries(run_dir)

    assert (second["market_price"] > 0).all()


def test_load_step_timeseries_sees_rewritten_files(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    before = load_step_timeseries(run_dir)

    rewritten = pd.read_csv(run_dir / "step_timeseries.csv").iloc[:50]
    rewritten.to_csv(run_dir / "step_timeseries.csv", index=False)
    after = load_step_timeseries(run_dir)

    assert len(before) > len(after)
    assert len(after) == 50


def test_compressed_archive_round_trip(tmp_path: Path) -> None:
    """Compression keeps discovery, loading, validation, and import working."""

    run_dir = _write_run(tmp_path)
    plain_frame = load_step_timeseries(run_dir)

    results = compress_run_archive(run_dir)

    compressed_names = {result.filename for result in results}
    assert "step_timeseries.csv" in compressed_names
    assert "trade_ledger.csv" in compressed_names
    assert not (run_dir / "step_timeseries.csv").exists()
    assert (run_dir / "step_timeseries.csv.gz").is_file()
    for result in results:
        assert result.compressed_bytes < result.original_bytes

    assert discover_run_directories(tmp_path) == [run_dir]
    archive = build_run_archive(run_dir)
    assert archive.step_timeseries_csv.name == "step_timeseries.csv.gz"

    validation = validate_run_archive(run_dir)
    assert validation.errors == ()

    compressed_frame = load_step_timeseries(run_dir)
    pd.testing.assert_frame_equal(plain_frame, compressed_frame)

    tables = build_run_import_tables(run_dir)
    assert len(tables["step_timeseries"]) == len(plain_frame)
    assert len(tables["trade_ledger"]) == 20


def test_compress_run_archive_is_idempotent(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)

    first = compress_run_archive(run_dir)
    second = compress_run_archive(run_dir)

    assert first
    assert second == []


def test_compress_rejects_non_run_directories(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compress_run_archive(tmp_path)


def test_plain_artifact_wins_over_stale_compressed_copy(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    compress_run_archive(run_dir)
    fresh_plain = run_dir / "step_timeseries.csv"
    fresh_plain.write_text("row_index\n0\n", encoding="utf-8")

    resolved = resolve_artifact_path(run_dir, "step_timeseries.csv")

    assert resolved == fresh_plain


def test_compressible_artifact_list_covers_the_large_per_row_files() -> None:
    assert "step_timeseries.csv" in COMPRESSIBLE_RUN_ARTIFACTS
    assert "trade_ledger.csv" in COMPRESSIBLE_RUN_ARTIFACTS
    assert "summary_metrics.csv" not in COMPRESSIBLE_RUN_ARTIFACTS
    assert "metadata.json" not in COMPRESSIBLE_RUN_ARTIFACTS
