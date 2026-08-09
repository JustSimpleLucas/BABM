"""Import-audit recording for PostgreSQL-backed ABM analysis data."""

from __future__ import annotations

from typing import Any

from .constants import CURRENT_SCHEMA_VERSION
from .provenance import _current_git_commit, _importer_version
from .sql import _require_sqlalchemy


def _insert_import_audit(
    connection: Any,
    item_type: str,
    identifier: str,
    rows_imported: int,
    *,
    source_archive_sha256: str | None = None,
    status: str = "completed",
    message: str | None = None,
) -> None:
    sqlalchemy = _require_sqlalchemy()
    connection.execute(
        sqlalchemy.text(
            """
            INSERT INTO import_audit(
                item_type, identifier, rows_imported, schema_version,
                importer_version, git_commit, source_archive_sha256, status, message
            )
            VALUES (
                :item_type, :identifier, :rows_imported, :schema_version,
                :importer_version, :git_commit, :source_archive_sha256, :status, :message
            )
            """
        ),
        {
            "item_type": item_type,
            "identifier": identifier,
            "rows_imported": rows_imported,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "importer_version": _importer_version(),
            "git_commit": _current_git_commit(),
            "source_archive_sha256": source_archive_sha256,
            "status": status,
            "message": message,
        },
    )
