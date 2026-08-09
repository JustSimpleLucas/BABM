"""Versioned PostgreSQL schema migrations for ABM research data."""

from __future__ import annotations

from typing import Any

from .constants import (
    BOOLEAN_TABLE_COLUMNS,
    COUNT_TABLE_COLUMNS,
    CURRENT_SCHEMA_VERSION,
    REQUIRED_SCHEMA_INDEXES,
)
from .sql import _require_sqlalchemy

def apply_schema(connection: Any) -> None:
    """Apply unapplied PostgreSQL schema migrations in numeric order."""

    sqlalchemy = _require_sqlalchemy()
    connection.execute(
        sqlalchemy.text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    applied_versions = {
        int(row["version"])
        for row in connection.execute(
            sqlalchemy.text("SELECT version FROM schema_migrations")
        ).mappings()
    }
    for version_number, description, statements in schema_migrations():
        if version_number in applied_versions:
            continue
        for statement in statements:
            connection.execute(sqlalchemy.text(statement))
        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO schema_migrations(version, description)
                VALUES (:version, :description)
                ON CONFLICT (version) DO NOTHING
                """
            ),
            {"version": version_number, "description": description},
        )

def schema_sql_statements() -> tuple[str, ...]:
    """Return all PostgreSQL DDL statements for audit and testing."""

    return tuple(
        statement
        for _, _, statements in schema_migrations()
        for statement in statements
    )

def schema_migrations() -> tuple[tuple[int, str, tuple[str, ...]], ...]:
    """Return ordered schema migrations used by ``apply_schema``."""

    return (
        (
            1,
            "Initial PostgreSQL ABM experiment schema",
            migration_001_initial_sql_statements(),
        ),
        (
            2,
            "Indexes, benchmark metadata, diagnostics tables, and import provenance",
            migration_002_indexes_and_metadata_sql_statements(),
        ),
        (
            3,
            "Step-level wealth inequality diagnostics",
            migration_003_wealth_inequality_sql_statements(),
        ),
        (
            4,
            "Final wealth inequality summary metric",
            migration_004_final_wealth_inequality_sql_statements(),
        ),
        (
            5,
            "Double-auction allocative-efficiency diagnostics",
            migration_005_allocative_efficiency_sql_statements(),
        ),
        (
            6,
            "Store integer count columns as BIGINT",
            migration_006_integer_count_columns_sql_statements(),
        ),
        (
            7,
            "Long-format per-asset time series for the multi-asset extension",
            migration_007_asset_timeseries_sql_statements(),
        ),
        (
            8,
            "Per-asset mean agent portfolio weights",
            migration_008_portfolio_composition_sql_statements(),
        ),
        (
            9,
            "Per-asset allocative efficiency and stylised-fact screening",
            migration_009_per_asset_screening_sql_statements(),
        ),
    )

def migration_001_initial_sql_statements() -> tuple[str, ...]:
    """Create the first normalised PostgreSQL schema used by the project."""

    return (
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS experiments (
            experiment_name TEXT PRIMARY KEY,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            experiment_name TEXT NOT NULL REFERENCES experiments(experiment_name)
                ON DELETE CASCADE,
            run_label TEXT,
            created_at_local TEXT,
            status TEXT,
            config_hash TEXT,
            config_json JSONB NOT NULL DEFAULT '{}'::JSONB,
            metadata_json JSONB NOT NULL DEFAULT '{}'::JSONB,
            source_config_text TEXT,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS step_timeseries (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            row_index BIGINT NOT NULL,
            phase TEXT,
            simulation_step DOUBLE PRECISION,
            reference_price DOUBLE PRECISION,
            market_price DOUBLE PRECISION,
            fundamental_price DOUBLE PRECISION,
            submitted_orders DOUBLE PRECISION,
            net_demand DOUBLE PRECISION,
            traded_volume DOUBLE PRECISION,
            notional_imbalance DOUBLE PRECISION,
            normalized_imbalance DOUBLE PRECISION,
            fundamental_signal DOUBLE PRECISION,
            random_shock DOUBLE PRECISION,
            raw_return DOUBLE PRECISION,
            log_return DOUBLE PRECISION,
            submitted_limit_orders DOUBLE PRECISION,
            submitted_market_orders DOUBLE PRECISION,
            cancelled_orders DOUBLE PRECISION,
            expired_orders DOUBLE PRECISION,
            executed_trades DOUBLE PRECISION,
            total_transaction_costs DOUBLE PRECISION,
            realized_allocative_surplus DOUBLE PRECISION,
            maximum_allocative_surplus DOUBLE PRECISION,
            allocative_efficiency DOUBLE PRECISION,
            last_trade_price DOUBLE PRECISION,
            best_bid DOUBLE PRECISION,
            best_ask DOUBLE PRECISION,
            bid_ask_spread DOUBLE PRECISION,
            mid_quote DOUBLE PRECISION,
            bid_depth DOUBLE PRECISION,
            ask_depth DOUBLE PRECISION,
            resting_bid_orders DOUBLE PRECISION,
            resting_ask_orders DOUBLE PRECISION,
            wealth_gini_coefficient DOUBLE PRECISION,
            PRIMARY KEY (run_id, row_index)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_snapshots (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            agent_id BIGINT NOT NULL,
            initial_strategy_type TEXT,
            current_strategy_type TEXT,
            initial_cash DOUBLE PRECISION,
            initial_stock DOUBLE PRECISION,
            initial_wealth DOUBLE PRECISION,
            x_coordinate DOUBLE PRECISION,
            y_coordinate DOUBLE PRECISION,
            social_gamma DOUBLE PRECISION,
            private_signal_std DOUBLE PRECISION,
            final_opinion DOUBLE PRECISION,
            final_cash DOUBLE PRECISION,
            final_stock DOUBLE PRECISION,
            number_of_trades DOUBLE PRECISION,
            traded_volume DOUBLE PRECISION,
            final_wealth DOUBLE PRECISION,
            cumulative_transaction_costs_paid DOUBLE PRECISION,
            average_entry_price DOUBLE PRECISION,
            recent_peak_wealth DOUBLE PRECISION,
            last_prospect_reference_point DOUBLE PRECISION,
            prospect_theory_enabled DOUBLE PRECISION,
            prospect_loss_aversion DOUBLE PRECISION,
            prospect_curvature_gain DOUBLE PRECISION,
            prospect_curvature_loss DOUBLE PRECISION,
            prospect_gamma_gain DOUBLE PRECISION,
            prospect_gamma_loss DOUBLE PRECISION,
            prospect_scenario_count DOUBLE PRECISION,
            PRIMARY KEY (run_id, agent_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS trade_ledger (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            ledger_row_index BIGINT NOT NULL,
            trade_id BIGINT,
            time DOUBLE PRECISION,
            agent_id BIGINT,
            counterparty_agent_id BIGINT,
            side TEXT,
            price DOUBLE PRECISION,
            qty DOUBLE PRECISION,
            asset TEXT,
            order_id BIGINT,
            counterparty_order_id BIGINT,
            gross_notional DOUBLE PRECISION,
            transaction_cost DOUBLE PRECISION,
            net_cash_flow DOUBLE PRECISION,
            PRIMARY KEY (run_id, ledger_row_index)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS summary_metrics (
            run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
            experiment_name TEXT,
            run_label TEXT,
            created_at_local TEXT,
            status TEXT,
            config_hash TEXT,
            seed BIGINT,
            time_steps BIGINT,
            warmup_steps BIGINT,
            fundamental_shock_std_dev DOUBLE PRECISION,
            fundamental_drift_per_step DOUBLE PRECISION,
            minimum_fundamental_value DOUBLE PRECISION,
            num_fundamentalists BIGINT,
            num_chartists BIGINT,
            num_noise_traders BIGINT,
            num_buy_and_hold_agents BIGINT,
            transaction_cost_rate DOUBLE PRECISION,
            transaction_cost_affects_decisions DOUBLE PRECISION,
            transaction_cost_apply_to_forced_buy_ins DOUBLE PRECISION,
            prospect_theory_enabled DOUBLE PRECISION,
            prospect_theory_agent_fraction DOUBLE PRECISION,
            prospect_heterogeneity_enabled DOUBLE PRECISION,
            social_enabled DOUBLE PRECISION,
            short_selling_enabled DOUBLE PRECISION,
            final_market_price DOUBLE PRECISION,
            final_fundamental_price DOUBLE PRECISION,
            final_wealth_gini_coefficient DOUBLE PRECISION,
            total_traded_volume DOUBLE PRECISION,
            total_transaction_costs DOUBLE PRECISION,
            average_absolute_order_imbalance DOUBLE PRECISION,
            mean_allocative_efficiency DOUBLE PRECISION,
            allocative_efficiency_observations BIGINT,
            mean_log_return DOUBLE PRECISION,
            log_return_variance DOUBLE PRECISION,
            log_return_std_dev DOUBLE PRECISION,
            skewness DOUBLE PRECISION,
            excess_kurtosis DOUBLE PRECISION,
            max_drawdown DOUBLE PRECISION,
            lag1_return_autocorrelation DOUBLE PRECISION,
            lag1_abs_return_autocorrelation DOUBLE PRECISION,
            lag1_squared_return_autocorrelation DOUBLE PRECISION,
            mean_traded_volume DOUBLE PRECISION,
            zero_return_share DOUBLE PRECISION,
            observation_count BIGINT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS stylised_facts (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            stylised_row_index BIGINT NOT NULL,
            stylised_fact TEXT,
            diagnostic TEXT,
            metric_value DOUBLE PRECISION,
            screening_rule TEXT,
            conclusion TEXT,
            PRIMARY KEY (run_id, stylised_row_index)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS benchmark_series (
            benchmark_id TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS benchmark_prices (
            benchmark_id TEXT NOT NULL REFERENCES benchmark_series(benchmark_id)
                ON DELETE CASCADE,
            row_index BIGINT NOT NULL,
            observation_date DATE,
            open_price DOUBLE PRECISION,
            high_price DOUBLE PRECISION,
            low_price DOUBLE PRECISION,
            close_price DOUBLE PRECISION,
            volume DOUBLE PRECISION,
            market_price DOUBLE PRECISION,
            traded_volume DOUBLE PRECISION,
            computed_log_return DOUBLE PRECISION,
            raw_row_json JSONB NOT NULL DEFAULT '{}'::JSONB,
            PRIMARY KEY (benchmark_id, row_index)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS import_audit (
            audit_id BIGSERIAL PRIMARY KEY,
            item_type TEXT NOT NULL,
            identifier TEXT NOT NULL,
            rows_imported BIGINT NOT NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    )

def migration_002_indexes_and_metadata_sql_statements() -> tuple[str, ...]:
    """Add thesis-audit metadata, query indexes, and explicit boolean switches."""

    return (
        """
        ALTER TABLE runs
        ADD COLUMN IF NOT EXISTS source_archive_sha256 TEXT
        """,
        """
        CREATE TABLE IF NOT EXISTS benchmark_metadata (
            benchmark_id TEXT PRIMARY KEY REFERENCES benchmark_series(benchmark_id)
                ON DELETE CASCADE,
            display_name TEXT,
            asset_class TEXT,
            source_vendor TEXT,
            source_url_or_dataset TEXT,
            source_file TEXT NOT NULL,
            date_start DATE,
            date_end DATE,
            frequency TEXT,
            timezone TEXT,
            price_column TEXT,
            return_definition TEXT,
            cleaning_notes TEXT,
            raw_file_sha256 TEXT,
            crisis_regime_label TEXT,
            license_or_access_note TEXT,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS mechanism_diagnostics (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            row_index BIGINT NOT NULL,
            phase TEXT,
            simulation_step DOUBLE PRECISION,
            mechanism_name TEXT NOT NULL,
            diagnostic_name TEXT NOT NULL,
            diagnostic_value DOUBLE PRECISION,
            diagnostic_text TEXT,
            PRIMARY KEY (run_id, row_index, mechanism_name, diagnostic_name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_step_diagnostics (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            row_index BIGINT NOT NULL,
            agent_id BIGINT NOT NULL,
            phase TEXT,
            simulation_step DOUBLE PRECISION,
            diagnostic_name TEXT NOT NULL,
            diagnostic_value DOUBLE PRECISION,
            diagnostic_text TEXT,
            PRIMARY KEY (run_id, row_index, agent_id, diagnostic_name)
        )
        """,
        """
        ALTER TABLE import_audit
        ADD COLUMN IF NOT EXISTS schema_version BIGINT
        """,
        """
        ALTER TABLE import_audit
        ADD COLUMN IF NOT EXISTS importer_version TEXT
        """,
        """
        ALTER TABLE import_audit
        ADD COLUMN IF NOT EXISTS git_commit TEXT
        """,
        """
        ALTER TABLE import_audit
        ADD COLUMN IF NOT EXISTS source_archive_sha256 TEXT
        """,
        """
        ALTER TABLE import_audit
        ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed'
        """,
        """
        ALTER TABLE import_audit
        ADD COLUMN IF NOT EXISTS message TEXT
        """,
        *_boolean_type_migration_statements(),
        """
        CREATE INDEX IF NOT EXISTS idx_runs_experiment_created
        ON runs(experiment_name, created_at_local)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_step_timeseries_run_phase_step
        ON step_timeseries(run_id, phase, simulation_step)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_benchmark_prices_series_date
        ON benchmark_prices(benchmark_id, observation_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_summary_metrics_experiment_seed_steps
        ON summary_metrics(experiment_name, seed, time_steps)
        """,
    )


def migration_003_wealth_inequality_sql_statements() -> tuple[str, ...]:
    """Add per-step whole-population wealth inequality diagnostics."""

    return (
        """
        ALTER TABLE step_timeseries
        ADD COLUMN IF NOT EXISTS wealth_gini_coefficient DOUBLE PRECISION
        """,
    )

def migration_004_final_wealth_inequality_sql_statements() -> tuple[str, ...]:
    """Add run-level final wealth inequality diagnostics."""

    return (
        """
        ALTER TABLE summary_metrics
        ADD COLUMN IF NOT EXISTS final_wealth_gini_coefficient DOUBLE PRECISION
        """,
    )

def migration_005_allocative_efficiency_sql_statements() -> tuple[str, ...]:
    """Add gross double-auction allocative-efficiency diagnostics."""

    return (
        """
        ALTER TABLE step_timeseries
        ADD COLUMN IF NOT EXISTS realized_allocative_surplus DOUBLE PRECISION
        """,
        """
        ALTER TABLE step_timeseries
        ADD COLUMN IF NOT EXISTS maximum_allocative_surplus DOUBLE PRECISION
        """,
        """
        ALTER TABLE step_timeseries
        ADD COLUMN IF NOT EXISTS allocative_efficiency DOUBLE PRECISION
        """,
        """
        ALTER TABLE summary_metrics
        ADD COLUMN IF NOT EXISTS mean_allocative_efficiency DOUBLE PRECISION
        """,
        """
        ALTER TABLE summary_metrics
        ADD COLUMN IF NOT EXISTS allocative_efficiency_observations BIGINT
        """,
    )

def migration_006_integer_count_columns_sql_statements() -> tuple[str, ...]:
    """Convert integer-count columns from DOUBLE PRECISION to BIGINT.

    Counts such as submitted or executed orders are exact integers in the
    simulator; storing them as floating point invites spurious fractional
    values in thesis queries. The conversion is generated from
    ``COUNT_TABLE_COLUMNS`` and each statement no-ops when a column already
    has the BIGINT type, so re-running the migration is safe.
    """

    statements: list[str] = []
    for table_name, columns in sorted(COUNT_TABLE_COLUMNS.items()):
        for column_name in sorted(columns):
            statements.append(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = '{table_name}'
                          AND column_name = '{column_name}'
                          AND data_type <> 'bigint'
                    ) THEN
                        ALTER TABLE {table_name}
                        ALTER COLUMN {column_name} TYPE BIGINT
                        USING ROUND({column_name}::DOUBLE PRECISION)::BIGINT;
                    END IF;
                END $$;
                """
            )
    return tuple(statements)


def migration_007_asset_timeseries_sql_statements() -> tuple[str, ...]:
    """Create the long-format per-(step, asset) time-series table."""

    return (
        """
        CREATE TABLE IF NOT EXISTS asset_timeseries (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            row_index BIGINT NOT NULL,
            phase TEXT,
            simulation_step DOUBLE PRECISION,
            asset TEXT,
            market_price DOUBLE PRECISION,
            fundamental_price DOUBLE PRECISION,
            raw_return DOUBLE PRECISION,
            log_return DOUBLE PRECISION,
            submitted_orders BIGINT,
            traded_volume DOUBLE PRECISION,
            executed_trades BIGINT,
            last_trade_price DOUBLE PRECISION,
            best_bid DOUBLE PRECISION,
            best_ask DOUBLE PRECISION,
            bid_ask_spread DOUBLE PRECISION,
            mid_quote DOUBLE PRECISION,
            bid_depth DOUBLE PRECISION,
            ask_depth DOUBLE PRECISION,
            resting_bid_orders BIGINT,
            resting_ask_orders BIGINT,
            stale_cancelled_orders BIGINT,
            expired_orders BIGINT,
            infeasible_resting_cancellations BIGINT,
            infeasible_incoming_cancellations BIGINT,
            self_trade_preventions BIGINT,
            collar_rejected_orders BIGINT,
            total_transaction_costs DOUBLE PRECISION,
            PRIMARY KEY (run_id, row_index)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_asset_timeseries_run_step_asset
        ON asset_timeseries(run_id, simulation_step, asset)
        """,
    )

def migration_008_portfolio_composition_sql_statements() -> tuple[str, ...]:
    """Add the per-asset portfolio-composition columns.

    Added as a separate migration rather than by editing migration 007 so that
    databases already carrying imported multi-asset runs upgrade in place. The
    columns are nullable because runs archived before the columns existed
    legitimately have no portfolio-composition data.
    """

    return (
        """
        ALTER TABLE asset_timeseries
        ADD COLUMN IF NOT EXISTS mean_agent_portfolio_weight DOUBLE PRECISION
        """,
        """
        ALTER TABLE asset_timeseries
        ADD COLUMN IF NOT EXISTS portfolio_weight_agent_count BIGINT
        """,
    )

def migration_009_per_asset_screening_sql_statements() -> tuple[str, ...]:
    """Put both markets on equal footing in the per-asset and screening tables.

    ``asset_timeseries`` gains the double-auction allocative-surplus columns
    that previously existed only for the primary asset, and ``stylised_facts``
    gains the asset each screening row describes. Both are nullable because
    runs archived before this migration carry neither.
    """

    return (
        """
        ALTER TABLE asset_timeseries
        ADD COLUMN IF NOT EXISTS submitted_limit_orders BIGINT
        """,
        """
        ALTER TABLE asset_timeseries
        ADD COLUMN IF NOT EXISTS submitted_market_orders BIGINT
        """,
        """
        ALTER TABLE asset_timeseries
        ADD COLUMN IF NOT EXISTS realized_allocative_surplus DOUBLE PRECISION
        """,
        """
        ALTER TABLE asset_timeseries
        ADD COLUMN IF NOT EXISTS maximum_allocative_surplus DOUBLE PRECISION
        """,
        """
        ALTER TABLE asset_timeseries
        ADD COLUMN IF NOT EXISTS allocative_efficiency DOUBLE PRECISION
        """,
        """
        ALTER TABLE stylised_facts
        ADD COLUMN IF NOT EXISTS asset TEXT
        """,
    )

def _boolean_type_migration_statements() -> tuple[str, ...]:
    statements: list[str] = []
    for table_name, columns in BOOLEAN_TABLE_COLUMNS.items():
        for column_name in sorted(columns):
            statements.append(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = '{table_name}'
                          AND column_name = '{column_name}'
                          AND data_type <> 'boolean'
                    ) THEN
                        ALTER TABLE {table_name}
                        ALTER COLUMN {column_name} TYPE BOOLEAN
                        USING CASE
                            WHEN {column_name} IS NULL THEN NULL
                            WHEN lower({column_name}::TEXT) IN ('true', 't', 'yes', 'y', '1', '1.0')
                                THEN TRUE
                            WHEN lower({column_name}::TEXT) IN ('false', 'f', 'no', 'n', '0', '0.0')
                                THEN FALSE
                            ELSE {column_name}::DOUBLE PRECISION <> 0
                        END;
                    END IF;
                END $$;
                """
            )
    return tuple(statements)

def _database_schema_version(connection: Any) -> int:
    sqlalchemy = _require_sqlalchemy()
    return int(
        connection.execute(
            sqlalchemy.text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
        ).scalar_one()
    )

def _schema_index_exists(connection: Any, index_name: str) -> bool:
    sqlalchemy = _require_sqlalchemy()
    return bool(
        connection.execute(
            sqlalchemy.text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND indexname = :index_name
                )
                """
            ),
            {"index_name": index_name},
        ).scalar_one()
    )
