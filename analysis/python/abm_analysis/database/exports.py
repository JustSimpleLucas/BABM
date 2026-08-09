"""Export and query workflows from PostgreSQL back to analysis archives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from abm_analysis.data import normalise_manifest_schema, parse_run_id

from .constants import (
    AGENT_SNAPSHOT_COLUMNS,
    AGENT_STEP_DIAGNOSTIC_COLUMNS,
    BENCHMARK_PRICE_COLUMNS,
    DEFAULT_DATABASE_URL_ENV,
    MECHANISM_DIAGNOSTIC_COLUMNS,
    STEP_TIMESERIES_COLUMNS,
    STYLISED_FACT_COLUMNS,
    SUMMARY_METRIC_COLUMNS,
    TRADE_LEDGER_COLUMNS,
)
from .normalisation import _normalise_selected_benchmark_ids, _read_json, _write_json
from .schema import apply_schema
from .sql import _fetch_all, _fetch_one, _query_dataframe, create_database_engine

def export_run_archive_from_database(
    run_identifier: str,
    output_root: Path | str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> Path:
    """Materialise one SQL run into a temporary file-shaped archive."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    output_path = Path(output_root).expanduser().resolve()
    run_id = Path(str(run_identifier)).name

    with engine.begin() as connection:
        apply_schema(connection)
        run_row = _fetch_one(
            connection,
            """
            SELECT run_id, experiment_name, run_label, created_at_local, status,
                   config_hash, config_json, metadata_json, source_config_text
            FROM runs
            WHERE run_id = :run_id
            """,
            {"run_id": run_id},
        )
        if run_row is None:
            raise FileNotFoundError(f"Run was not found in PostgreSQL: {run_id}")

        experiment_name = str(run_row["experiment_name"])
        experiment_dir = output_path / experiment_name
        run_dir = experiment_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(exist_ok=True)

        _write_json(run_dir / "config.json", _coerce_json_value(run_row.get("config_json")))
        _write_json(run_dir / "metadata.json", _coerce_json_value(run_row.get("metadata_json")))
        if run_row.get("source_config_text"):
            (run_dir / "config_used.cfg").write_text(
                str(run_row["source_config_text"]),
                encoding="utf-8",
            )

        _query_dataframe(
            connection,
            """
            SELECT row_index, phase, simulation_step, reference_price, market_price,
                   fundamental_price, submitted_orders, net_demand, traded_volume,
                   notional_imbalance, normalized_imbalance, fundamental_signal,
                   random_shock, raw_return, log_return, submitted_limit_orders,
                   submitted_market_orders, cancelled_orders, expired_orders,
                   executed_trades, total_transaction_costs,
                   realized_allocative_surplus, maximum_allocative_surplus,
                   allocative_efficiency, last_trade_price, best_bid, best_ask,
                   bid_ask_spread, mid_quote, bid_depth, ask_depth,
                   resting_bid_orders, resting_ask_orders, wealth_gini_coefficient
            FROM step_timeseries
            WHERE run_id = :run_id
            ORDER BY row_index
            """,
            {"run_id": run_id},
        ).to_csv(run_dir / "step_timeseries.csv", index=False)
        _query_dataframe(
            connection,
            _select_without_run_id("agent_snapshots", AGENT_SNAPSHOT_COLUMNS),
            {"run_id": run_id},
        ).to_csv(run_dir / "agents_final.csv", index=False)
        trade_ledger = _query_dataframe(
            connection,
            _select_without_run_id(
                "trade_ledger",
                TRADE_LEDGER_COLUMNS,
                exclude={"ledger_row_index"},
                order_by="ledger_row_index",
            ),
            {"run_id": run_id},
        )
        if not trade_ledger.empty:
            trade_ledger.to_csv(run_dir / "trade_ledger.csv", index=False)
        _query_dataframe(
            connection,
            _select_without_run_id("summary_metrics", SUMMARY_METRIC_COLUMNS),
            {"run_id": run_id},
        ).to_csv(run_dir / "summary_metrics.csv", index=False)
        _query_dataframe(
            connection,
            _select_without_run_id(
                "stylised_facts",
                STYLISED_FACT_COLUMNS,
                exclude={"stylised_row_index"},
                order_by="stylised_row_index",
            ),
            {"run_id": run_id},
        ).to_csv(run_dir / "stylised_facts.csv", index=False)
        mechanism_diagnostics = _query_dataframe(
            connection,
            _select_without_run_id("mechanism_diagnostics", MECHANISM_DIAGNOSTIC_COLUMNS),
            {"run_id": run_id},
        )
        if not mechanism_diagnostics.empty:
            mechanism_diagnostics.to_csv(run_dir / "mechanism_diagnostics.csv", index=False)
        agent_step_diagnostics = _query_dataframe(
            connection,
            _select_without_run_id("agent_step_diagnostics", AGENT_STEP_DIAGNOSTIC_COLUMNS),
            {"run_id": run_id},
        )
        if not agent_step_diagnostics.empty:
            agent_step_diagnostics.to_csv(run_dir / "agent_step_diagnostics.csv", index=False)
        _write_experiment_manifest(connection, experiment_name, experiment_dir)

    return run_dir

