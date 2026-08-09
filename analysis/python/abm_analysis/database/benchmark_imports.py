"""Benchmark-series import workflows for PostgreSQL-backed ABM analysis data."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from abm_analysis.benchmarks import (
    BenchmarkSeries,
    discover_benchmark_files,
    infer_benchmark_id,
    load_benchmark_timeseries_map,
)

from .audit import _insert_import_audit
from .constants import (
    BENCHMARK_METADATA_COLUMNS,
    BENCHMARK_PRICE_COLUMNS,
    DEFAULT_DATABASE_URL_ENV,
)
from .models import ImportSummary
from .normalisation import _json_safe_record
from .provenance import _file_sha256, _repository_root
from .run_imports import import_experiment_archives
from .schema import apply_schema
from .sql import _require_sqlalchemy, create_database_engine
from .table_builders import _insert_dataframe


def import_benchmark_directory(
    benchmark_dir: Path | str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
    benchmark_series: str | list[str] | tuple[str, ...] | None = None,
) -> list[ImportSummary]:
    """Import normalised empirical benchmark CSVs into PostgreSQL."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    benchmark_paths = {
        infer_benchmark_id(path): path
        for path in discover_benchmark_files(benchmark_dir, benchmark_series)
    }
    benchmark_metadata = _load_benchmark_metadata_manifest(benchmark_dir)
    benchmarks = load_benchmark_timeseries_map(benchmark_dir, benchmark_series)
    summaries: list[ImportSummary] = []

    with engine.begin() as connection:
        apply_schema(connection)
        for benchmark in benchmarks.values():
            source_path = benchmark_paths.get(benchmark.benchmark_id)
            metadata_record = _build_benchmark_metadata_record(
                benchmark,
                source_path=source_path,
                manifest_record=benchmark_metadata.get(benchmark.benchmark_id, {}),
            )
            rows_imported = _replace_benchmark(connection, benchmark, metadata_record)
            _insert_import_audit(
                connection,
                "benchmark",
                benchmark.benchmark_id,
                rows_imported,
                source_archive_sha256=str(metadata_record.get("raw_file_sha256") or ""),
                status="completed",
                message="Benchmark series imported into PostgreSQL.",
            )
            summaries.append(
                ImportSummary("benchmark", benchmark.benchmark_id, rows_imported)
            )

    return summaries


def import_all_data(
    experiments_root: Path | str,
    benchmark_dir: Path | str | None,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
    benchmark_series: str | list[str] | tuple[str, ...] | None = None,
    prune_source: bool = False,
) -> list[ImportSummary]:
    """Import every discovered experiment run and selected benchmark CSV."""

    summaries: list[ImportSummary] = []
    experiments_path = Path(experiments_root).expanduser().resolve()
    for experiment_dir in sorted(path for path in experiments_path.iterdir() if path.is_dir()):
        summaries.extend(
            import_experiment_archives(
                experiment_dir,
                database_url,
                database_url_env=database_url_env,
                prune_source=prune_source,
            )
        )
    if benchmark_dir is not None:
        summaries.extend(
            import_benchmark_directory(
                benchmark_dir,
                database_url,
                database_url_env=database_url_env,
                benchmark_series=benchmark_series,
            )
        )
    return summaries


