"""SQLAlchemy connection and low-level query helpers."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from .constants import DEFAULT_DATABASE_URL_ENV

def resolve_database_url(
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> str:
    """Resolve the PostgreSQL connection URL from an explicit value or env var."""

    if database_url:
        return database_url
    value = os.environ.get(database_url_env)
    if value:
        return value
    raise RuntimeError(
        f"PostgreSQL connection URL is not configured. Set {database_url_env} "
        "or pass --database-url."
    )

def initialise_database(
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> None:
    """Create or update the PostgreSQL schema used by the ABM analysis layer."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    with engine.begin() as connection:
        from .schema import apply_schema

        apply_schema(connection)

def create_database_engine(
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> Any:
    """Create a SQLAlchemy engine without hard-coding database credentials."""

    sqlalchemy = _require_sqlalchemy()
    return sqlalchemy.create_engine(
        resolve_database_url(database_url, database_url_env=database_url_env),
        future=True,
    )

def _table_count(connection: Any, table_name: str, key_column: str, value: str) -> int:
    sqlalchemy = _require_sqlalchemy()
    return int(
        connection.execute(
            sqlalchemy.text(
                f"SELECT COUNT(*) AS row_count FROM {table_name} WHERE {key_column} = :value"
            ),
            {"value": value},
        ).scalar_one()
    )

def _query_dataframe(connection: Any, statement: str, params: dict[str, Any]) -> pd.DataFrame:
    sqlalchemy = _require_sqlalchemy()
    return pd.read_sql_query(sqlalchemy.text(statement), connection, params=params)

def _fetch_one(
    connection: Any,
    statement: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    sqlalchemy = _require_sqlalchemy()
    row = connection.execute(sqlalchemy.text(statement), params).mappings().first()
    return dict(row) if row is not None else None

def _fetch_all(
    connection: Any,
    statement: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    sqlalchemy = _require_sqlalchemy()
    return [
        dict(row)
        for row in connection.execute(sqlalchemy.text(statement), params).mappings().all()
    ]

def _require_sqlalchemy() -> Any:
    try:
        import sqlalchemy
    except ImportError as error:  # pragma: no cover - depends on local environment.
        raise RuntimeError(
            "PostgreSQL support requires SQLAlchemy. Install project dependencies with "
            "`.venv/bin/pip install -r requirements.txt`."
        ) from error
    return sqlalchemy
