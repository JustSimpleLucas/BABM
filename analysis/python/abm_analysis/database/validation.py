"""Database validation checks for thesis-scale ABM archives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from abm_analysis.benchmarks import discover_benchmark_files, infer_benchmark_id, load_benchmark_timeseries
from abm_analysis.data import (
    build_run_archive,
    discover_run_directories,
    read_csv_if_exists,
    resolve_artifact_path,
)

from .constants import (
    BENCHMARK_METADATA_REQUIRED_FIELDS,
    CURRENT_SCHEMA_VERSION,
    DEFAULT_DATABASE_URL_ENV,
    REQUIRED_SCHEMA_INDEXES,
)
from .normalisation import _normalise_selected_benchmark_ids
from .provenance import _file_sha256, _hash_run_archive
from .schema import apply_schema, _database_schema_version, _schema_index_exists
from .sql import _fetch_one, _table_count, create_database_engine

def validate_database_imports(
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
    experiments_root: Path | str | None = None,
    benchmark_dir: Path | str | None = None,
    benchmark_series: str | list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Compare source CSV row counts with PostgreSQL row counts."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    rows: list[dict[str, object]] = []
    with engine.begin() as connection:
        apply_schema(connection)
        rows.extend(_validate_schema_health(connection))
        if experiments_root is not None:
            for experiment_dir in sorted(Path(experiments_root).expanduser().resolve().iterdir()):
                if not experiment_dir.is_dir():
                    continue
                for run_dir in discover_run_directories(experiment_dir):
                    rows.extend(_validate_run_counts(connection, run_dir))
        if benchmark_dir is not None:
            rows.extend(
                _validate_benchmark_counts(
                    connection,
                    benchmark_dir,
                    benchmark_series=benchmark_series,
                )
            )
    return pd.DataFrame(rows)

def _validate_run_counts(connection: Any, run_dir: Path) -> list[dict[str, object]]:
    archive = build_run_archive(run_dir)
    source_counts = {
        "step_timeseries": len(read_csv_if_exists(archive.step_timeseries_csv)),
        "agent_snapshots": len(read_csv_if_exists(archive.agents_final_csv)),
        "trade_ledger": len(read_csv_if_exists(archive.trade_ledger_csv)),
        "summary_metrics": len(read_csv_if_exists(archive.summary_metrics_csv)),
        "stylised_facts": len(
            read_csv_if_exists(resolve_artifact_path(archive.run_dir, "stylised_facts.csv"))
        ),
        "mechanism_diagnostics": len(
            read_csv_if_exists(
                resolve_artifact_path(archive.run_dir, "mechanism_diagnostics.csv")
            )
        ),
        "agent_step_diagnostics": len(
            read_csv_if_exists(
                resolve_artifact_path(archive.run_dir, "agent_step_diagnostics.csv")
            )
        ),
    }
    rows = []
    for table_name, source_count in source_counts.items():
        database_count = _table_count(connection, table_name, "run_id", archive.run_id)
        rows.append(
            {
                "item_type": table_name,
                "identifier": archive.run_id,
                "source_rows": source_count,
                "database_rows": database_count,
                "status": "matched" if source_count == database_count else "mismatch",
            }
        )
    source_hash = _hash_run_archive(archive.run_dir)
    database_hash = _latest_import_hash(connection, "run", archive.run_id)
    rows.append(
        {
            "item_type": "run_archive_hash",
            "identifier": archive.run_id,
            "source_value": source_hash,
            "database_value": database_hash or "",
            "status": "matched" if source_hash and source_hash == database_hash else "mismatch",
        }
    )
    return rows

def _validate_schema_health(connection: Any) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    database_version = _database_schema_version(connection)
    rows.append(
        {
            "item_type": "schema_version",
            "identifier": "current",
            "source_rows": CURRENT_SCHEMA_VERSION,
            "database_rows": database_version,
            "status": "matched" if database_version >= CURRENT_SCHEMA_VERSION else "mismatch",
        }
    )
    for index_name in REQUIRED_SCHEMA_INDEXES:
        exists = _schema_index_exists(connection, index_name)
        rows.append(
            {
                "item_type": "schema_index",
                "identifier": index_name,
                "source_value": "required",
                "database_value": "present" if exists else "missing",
                "status": "matched" if exists else "mismatch",
            }
        )
    return rows

def _validate_benchmark_counts(
    connection: Any,
    benchmark_dir: Path | str,
    *,
    benchmark_series: str | list[str] | tuple[str, ...] | None,
) -> list[dict[str, object]]:
    rows = []
    selected = _normalise_selected_benchmark_ids(benchmark_series)
    for path in discover_benchmark_files(benchmark_dir, benchmark_series):
        benchmark_id = infer_benchmark_id(path)
        if selected is not None and benchmark_id not in selected:
            continue
        benchmark = load_benchmark_timeseries(path)
        source_count = len(benchmark.data)
        database_count = _table_count(
            connection,
            "benchmark_prices",
            "benchmark_id",
            benchmark_id,
        )
        rows.append(
            {
                "item_type": "benchmark_prices",
                "identifier": benchmark_id,
                "source_rows": source_count,
                "database_rows": database_count,
                "status": "matched" if source_count == database_count else "mismatch",
            }
        )
        source_hash = _file_sha256(path)
        database_metadata = _fetch_one(
            connection,
            """
            SELECT raw_file_sha256, source_file, date_start, date_end,
                   price_column, return_definition
            FROM benchmark_metadata
            WHERE benchmark_id = :benchmark_id
            """,
            {"benchmark_id": benchmark_id},
        )
        missing_fields = _missing_benchmark_metadata_fields(database_metadata)
        database_hash = (
            str(database_metadata.get("raw_file_sha256") or "")
            if database_metadata
            else ""
        )
        rows.append(
            {
                "item_type": "benchmark_metadata",
                "identifier": benchmark_id,
                "source_value": source_hash,
                "database_value": database_hash,
                "message": ", ".join(missing_fields),
                "status": (
                    "matched"
                    if database_metadata and not missing_fields and source_hash == database_hash
                    else "mismatch"
                ),
            }
        )
    return rows

def _latest_import_hash(connection: Any, item_type: str, identifier: str) -> str | None:
    row = _fetch_one(
        connection,
        """
        SELECT source_archive_sha256
        FROM import_audit
        WHERE item_type = :item_type
          AND identifier = :identifier
          AND status = 'completed'
        ORDER BY imported_at DESC, audit_id DESC
        LIMIT 1
        """,
        {"item_type": item_type, "identifier": identifier},
    )
    return str(row["source_archive_sha256"]) if row and row.get("source_archive_sha256") else None

def _missing_benchmark_metadata_fields(record: dict[str, Any] | None) -> list[str]:
    if record is None:
        return list(BENCHMARK_METADATA_REQUIRED_FIELDS)
    missing = []
    for field_name in BENCHMARK_METADATA_REQUIRED_FIELDS:
        value = record.get(field_name)
        if value is None or str(value).strip() == "":
            missing.append(field_name)
    return missing