def export_experiment_archive_from_database(
    experiment_identifier: str,
    output_root: Path | str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> Path:
    """Materialise all SQL runs from one experiment into a temporary archive."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    experiment_name = Path(str(experiment_identifier)).name
    output_path = Path(output_root).expanduser().resolve()

    with engine.begin() as connection:
        apply_schema(connection)
        run_ids = [
            str(row["run_id"])
            for row in _fetch_all(
                connection,
                """
                SELECT run_id
                FROM runs
                WHERE experiment_name = :experiment_name
                ORDER BY created_at_local, run_id
                """,
                {"experiment_name": experiment_name},
            )
        ]
    if not run_ids:
        raise FileNotFoundError(f"Experiment was not found in PostgreSQL: {experiment_name}")

    for run_id in run_ids:
        export_run_archive_from_database(
            run_id,
            output_path,
            database_url,
            database_url_env=database_url_env,
        )
    return output_path / experiment_name

def export_benchmarks_from_database(
    output_dir: Path | str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
    benchmark_series: str | list[str] | tuple[str, ...] | None = None,
) -> Path | None:
    """Export benchmark records from PostgreSQL as temporary CSVs."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    selected = _normalise_selected_benchmark_ids(benchmark_series)

    with engine.begin() as connection:
        apply_schema(connection)
        rows = _fetch_all(
            connection,
            "SELECT benchmark_id, source_file FROM benchmark_series ORDER BY benchmark_id",
            {},
        )
        wrote_any = False
        for row in rows:
            benchmark_id = str(row["benchmark_id"])
            if selected is not None and benchmark_id not in selected:
                continue
            prices = _query_dataframe(
                connection,
                """
                SELECT observation_date AS "Date",
                       open_price AS "Open",
                       high_price AS "High",
                       low_price AS "Low",
                       close_price AS "Close",
                       volume AS "Volume"
                FROM benchmark_prices
                WHERE benchmark_id = :benchmark_id
                ORDER BY row_index
                """,
                {"benchmark_id": benchmark_id},
            )
            if prices.empty:
                continue
            filename = str(row["source_file"]) or f"{benchmark_id}.csv"
            prices.to_csv(output_path / filename, index=False)
            wrote_any = True
    return output_path if wrote_any else None

def load_step_timeseries_from_database(
    run_id: str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
    price_column: str = "market_price",
) -> pd.DataFrame:
    """Load one run's time series directly from PostgreSQL."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    with engine.begin() as connection:
        data = _query_dataframe(
            connection,
            """
            SELECT row_index, phase, simulation_step, reference_price, market_price,
                   fundamental_price, submitted_orders, net_demand, traded_volume,
                   notional_imbalance, normalized_imbalance, fundamental_signal,
                   random_shock, raw_return, log_return, submitted_limit_orders,
                   submitted_market_orders, cancelled_orders, expired_orders,
                   executed_trades, total_transaction_costs,
                   realized_allocative_surplus, maximum_allocative_surplus,
                   allocative_efficiency, last_trade_price, best_bid, best_ask,
                   bid_ask_spread, mid_quote, bid_depth, ask_depth,
                   resting_bid_orders, resting_ask_orders, wealth_gini_coefficient
            FROM step_timeseries
            WHERE run_id = :run_id
            ORDER BY row_index
            """,
            {"run_id": run_id},
        )
    if data.empty:
        raise FileNotFoundError(f"Run has no step_timeseries rows in PostgreSQL: {run_id}")
    data["computed_log_return"] = compute_log_returns(data[price_column])
    if "fundamental_price" in data.columns:
        data["computed_fundamental_log_return"] = compute_log_returns(data["fundamental_price"])
    data["run_id"] = run_id
    return data

def build_runs_index_from_database(
    experiment_name: str,
    database_url: str | None = None,
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> pd.DataFrame:
    """Build the experiment run index directly from PostgreSQL summary rows."""

    engine = create_database_engine(database_url, database_url_env=database_url_env)
    with engine.begin() as connection:
        data = _query_dataframe(
            connection,
            """
            SELECT sm.*
            FROM summary_metrics sm
            JOIN runs r ON r.run_id = sm.run_id
            WHERE r.experiment_name = :experiment_name
            ORDER BY sm.created_at_local, sm.run_id
            """,
            {"experiment_name": experiment_name},
        )
    if data.empty:
        return data
    parsed = pd.DataFrame([parse_run_id(str(run_id)) for run_id in data["run_id"]])
    return normalise_manifest_schema(parsed.merge(data, on="run_id", how="left"))

def _write_experiment_manifest(connection: Any, experiment_name: str, experiment_dir: Path) -> None:
    manifest = _query_dataframe(
        connection,
        """
        SELECT sm.*
        FROM summary_metrics sm
        JOIN runs r ON r.run_id = sm.run_id
        WHERE r.experiment_name = :experiment_name
        ORDER BY sm.created_at_local, sm.run_id
        """,
        {"experiment_name": experiment_name},
    )
    if not manifest.empty:
        manifest.to_csv(experiment_dir / "experiment_manifest.csv", index=False)

def _select_without_run_id(
    table_name: str,
    columns: Iterable[str],
    *,
    exclude: set[str] | None = None,
    order_by: str | None = None,
) -> str:
    excluded = {"run_id", *(exclude or set())}
    selected = ", ".join(column for column in columns if column not in excluded)
    ordering = order_by or next(column for column in columns if column != "run_id")
    return (
        f"SELECT {selected} FROM {table_name} "
        "WHERE run_id = :run_id "
        f"ORDER BY {ordering}"
    )