def _replace_benchmark(
    connection: Any,
    benchmark: BenchmarkSeries,
    metadata_record: dict[str, Any],
) -> int:
    sqlalchemy = _require_sqlalchemy()
    connection.execute(
        sqlalchemy.text("DELETE FROM benchmark_series WHERE benchmark_id = :benchmark_id"),
        {"benchmark_id": benchmark.benchmark_id},
    )
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO benchmark_series(benchmark_id, source_file, imported_at)
            VALUES (:benchmark_id, :source_file, NOW())
            """
        ),
        {
            "benchmark_id": benchmark.benchmark_id,
            "source_file": benchmark.source_file,
        },
    )
    prices = _benchmark_price_frame(benchmark)
    rows = _insert_dataframe(connection, "benchmark_prices", prices, BENCHMARK_PRICE_COLUMNS)
    rows += _insert_dataframe(
        connection,
        "benchmark_metadata",
        pd.DataFrame([metadata_record]),
        BENCHMARK_METADATA_COLUMNS,
    )
    return rows


def _benchmark_price_frame(benchmark: BenchmarkSeries) -> pd.DataFrame:
    data = benchmark.data.copy()
    frame = pd.DataFrame(
        {
            "benchmark_id": benchmark.benchmark_id,
            "row_index": range(len(data)),
            "observation_date": data.get("Date"),
            "open_price": data.get("Open"),
            "high_price": data.get("High"),
            "low_price": data.get("Low"),
            "close_price": data.get("Close"),
            "volume": data.get("Volume"),
            "market_price": data.get("market_price"),
            "traded_volume": data.get("traded_volume"),
            "computed_log_return": data.get("computed_log_return"),
            "raw_row_json": [
                json.dumps(_json_safe_record(row), sort_keys=True)
                for row in data.to_dict("records")
            ],
        }
    )
    return frame.loc[:, list(BENCHMARK_PRICE_COLUMNS)]


def _load_benchmark_metadata_manifest(
    benchmark_dir: Path | str,
) -> dict[str, dict[str, Any]]:
    """Load optional benchmark provenance metadata keyed by benchmark ID."""

    benchmark_path = Path(benchmark_dir).expanduser().resolve()
    candidates = [
        benchmark_path / "manifest.csv",
        _repository_root() / "config" / "benchmarks" / "manifest.csv",
    ]
    manifest_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if manifest_path is None:
        return {}

    manifest = pd.read_csv(manifest_path)
    if "benchmark_id" not in manifest.columns:
        raise KeyError(f"Benchmark manifest is missing required column: {manifest_path}")

    records: dict[str, dict[str, Any]] = {}
    for record in manifest.to_dict("records"):
        benchmark_id = str(record.get("benchmark_id", "")).strip().upper()
        if benchmark_id:
            records[benchmark_id] = _json_safe_record(record)
    return records


def _build_benchmark_metadata_record(
    benchmark: BenchmarkSeries,
    *,
    source_path: Path | None,
    manifest_record: dict[str, Any],
) -> dict[str, Any]:
    data = benchmark.data
    date_values = data["Date"] if "Date" in data.columns else pd.Series(dtype=object)
    dates = pd.to_datetime(date_values, errors="coerce")
    inferred_start = dates.min().date().isoformat() if dates.notna().any() else None
    inferred_end = dates.max().date().isoformat() if dates.notna().any() else None

    def manifest_text(column: str, default: object = "") -> object:
        value = manifest_record.get(column)
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        text = str(value).strip()
        return text if text else default

    return {
        "benchmark_id": benchmark.benchmark_id,
        "display_name": manifest_text("display_name", benchmark.benchmark_id),
        "asset_class": manifest_text("asset_class"),
        "source_vendor": manifest_text("source_vendor"),
        "source_url_or_dataset": manifest_text("source_url_or_dataset"),
        "source_file": benchmark.source_file,
        "date_start": manifest_text("date_start", inferred_start),
        "date_end": manifest_text("date_end", inferred_end),
        "frequency": manifest_text("frequency", "daily"),
        "timezone": manifest_text("timezone"),
        "price_column": manifest_text("price_column", "Close"),
        "return_definition": manifest_text(
            "return_definition",
            "close_to_close_log_return",
        ),
        "cleaning_notes": manifest_text(
            "cleaning_notes",
            "Dates parsed, rows sorted ascending, invalid dates removed, "
            "and close-to-close log returns computed by abm_analysis.",
        ),
        "raw_file_sha256": _file_sha256(source_path)
        or manifest_text("raw_file_sha256"),
        "crisis_regime_label": manifest_text("crisis_regime_label"),
        "license_or_access_note": manifest_text("license_or_access_note"),
    }
