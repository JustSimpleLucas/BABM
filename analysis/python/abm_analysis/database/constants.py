"""Constants defining the PostgreSQL schema and import policy."""

from __future__ import annotations

DEFAULT_DATABASE_URL_ENV = "ABM_DATABASE_URL"

CURRENT_SCHEMA_VERSION = 9

IMPORTER_PACKAGE_NAME = "abm-analysis"

UNKNOWN_IMPORTER_VERSION = "0.1.0"

SCHEMA_TABLE_NAMES = (
    "schema_migrations",
    "experiments",
    "runs",
    "step_timeseries",
    "asset_timeseries",
    "agent_snapshots",
    "trade_ledger",
    "summary_metrics",
    "stylised_facts",
    "benchmark_series",
    "benchmark_metadata",
    "benchmark_prices",
    "mechanism_diagnostics",
    "agent_step_diagnostics",
    "import_audit",
)

REQUIRED_SCHEMA_INDEXES = (
    "idx_runs_experiment_created",
    "idx_step_timeseries_run_phase_step",
    "idx_asset_timeseries_run_step_asset",
    "idx_benchmark_prices_series_date",
    "idx_summary_metrics_experiment_seed_steps",
)

STEP_TIMESERIES_COLUMNS = (
    "run_id",
    "row_index",
    "phase",
    "simulation_step",
    "reference_price",
    "market_price",
    "fundamental_price",
    "submitted_orders",
    "net_demand",
    "traded_volume",
    "notional_imbalance",
    "normalized_imbalance",
    "fundamental_signal",
    "random_shock",
    "raw_return",
    "log_return",
    "submitted_limit_orders",
    "submitted_market_orders",
    "cancelled_orders",
    "expired_orders",
    "executed_trades",
    "total_transaction_costs",
    "realized_allocative_surplus",
    "maximum_allocative_surplus",
    "allocative_efficiency",
    "last_trade_price",
    "best_bid",
    "best_ask",
    "bid_ask_spread",
    "mid_quote",
    "bid_depth",
    "ask_depth",
    "resting_bid_orders",
    "resting_ask_orders",
    "wealth_gini_coefficient",
)

ASSET_TIMESERIES_COLUMNS = (
    "run_id",
    "row_index",
    "phase",
    "simulation_step",
    "asset",
    "market_price",
    "fundamental_price",
    "raw_return",
    "log_return",
    "submitted_orders",
    "submitted_limit_orders",
    "submitted_market_orders",
    "traded_volume",
    "executed_trades",
    "last_trade_price",
    "best_bid",
    "best_ask",
    "bid_ask_spread",
    "mid_quote",
    "bid_depth",
    "ask_depth",
    "resting_bid_orders",
    "resting_ask_orders",
    "stale_cancelled_orders",
    "expired_orders",
    "infeasible_resting_cancellations",
    "infeasible_incoming_cancellations",
    "self_trade_preventions",
    "collar_rejected_orders",
    "total_transaction_costs",
    "realized_allocative_surplus",
    "maximum_allocative_surplus",
    "allocative_efficiency",
    "mean_agent_portfolio_weight",
    "portfolio_weight_agent_count",
)

AGENT_SNAPSHOT_COLUMNS = (
    "run_id",
    "agent_id",
    "initial_strategy_type",
    "current_strategy_type",
    "initial_cash",
    "initial_stock",
    "initial_wealth",
    "x_coordinate",
    "y_coordinate",
    "social_gamma",
    "private_signal_std",
    "final_opinion",
    "final_cash",
    "final_stock",
    "number_of_trades",
    "traded_volume",
    "final_wealth",
    "cumulative_transaction_costs_paid",
    "average_entry_price",
    "recent_peak_wealth",
    "last_prospect_reference_point",
    "prospect_theory_enabled",
    "prospect_loss_aversion",
    "prospect_curvature_gain",
    "prospect_curvature_loss",
    "prospect_gamma_gain",
    "prospect_gamma_loss",
    "prospect_scenario_count",
)

TRADE_LEDGER_COLUMNS = (
    "run_id",
    "ledger_row_index",
    "trade_id",
    "time",
    "agent_id",
    "counterparty_agent_id",
    "side",
    "price",
    "qty",
    "asset",
    "order_id",
    "counterparty_order_id",
    "gross_notional",
    "transaction_cost",
    "net_cash_flow",
)

SUMMARY_METRIC_COLUMNS = (
    "run_id",
    "experiment_name",
    "run_label",
    "created_at_local",
    "status",
    "config_hash",
    "seed",
    "time_steps",
    "warmup_steps",
    "fundamental_shock_std_dev",
    "fundamental_drift_per_step",
    "minimum_fundamental_value",
    "num_fundamentalists",
    "num_chartists",
    "num_noise_traders",
    "num_buy_and_hold_agents",
    "transaction_cost_rate",
    "transaction_cost_affects_decisions",
    "transaction_cost_apply_to_forced_buy_ins",
    "prospect_theory_enabled",
    "prospect_theory_agent_fraction",
    "prospect_heterogeneity_enabled",
    "social_enabled",
    "short_selling_enabled",
    "final_market_price",
    "final_fundamental_price",
    "final_wealth_gini_coefficient",
    "total_traded_volume",
    "total_transaction_costs",
    "average_absolute_order_imbalance",
    "mean_allocative_efficiency",
    "allocative_efficiency_observations",
    "mean_log_return",
    "log_return_variance",
    "log_return_std_dev",
    "skewness",
    "excess_kurtosis",
    "max_drawdown",
    "lag1_return_autocorrelation",
    "lag1_abs_return_autocorrelation",
    "lag1_squared_return_autocorrelation",
    "mean_traded_volume",
    "zero_return_share",
    "observation_count",
)

