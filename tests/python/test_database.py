from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from abm_analysis.archive.benchmarks import load_benchmark_timeseries
from abm_analysis.database import (
    CURRENT_SCHEMA_VERSION,
    REQUIRED_SCHEMA_INDEXES,
    SCHEMA_TABLE_NAMES,
    _build_benchmark_metadata_record,
    _missing_benchmark_metadata_fields,
    build_run_import_tables,
    import_run_archive,
    initialise_database,
    resolve_database_url,
    schema_migrations,
    schema_sql_statements,
)


def test_schema_contains_required_postgresql_tables() -> None:
    ddl = "\n".join(schema_sql_statements()).lower()

    for table_name in SCHEMA_TABLE_NAMES:
        assert f"create table if not exists {table_name}" in ddl
    for index_name in REQUIRED_SCHEMA_INDEXES:
        assert f"create index if not exists {index_name}" in ddl
    assert "jsonb" in ddl
    assert "schema_migrations" in ddl
    assert "source_archive_sha256" in ddl
    assert "final_wealth_gini_coefficient" in ddl
    assert "allocative_efficiency" in ddl
    assert "mean_allocative_efficiency" in ddl
    assert "importer_version" in ddl
    assert "boolean" in ddl


def test_schema_migrations_are_ordered_and_current() -> None:
    migrations = schema_migrations()
    versions = [version for version, _, _ in migrations]

    assert versions == sorted(versions)
    assert versions[-1] == CURRENT_SCHEMA_VERSION


def test_resolve_database_url_reads_named_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABM_UNIT_DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")

    assert (
        resolve_database_url(database_url_env="ABM_UNIT_DATABASE_URL")
        == "postgresql+psycopg://user:pass@localhost/db"
    )
    assert (
        resolve_database_url(
            "postgresql+psycopg://override/db",
            database_url_env="ABM_UNIT_DATABASE_URL",
        )
        == "postgresql+psycopg://override/db"
    )


def test_run_import_tables_remove_path_like_provenance(tmp_path: Path) -> None:
    run_dir = _write_minimal_run(tmp_path)

    tables = build_run_import_tables(run_dir)
    run_record = tables["runs"].iloc[0]
    metadata_json = json.loads(str(run_record["metadata_json"]))

    assert run_record["run_id"] == run_dir.name
    assert run_record["experiment_name"] == "database_test"
    assert "outputs" not in metadata_json
    assert "source_config_path" not in metadata_json
    assert "simulation_csv_output" not in str(run_record["source_config_text"])
    assert tables["step_timeseries"]["run_id"].eq(run_dir.name).all()
    assert "wealth_gini_coefficient" in tables["step_timeseries"].columns
    assert tables["step_timeseries"]["wealth_gini_coefficient"].dropna().tolist() == [0.0, 0.1]
    assert "allocative_efficiency" in tables["step_timeseries"].columns
    assert tables["step_timeseries"]["allocative_efficiency"].dropna().tolist() == [0.8, 0.5]
    assert "final_wealth_gini_coefficient" in tables["summary_metrics"].columns
    assert float(tables["summary_metrics"]["final_wealth_gini_coefficient"].iloc[0]) == (
        pytest.approx(0.0357142857)
    )
    assert float(tables["summary_metrics"]["mean_allocative_efficiency"].iloc[0]) == (
        pytest.approx(0.65)
    )
    assert tables["trade_ledger"]["ledger_row_index"].tolist() == [0, 1]
    assert len(tables["summary_metrics"]) == 1
    assert len(str(run_record["source_archive_sha256"])) == 64
    assert len(tables["mechanism_diagnostics"]) == 1
    assert len(tables["agent_step_diagnostics"]) == 1


def test_legacy_summary_without_final_wealth_gini_still_imports(tmp_path: Path) -> None:
    run_dir = _write_minimal_run(tmp_path)
    summary_path = run_dir / "summary_metrics.csv"
    summary = pd.read_csv(summary_path).drop(columns=["final_wealth_gini_coefficient"])
    summary.to_csv(summary_path, index=False)

    tables = build_run_import_tables(run_dir)

    assert "final_wealth_gini_coefficient" in tables["summary_metrics"].columns
    assert pd.isna(tables["summary_metrics"]["final_wealth_gini_coefficient"].iloc[0])


def test_benchmark_metadata_record_hashes_source_and_reports_missing_fields(
    tmp_path: Path,
) -> None:
    benchmark_path = tmp_path / "02_SPX.csv"
    benchmark_path.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-01,100,101,99,100,1000\n"
        "2026-01-02,100,102,99,101,1200\n",
        encoding="utf-8",
    )
    benchmark = load_benchmark_timeseries(benchmark_path)

    record = _build_benchmark_metadata_record(
        benchmark,
        source_path=benchmark_path,
        manifest_record={"display_name": "S&P 500", "source_vendor": "unit_test"},
    )

    assert record["benchmark_id"] == "SPX"
    assert record["display_name"] == "S&P 500"
    assert record["date_start"] == "2026-01-01"
    assert record["date_end"] == "2026-01-02"
    assert len(str(record["raw_file_sha256"])) == 64
    assert _missing_benchmark_metadata_fields(record) == []
    assert "raw_file_sha256" in _missing_benchmark_metadata_fields({"benchmark_id": "SPX"})


