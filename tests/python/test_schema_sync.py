"""Cross-language schema drift checks between the C++ writers and Python.

Each C++ writer now declares its columns once, as a `CsvColumn` table pairing
every header name with the function that writes its value, so the header line
and the value line cannot disagree within the writer. The Python side still
spells the layout out separately — the required-column sets used for archive
validation and the PostgreSQL column tuples used for import — because those
encode different contracts (a minimum subset, and a typed load order). That
explicitness only stays safe if drift fails a test instead of silently dropping
simulator output during database import, so these tests read the column tables
straight out of the C++ sources. No build step is required.
"""

from __future__ import annotations

from pathlib import Path
import re

from abm_analysis.archive.archives import (
    REQUIRED_AGENT_FINAL_COLUMNS,
    REQUIRED_ASSET_TIMESERIES_COLUMNS,
    REQUIRED_STEP_TIMESERIES_COLUMNS,
    REQUIRED_SUMMARY_METRICS_COLUMNS,
    REQUIRED_TRADE_LEDGER_COLUMNS,
)
from abm_analysis.database.constants import (
    AGENT_SNAPSHOT_COLUMNS,
    ASSET_TIMESERIES_COLUMNS,
    BOOLEAN_TABLE_COLUMNS,
    COUNT_TABLE_COLUMNS,
    PROTAGONIST_TIMESERIES_COLUMNS,
    STEP_TIMESERIES_COLUMNS,
    STYLISED_FACT_COLUMNS,
    SUMMARY_METRIC_COLUMNS,
    TRADE_LEDGER_COLUMNS,
)
from abm_analysis.database.schema import schema_sql_statements


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_SOURCE_DIR = REPOSITORY_ROOT / "src" / "Output"

# The `constexpr CsvColumn<Row> kColumns[] = { ... };` table in one writer.
_COLUMN_TABLE = re.compile(
    r"constexpr\s+CsvColumn<\w+>\s+kColumns\[\]\s*=\s*\{(.*?)\n\};",
    re.DOTALL,
)
# The header name opening each `{"name", [](...)...}` entry.
_COLUMN_NAME = re.compile(r'\{\s*"([a-z0-9_]+)"\s*,')


def _extract_csv_header_columns(source_file: Path) -> tuple[str, ...]:
    """Return the column names, in order, from one C++ writer's column table.

    The table is the writer's single source of truth: the same entries produce
    the header line and the value line, so reading it here checks the Python
    copies against exactly what the simulator writes.
    """

    text = source_file.read_text(encoding="utf-8")
    table = _COLUMN_TABLE.search(text)
    if table is None:
        raise AssertionError(f"No CsvColumn table found in {source_file}")
    names = _COLUMN_NAME.findall(table.group(1))
    if not names:
        raise AssertionError(f"CsvColumn table in {source_file} declares no columns")
    return tuple(names)


def test_step_timeseries_writer_matches_database_columns() -> None:
    header = _extract_csv_header_columns(
        OUTPUT_SOURCE_DIR / "StepTimeseriesCsvWriter.cpp"
    )

    assert ("run_id", *header) == STEP_TIMESERIES_COLUMNS
    assert REQUIRED_STEP_TIMESERIES_COLUMNS.issubset(header)


def test_asset_timeseries_writer_matches_database_columns() -> None:
    header = _extract_csv_header_columns(
        OUTPUT_SOURCE_DIR / "AssetTimeseriesCsvWriter.cpp"
    )

    assert ("run_id", *header) == ASSET_TIMESERIES_COLUMNS
    assert REQUIRED_ASSET_TIMESERIES_COLUMNS.issubset(header)


def test_agent_snapshot_writer_matches_database_columns() -> None:
    header = _extract_csv_header_columns(
        OUTPUT_SOURCE_DIR / "AgentSnapshotCsvWriter.cpp"
    )

    assert ("run_id", *header) == AGENT_SNAPSHOT_COLUMNS
    assert REQUIRED_AGENT_FINAL_COLUMNS.issubset(header)


def test_protagonist_timeseries_writer_matches_database_columns() -> None:
    header = _extract_csv_header_columns(
        OUTPUT_SOURCE_DIR / "ProtagonistTimeseriesCsvWriter.cpp"
    )

    assert ("run_id", *header) == PROTAGONIST_TIMESERIES_COLUMNS


def test_trade_ledger_writer_matches_database_columns() -> None:
    header = _extract_csv_header_columns(
        OUTPUT_SOURCE_DIR / "TradeLedgerCsvWriter.cpp"
    )

    assert ("run_id", "ledger_row_index", *header) == TRADE_LEDGER_COLUMNS
    assert REQUIRED_TRADE_LEDGER_COLUMNS.issubset(header)


def test_summary_metrics_writer_matches_database_columns() -> None:
    header = _extract_csv_header_columns(
        OUTPUT_SOURCE_DIR / "RunSummaryCsvWriter.cpp"
    )

    assert header == SUMMARY_METRIC_COLUMNS
    assert REQUIRED_SUMMARY_METRICS_COLUMNS.issubset(header)


def test_stylised_fact_writer_matches_database_columns() -> None:
    header = _extract_csv_header_columns(
        OUTPUT_SOURCE_DIR / "StylisedFactCsvWriter.cpp"
    )

    assert ("run_id", "stylised_row_index", *header) == STYLISED_FACT_COLUMNS


def test_every_import_column_exists_in_schema_ddl() -> None:
    """Every import column must appear in the PostgreSQL DDL statements."""

    ddl = "\n".join(schema_sql_statements()).lower()
    for table_columns in (
        STEP_TIMESERIES_COLUMNS,
        ASSET_TIMESERIES_COLUMNS,
        AGENT_SNAPSHOT_COLUMNS,
        TRADE_LEDGER_COLUMNS,
        SUMMARY_METRIC_COLUMNS,
        STYLISED_FACT_COLUMNS,
        PROTAGONIST_TIMESERIES_COLUMNS,
    ):
        for column in table_columns:
            assert re.search(rf"\b{re.escape(column)}\b", ddl), (
                f"Column {column} is missing from the schema DDL"
            )


def test_type_override_maps_reference_known_columns() -> None:
    """Boolean and count overrides must name real import columns."""

    known_columns = {
        "step_timeseries": set(STEP_TIMESERIES_COLUMNS),
        "asset_timeseries": set(ASSET_TIMESERIES_COLUMNS),
        "agent_snapshots": set(AGENT_SNAPSHOT_COLUMNS),
        "trade_ledger": set(TRADE_LEDGER_COLUMNS),
        "summary_metrics": set(SUMMARY_METRIC_COLUMNS),
        "protagonist_timeseries": set(PROTAGONIST_TIMESERIES_COLUMNS),
    }
    for override_map in (BOOLEAN_TABLE_COLUMNS, COUNT_TABLE_COLUMNS):
        for table_name, columns in override_map.items():
            assert table_name in known_columns
            unknown = columns.difference(known_columns[table_name])
            assert not unknown, f"{table_name} overrides unknown columns: {unknown}"
    for table_name, boolean_columns in BOOLEAN_TABLE_COLUMNS.items():
        overlap = boolean_columns.intersection(
            COUNT_TABLE_COLUMNS.get(table_name, set())
        )
        assert not overlap, f"{table_name} columns typed as both bool and count: {overlap}"
