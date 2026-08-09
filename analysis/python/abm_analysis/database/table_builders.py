"""Build and insert normalised database tables from simulator staging files."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Iterable

import pandas as pd

from abm_analysis.archives import build_run_archive, resolve_artifact_path
from abm_analysis.run_ids import parse_run_id
from abm_analysis.timeseries import read_csv_if_exists

from .constants import (
    AGENT_SNAPSHOT_COLUMNS,
    AGENT_STEP_DIAGNOSTIC_COLUMNS,
    ASSET_TIMESERIES_COLUMNS,
    JSONB_TABLE_COLUMNS,
    MECHANISM_DIAGNOSTIC_COLUMNS,
    STAGING_ARTIFACTS,
    STEP_TIMESERIES_COLUMNS,
    STYLISED_FACT_COLUMNS,
    SUMMARY_METRIC_COLUMNS,
    TRADE_LEDGER_COLUMNS,
)
from .normalisation import (
    _first_text,
    _normalise_table_record,
    _read_json,
    _sanitize_config_text,
    sanitize_metadata_for_database,
)
from .provenance import _hash_run_archive
from .sql import _require_sqlalchemy


def build_run_import_tables(run_dir: Path | str) -> dict[str, pd.DataFrame]:
    """Build normalised import frames for one staged run without connecting."""

    archive = build_run_archive(run_dir)
    run_path = archive.run_dir
    metadata = _read_json(archive.metadata_json)
    config_json = _read_json(run_path / "config.json")
    summary = read_csv_if_exists(archive.summary_metrics_csv)

    parsed_run_id = parse_run_id(archive.run_id)
    summary_row = summary.iloc[0].to_dict() if not summary.empty else {}
    experiment_name = _first_text(
        summary_row.get("experiment_name"),
        metadata.get("experiment_name"),
        run_path.parent.name,
    )
    run_label = _first_text(summary_row.get("run_label"), metadata.get("run_label"), "")
    created_at_local = _first_text(
        summary_row.get("created_at_local"),
        metadata.get("created_at_local"),
        parsed_run_id.get("run_id_created_at_local"),
        "",
    )
    config_hash = _first_text(summary_row.get("config_hash"), metadata.get("config_hash"), "")
    status = _first_text(summary_row.get("status"), metadata.get("status"), "completed")

    run_record = pd.DataFrame(
        [
            {
                "run_id": archive.run_id,
                "experiment_name": experiment_name,
                "run_label": run_label,
                "created_at_local": created_at_local,
                "status": status,
                "config_hash": config_hash,
                "config_json": json.dumps(config_json, sort_keys=True),
                "metadata_json": json.dumps(
                    sanitize_metadata_for_database(metadata),
                    sort_keys=True,
                ),
                "source_config_text": _sanitize_config_text(run_path / "config_used.cfg"),
                "source_archive_sha256": _hash_run_archive(run_path),
            }
        ]
    )

    return {
        "runs": run_record,
        "step_timeseries": _prepare_run_table(
            read_csv_if_exists(archive.step_timeseries_csv),
            archive.run_id,
            STEP_TIMESERIES_COLUMNS,
            table_name="step_timeseries",
            row_index_column="row_index",
        ),
        "asset_timeseries": _prepare_run_table(
            read_csv_if_exists(archive.asset_timeseries_csv),
            archive.run_id,
            ASSET_TIMESERIES_COLUMNS,
            table_name="asset_timeseries",
            row_index_column="row_index",
        ),
        "agent_snapshots": _prepare_run_table(
            read_csv_if_exists(archive.agents_final_csv),
            archive.run_id,
            AGENT_SNAPSHOT_COLUMNS,
            table_name="agent_snapshots",
        ),
        "trade_ledger": _prepare_run_table(
            read_csv_if_exists(archive.trade_ledger_csv),
            archive.run_id,
            TRADE_LEDGER_COLUMNS,
            table_name="trade_ledger",
            generated_index_column="ledger_row_index",
        ),
        "summary_metrics": _prepare_run_table(
            summary,
            archive.run_id,
            SUMMARY_METRIC_COLUMNS,
            table_name="summary_metrics",
        ),
        "stylised_facts": _prepare_run_table(
            read_csv_if_exists(resolve_artifact_path(run_path, "stylised_facts.csv")),
            archive.run_id,
            STYLISED_FACT_COLUMNS,
            table_name="stylised_facts",
            generated_index_column="stylised_row_index",
        ),
        "mechanism_diagnostics": _prepare_optional_diagnostic_table(
            read_csv_if_exists(resolve_artifact_path(run_path, "mechanism_diagnostics.csv")),
            archive.run_id,
            MECHANISM_DIAGNOSTIC_COLUMNS,
            table_name="mechanism_diagnostics",
            required_columns={"row_index", "mechanism_name", "diagnostic_name"},
        ),
        "agent_step_diagnostics": _prepare_optional_diagnostic_table(
            read_csv_if_exists(resolve_artifact_path(run_path, "agent_step_diagnostics.csv")),
            archive.run_id,
            AGENT_STEP_DIAGNOSTIC_COLUMNS,
            table_name="agent_step_diagnostics",
            required_columns={"row_index", "agent_id", "diagnostic_name"},
        ),
    }


def prune_staging_artifacts(run_dir: Path | str) -> None:
    """Delete simulator staging artefacts after successful PostgreSQL import."""

    run_path = Path(run_dir).expanduser().resolve()
    for filename in STAGING_ARTIFACTS:
        for candidate_name in (filename, filename + ".gz"):
            candidate = run_path / candidate_name
            if candidate.exists() and candidate.is_file():
                candidate.unlink()
    logs_dir = run_path / "logs"
    if logs_dir.exists() and logs_dir.is_dir():
        shutil.rmtree(logs_dir)


def _insert_run_tables(connection: Any, import_tables: dict[str, pd.DataFrame]) -> int:
    rows = 0
    rows += _insert_dataframe(
        connection,
        "step_timeseries",
        import_tables["step_timeseries"],
        STEP_TIMESERIES_COLUMNS,
    )
    rows += _insert_dataframe(
        connection,
        "asset_timeseries",
        import_tables["asset_timeseries"],
        ASSET_TIMESERIES_COLUMNS,
    )
    rows += _insert_dataframe(
        connection,
        "agent_snapshots",
        import_tables["agent_snapshots"],
        AGENT_SNAPSHOT_COLUMNS,
    )
    rows += _insert_dataframe(
        connection,
        "trade_ledger",
        import_tables["trade_ledger"],
        TRADE_LEDGER_COLUMNS,
    )
    rows += _insert_dataframe(
        connection,
        "summary_metrics",
        import_tables["summary_metrics"],
        SUMMARY_METRIC_COLUMNS,
    )
    rows += _insert_dataframe(
        connection,
        "stylised_facts",
        import_tables["stylised_facts"],
        STYLISED_FACT_COLUMNS,
    )
    rows += _insert_dataframe(
        connection,
        "mechanism_diagnostics",
        import_tables["mechanism_diagnostics"],
        MECHANISM_DIAGNOSTIC_COLUMNS,
    )
    rows += _insert_dataframe(
        connection,
        "agent_step_diagnostics",
        import_tables["agent_step_diagnostics"],
        AGENT_STEP_DIAGNOSTIC_COLUMNS,
    )
    return rows


def _prepare_run_table(
    data: pd.DataFrame,
    run_id: str,
    columns: Iterable[str],
    *,
    table_name: str,
    row_index_column: str | None = None,
    generated_index_column: str | None = None,
) -> pd.DataFrame:
    columns = tuple(columns)
    if data.empty:
        return pd.DataFrame(columns=columns)
    frame = data.copy()
    frame["run_id"] = run_id
    if row_index_column and row_index_column not in frame.columns:
        frame[row_index_column] = range(len(frame))
    if generated_index_column:
        frame[generated_index_column] = range(len(frame))
    # Columns absent from an older archive are imported as missing values, but a
    # column the importer does not know about must fail loudly: silently
    # dropping it would lose simulator output without any warning. This guards
    # against the C++ writers gaining a column before the Python schema does.
    unexpected_columns = sorted(set(frame.columns).difference(columns))
    if unexpected_columns:
        unexpected_text = ", ".join(unexpected_columns)
        raise ValueError(
            f"Staged {table_name} data contains columns unknown to the database "
            f"schema and cannot be imported without losing data: {unexpected_text}. "
            "Update abm_analysis.database.constants and add a schema migration first."
        )
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame.loc[:, list(columns)]


def _prepare_optional_diagnostic_table(
    data: pd.DataFrame,
    run_id: str,
    columns: Iterable[str],
    *,
    table_name: str,
    required_columns: set[str],
) -> pd.DataFrame:
    """Prepare optional mechanism-level diagnostics without weakening schema checks."""

    columns = tuple(columns)
    if data.empty:
        return pd.DataFrame(columns=columns)
    missing = required_columns.difference(data.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Diagnostic CSV is missing required columns: {missing_text}")
    return _prepare_run_table(data, run_id, columns, table_name=table_name)


# Upper bound on bind parameters per INSERT statement. PostgreSQL's extended
# query protocol rejects statements beyond 65535 parameters; staying an order
# of magnitude below that still batches hundreds of rows per round trip, which
# is what makes thesis-scale trade-ledger imports fast.
_MAX_BIND_PARAMETERS_PER_STATEMENT = 10000


def _insert_dataframe(
    connection: Any,
    table_name: str,
    data: pd.DataFrame,
    columns: Iterable[str],
) -> int:
    """Insert one staged frame using chunked multi-row INSERT statements.

    A single-row statement executed once per record forces one database round
    trip per row, which dominates import time for large trade ledgers. Packing
    many rows into each VALUES clause keeps the same transactional semantics
    while cutting round trips by two to three orders of magnitude.
    """

    if data.empty:
        return 0
    sqlalchemy = _require_sqlalchemy()
    columns = tuple(columns)
    jsonb_columns = JSONB_TABLE_COLUMNS.get(table_name, set())
    column_list = ", ".join(columns)
    records = [
        _normalise_table_record(table_name, record)
        for record in data.loc[:, columns].to_dict("records")
    ]

    rows_per_statement = max(1, _MAX_BIND_PARAMETERS_PER_STATEMENT // len(columns))
    for chunk_start in range(0, len(records), rows_per_statement):
        chunk = records[chunk_start : chunk_start + rows_per_statement]
        value_rows = []
        parameters: dict[str, Any] = {}
        for row_number, record in enumerate(chunk):
            placeholders = []
            for column in columns:
                parameter_name = f"{column}_{row_number}"
                parameters[parameter_name] = record[column]
                if column in jsonb_columns:
                    placeholders.append(f"CAST(:{parameter_name} AS JSONB)")
                else:
                    placeholders.append(f":{parameter_name}")
            value_rows.append("(" + ", ".join(placeholders) + ")")
        connection.execute(
            sqlalchemy.text(
                f"INSERT INTO {table_name} ({column_list}) VALUES {', '.join(value_rows)}"
            ),
            parameters,
        )
    return len(records)