STYLISED_FACT_COLUMNS = (
    "run_id",
    "stylised_row_index",
    "asset",
    "stylised_fact",
    "diagnostic",
    "metric_value",
    "screening_rule",
    "conclusion",
)

BENCHMARK_PRICE_COLUMNS = (
    "benchmark_id",
    "row_index",
    "observation_date",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "market_price",
    "traded_volume",
    "computed_log_return",
    "raw_row_json",
)

BENCHMARK_METADATA_COLUMNS = (
    "benchmark_id",
    "display_name",
    "asset_class",
    "source_vendor",
    "source_url_or_dataset",
    "source_file",
    "date_start",
    "date_end",
    "frequency",
    "timezone",
    "price_column",
    "return_definition",
    "cleaning_notes",
    "raw_file_sha256",
    "crisis_regime_label",
    "license_or_access_note",
)

MECHANISM_DIAGNOSTIC_COLUMNS = (
    "run_id",
    "row_index",
    "phase",
    "simulation_step",
    "mechanism_name",
    "diagnostic_name",
    "diagnostic_value",
    "diagnostic_text",
)

AGENT_STEP_DIAGNOSTIC_COLUMNS = (
    "run_id",
    "row_index",
    "agent_id",
    "phase",
    "simulation_step",
    "diagnostic_name",
    "diagnostic_value",
    "diagnostic_text",
)

STAGING_ARTIFACTS = (
    "step_timeseries.csv",
    "asset_timeseries.csv",
    "agents_final.csv",
    "trade_ledger.csv",
    "summary_metrics.csv",
    "stylised_facts.csv",
    "mechanism_diagnostics.csv",
    "agent_step_diagnostics.csv",
    "config.json",
    "metadata.json",
    "config_used.cfg",
)

JSONB_TABLE_COLUMNS = {
    "benchmark_prices": {"raw_row_json"},
}

BOOLEAN_TABLE_COLUMNS = {
    "agent_snapshots": {"prospect_theory_enabled"},
    "summary_metrics": {
        "transaction_cost_affects_decisions",
        "transaction_cost_apply_to_forced_buy_ins",
        "prospect_theory_enabled",
        "prospect_heterogeneity_enabled",
        "social_enabled",
        "short_selling_enabled",
    },
}

# Columns that hold integer counts or identifiers. The simulator emits them as
# integers, but pandas promotes any column containing missing values (for
# example warm-up rows) to float, so import normalisation coerces whole floats
# back to integers and migration 006 stores them as BIGINT. Counting variables
# must not be confused with continuous quantities such as traded volume, which
# legitimately stays DOUBLE PRECISION because partial fills are allowed.
COUNT_TABLE_COLUMNS = {
    "step_timeseries": {
        "submitted_orders",
        "submitted_limit_orders",
        "submitted_market_orders",
        "cancelled_orders",
        "expired_orders",
        "executed_trades",
        "resting_bid_orders",
        "resting_ask_orders",
    },
    "asset_timeseries": {
        "submitted_orders",
        "submitted_limit_orders",
        "submitted_market_orders",
        "executed_trades",
        "resting_bid_orders",
        "resting_ask_orders",
        "stale_cancelled_orders",
        "expired_orders",
        "infeasible_resting_cancellations",
        "infeasible_incoming_cancellations",
        "self_trade_preventions",
        "collar_rejected_orders",
    },
    "agent_snapshots": {
        "agent_id",
        "number_of_trades",
        "prospect_scenario_count",
    },
    "trade_ledger": {
        "trade_id",
        "time",
        "agent_id",
        "counterparty_agent_id",
        "order_id",
        "counterparty_order_id",
    },
    "summary_metrics": {
        "seed",
        "time_steps",
        "warmup_steps",
        "num_fundamentalists",
        "num_chartists",
        "num_noise_traders",
        "num_buy_and_hold_agents",
        "allocative_efficiency_observations",
        "observation_count",
    },
}

BENCHMARK_METADATA_REQUIRED_FIELDS = (
    "benchmark_id",
    "source_file",
    "date_start",
    "date_end",
    "price_column",
    "return_definition",
    "raw_file_sha256",
)

PATH_LIKE_METADATA_KEYS = {
    "outputs",
    "source_config_path",
    "archived_config_path",
    "step_timeseries_csv",
    "asset_timeseries_csv",
    "agents_final_csv",
    "trade_ledger_csv",
    "summary_metrics_csv",
    "stylised_facts_csv",
    "config_json",
    "run_log",
}

PATH_LIKE_CONFIG_KEYS = {
    "simulation_csv_output",
    "asset_timeseries_csv_output",
    "agent_csv_output",
    "trade_ledger_csv_output",
    "summary_metrics_csv_output",
    "stylised_facts_csv_output",
    "config_json_output",
    "metadata_json_output",
    "run_log_output",
    "experiment_root",
    "python_analysis_python",
}
