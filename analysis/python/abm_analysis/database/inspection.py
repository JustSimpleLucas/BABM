"""Read-only inspection helpers for imported run provenance."""

from __future__ import annotations

from typing import Any

from .constants import DEFAULT_DATABASE_URL_ENV
from .schema import apply_schema, _database_schema_version
from .sql import _fetch_all, _fetch_one, _table_count, create_database_engine

def inspect_database_run(
    run_id: str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> dict[str, Any]:
    """Return a compact provenance and row-count summary for one imported run."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    with engine.begin() as connection:
        apply_schema(connection)
        run_row = _fetch_one(
            connection,
            """
            SELECT run_id, experiment_name, run_label, created_at_local, status,
                   config_hash, source_archive_sha256, imported_at
            FROM runs
            WHERE run_id = :run_id
            """,
            {"run_id": run_id},
        )
        if run_row is None:
            raise FileNotFoundError(f"Run was not found in PostgreSQL: {run_id}")

        row_counts = {
            table_name: _table_count(connection, table_name, "run_id", run_id)
            for table_name in (
                "step_timeseries",
                "agent_snapshots",
                "trade_ledger",
                "summary_metrics",
                "stylised_facts",
                "mechanism_diagnostics",
                "agent_step_diagnostics",
            )
        }
        audit_row = _fetch_one(
            connection,
            """
            SELECT rows_imported, schema_version, importer_version, git_commit,
                   source_archive_sha256, status, message, imported_at
            FROM import_audit
            WHERE item_type = 'run'
              AND identifier = :run_id
            ORDER BY imported_at DESC, audit_id DESC
            LIMIT 1
            """,
            {"run_id": run_id},
        )
        benchmark_rows = _fetch_all(
            connection,
            """
            SELECT benchmark_id
            FROM benchmark_metadata
            ORDER BY benchmark_id
            """,
            {},
        )
        return {
            "schema_version": _database_schema_version(connection),
            "run": run_row,
            "row_counts": row_counts,
            "latest_import_audit": audit_row or {},
            "available_benchmarks": [str(row["benchmark_id"]) for row in benchmark_rows],
        }
