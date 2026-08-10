"""Run archive import workflows for PostgreSQL-backed ABM analysis data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from abm_analysis.archive.archives import discover_run_directories

from .audit import _insert_import_audit
from .constants import DEFAULT_DATABASE_URL_ENV
from .models import ImportSummary
from .normalisation import _normalise_record
from .schema import apply_schema
from .sql import _require_sqlalchemy, create_database_engine
from .table_builders import (
    _insert_run_tables,
    build_run_import_tables,
    prune_staging_artifacts,
)


def import_run_archive(
    run_dir: Path | str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
    prune_source: bool = False,
) -> ImportSummary:
    """Import one staged simulator run archive into PostgreSQL."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    import_tables = build_run_import_tables(run_dir)
    run_record = import_tables["runs"].iloc[0].to_dict()
    run_id = str(run_record["run_id"])
    experiment_name = str(run_record["experiment_name"])
    source_archive_sha256 = str(run_record.get("source_archive_sha256") or "")

    with engine.begin() as connection:
        apply_schema(connection)
        _upsert_experiment(connection, experiment_name)
        _delete_run(connection, run_id)
        _insert_run_record(connection, run_record)
        rows_imported = _insert_run_tables(connection, import_tables)
        _insert_import_audit(
            connection,
            "run",
            run_id,
            rows_imported,
            source_archive_sha256=source_archive_sha256,
            status="completed",
            message="Run archive imported into PostgreSQL.",
        )

    if prune_source:
        prune_staging_artifacts(Path(run_dir))

    return ImportSummary("run", run_id, rows_imported)


def import_experiment_archives(
    experiment_dir: Path | str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
    prune_source: bool = False,
) -> list[ImportSummary]:
    """Import all run archives under one experiment directory."""

    summaries: list[ImportSummary] = []
    for run_dir in discover_run_directories(experiment_dir):
        summaries.append(
            import_run_archive(
                run_dir,
                database_url,
                database_url_env=database_url_env,
                prune_source=prune_source,
            )
        )
    return summaries


def _upsert_experiment(connection: Any, experiment_name: str) -> None:
    sqlalchemy = _require_sqlalchemy()
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO experiments(experiment_name, imported_at)
            VALUES (:experiment_name, NOW())
            ON CONFLICT (experiment_name)
            DO UPDATE SET imported_at = EXCLUDED.imported_at
            """
        ),
        {"experiment_name": experiment_name},
    )


def _delete_run(connection: Any, run_id: str) -> None:
    sqlalchemy = _require_sqlalchemy()
    connection.execute(
        sqlalchemy.text("DELETE FROM runs WHERE run_id = :run_id"),
        {"run_id": run_id},
    )


def _insert_run_record(connection: Any, record: dict[str, Any]) -> None:
    sqlalchemy = _require_sqlalchemy()
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO runs(
                run_id, experiment_name, run_label, created_at_local, status,
                config_hash, config_json, metadata_json, source_config_text,
                source_archive_sha256, imported_at
            )
            VALUES (
                :run_id, :experiment_name, :run_label, :created_at_local, :status,
                :config_hash, CAST(:config_json AS JSONB), CAST(:metadata_json AS JSONB),
                :source_config_text, :source_archive_sha256, NOW()
            )
            """
        ),
        _normalise_record(record),
    )