@pytest.mark.skipif(
    not os.environ.get("ABM_TEST_DATABASE_URL"),
    reason="Set ABM_TEST_DATABASE_URL to run PostgreSQL integration tests.",
)
def test_postgresql_import_is_idempotent(tmp_path: Path) -> None:
    run_dir = _write_minimal_run(tmp_path)
    database_url = os.environ["ABM_TEST_DATABASE_URL"]

    initialise_database(database_url)
    first = import_run_archive(run_dir, database_url)
    second = import_run_archive(run_dir, database_url)

    assert first.rows_imported == second.rows_imported
    assert first.identifier == run_dir.name


def _write_minimal_run(tmp_path: Path) -> Path:
    run_id = "20260610120000_1_0_1_1_2_3_1_0_20_99"
    run_dir = tmp_path / "database_test" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "logs").mkdir()

    pd.DataFrame(
        {
            "row_index": [0, 1, 2],
            "phase": ["initial", "simulation", "simulation"],
            "simulation_step": [None, 1, 2],
            "market_price": [100.0, 101.0, 99.5],
            "fundamental_price": [100.0, 100.5, 100.2],
            "submitted_orders": [None, 2, 3],
            "net_demand": [None, 1.0, -0.5],
            "traded_volume": [None, 10.0, 12.0],
            "raw_return": [None, 0.01, -0.0149],
            "log_return": [None, 0.00995, -0.01496],
            "realized_allocative_surplus": [None, 80.0, 25.0],
            "maximum_allocative_surplus": [None, 100.0, 50.0],
            "allocative_efficiency": [None, 0.8, 0.5],
            "wealth_gini_coefficient": [None, 0.0, 0.1],
        }
    ).to_csv(run_dir / "step_timeseries.csv", index=False)
    pd.DataFrame(
        {
            "agent_id": [1, 2],
            "initial_strategy_type": ["fundamentalist", "chartist"],
            "current_strategy_type": ["fundamentalist", "chartist"],
            "final_cash": [1000.0, 900.0],
            "final_stock": [5.0, 4.0],
            "number_of_trades": [1, 1],
            "traded_volume": [10.0, 10.0],
            "final_wealth": [1500.0, 1300.0],
        }
    ).to_csv(run_dir / "agents_final.csv", index=False)
    pd.DataFrame(
        {
            "trade_id": [1, 1],
            "time": [1, 1],
            "agent_id": [1, 2],
            "counterparty_agent_id": [2, 1],
            "side": ["BUY", "SELL"],
            "price": [101.0, 101.0],
            "qty": [10.0, 10.0],
            "asset": ["asset", "asset"],
        }
    ).to_csv(run_dir / "trade_ledger.csv", index=False)
    pd.DataFrame(
        {
            "run_id": [run_id],
            "experiment_name": ["database_test"],
            "run_label": ["unit"],
            "created_at_local": ["2026-06-10T12:00:00"],
            "status": ["completed"],
            "config_hash": ["abc123"],
            "seed": [99],
            "time_steps": [20],
            "num_fundamentalists": [2],
            "num_chartists": [3],
            "num_buy_and_hold_agents": [0],
            "num_noise_traders": [1],
            "prospect_theory_enabled": [1],
            "prospect_heterogeneity_enabled": [0],
            "social_enabled": [1],
            "short_selling_enabled": [1],
            "final_market_price": [99.5],
            "final_wealth_gini_coefficient": [0.0357142857],
            "mean_allocative_efficiency": [0.65],
            "allocative_efficiency_observations": [2],
            "mean_log_return": [-0.0025],
            "log_return_std_dev": [0.01],
            "excess_kurtosis": [0.2],
        }
    ).to_csv(run_dir / "summary_metrics.csv", index=False)
    pd.DataFrame(
        {
            "stylised_fact": ["Fat tails"],
            "diagnostic": ["Excess kurtosis"],
            "metric_value": [0.2],
            "screening_rule": ["Positive excess kurtosis"],
            "conclusion": ["Consistent"],
        }
    ).to_csv(run_dir / "stylised_facts.csv", index=False)
    pd.DataFrame(
        {
            "row_index": [1],
            "phase": ["simulation"],
            "simulation_step": [1],
            "mechanism_name": ["prospect_theory"],
            "diagnostic_name": ["active_agent_share"],
            "diagnostic_value": [0.5],
            "diagnostic_text": ["unit"],
        }
    ).to_csv(run_dir / "mechanism_diagnostics.csv", index=False)
    pd.DataFrame(
        {
            "row_index": [1],
            "agent_id": [1],
            "phase": ["simulation"],
            "simulation_step": [1],
            "diagnostic_name": ["reference_point"],
            "diagnostic_value": [100.0],
            "diagnostic_text": ["unit"],
        }
    ).to_csv(run_dir / "agent_step_diagnostics.csv", index=False)
    (run_dir / "config.json").write_text(
        json.dumps({"schema_version": 5, "simulation": {"seed": 99}}),
        encoding="utf-8",
    )
    (run_dir / "metadata.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "experiment_name": "database_test",
                "run_label": "unit",
                "created_at_local": "2026-06-10T12:00:00",
                "config_hash": "abc123",
                "source_config_path": "/local/machine/config/simulation.cfg",
                "outputs": {"step_timeseries_csv": "step_timeseries.csv"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "config_used.cfg").write_text(
        "seed = 99\nsimulation_csv_output = ../data/latest/step_timeseries.csv\n",
        encoding="utf-8",
    )
    (run_dir / "logs" / "run.log").write_text("completed\n", encoding="utf-8")
    return run_dir
