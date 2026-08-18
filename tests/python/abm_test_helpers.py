from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _non_negative_gini(values: np.ndarray) -> float:
    """Return the bounded non-negative Gini used by synthetic run summaries."""

    wealth = np.asarray(values, dtype=float)
    wealth = np.where(np.isfinite(wealth), np.maximum(wealth, 0.0), np.nan)
    wealth = wealth[np.isfinite(wealth)]
    if wealth.size < 2:
        return 0.0
    wealth = np.sort(wealth)
    total_wealth = float(wealth.sum())
    if total_wealth <= 1e-12:
        return 0.0
    weights = np.arange(1, wealth.size + 1, dtype=float)
    gini = (2.0 * float(np.dot(weights, wealth))) / (wealth.size * total_wealth)
    gini -= (wealth.size + 1.0) / wealth.size
    return float(np.clip(gini, 0.0, 1.0))


def make_synthetic_experiment(tmp_path: Path) -> Path:
    experiment_dir = tmp_path / "synthetic_experiment"
    experiment_dir.mkdir()
    run_specs = [
        ("20260427143012_1_1_0_1_20_30_5_2_180_66", 66, 0.0),
        ("20260427143112_0_1_1_1_20_30_5_2_180_67", 67, 0.015),
    ]
    for run_id, seed, drift_adjustment in run_specs:
        write_synthetic_run(experiment_dir / run_id, run_id, seed, drift_adjustment)
    return experiment_dir


def make_synthetic_benchmark_dir(tmp_path: Path) -> Path:
    benchmark_dir = tmp_path / "benchmarks"
    benchmark_dir.mkdir(exist_ok=True)
    dates = pd.date_range("2025-01-01", periods=220, freq="D")
    for filename, seed, drift in [
        ("02_SPX.csv", 100, 0.0003),
        ("03_NAQ.csv", 101, 0.0005),
    ]:
        rng = np.random.default_rng(seed)
        shocks = rng.standard_t(df=6, size=len(dates)) * 0.01 + drift
        close = 100.0 * np.exp(np.cumsum(shocks))
        benchmark = pd.DataFrame(
            {
                "Date": dates,
                "Open": close * 0.995,
                "High": close * 1.01,
                "Low": close * 0.99,
                "Close": close,
                "Volume": rng.integers(1000, 5000, size=len(dates)),
            }
        )
        # Write newest-first to match common spreadsheet exports.
        benchmark.iloc[::-1].to_csv(benchmark_dir / filename, index=False, encoding="utf-8-sig")
    return benchmark_dir


def write_synthetic_run(run_dir: Path, run_id: str, seed: int, drift_adjustment: float) -> None:
    run_dir.mkdir()
    (run_dir / "logs").mkdir()
    rng = np.random.default_rng(seed)
    observations = 190
    shocks = rng.standard_t(df=5, size=observations) * 0.012 + drift_adjustment / observations
    market_price = 100.0 * np.exp(np.cumsum(shocks))
    fundamental_price = 100.0 * np.exp(np.cumsum(np.full(observations, 0.0002)))
    traded_volume = np.maximum(0.0, rng.normal(120.0, 30.0, size=observations))
    spread = np.maximum(0.01, rng.normal(0.08, 0.015, size=observations))
    best_bid = market_price - spread / 2.0
    best_ask = market_price + spread / 2.0
    bid_depth = np.maximum(0.0, rng.normal(420.0, 70.0, size=observations))
    ask_depth = np.maximum(0.0, rng.normal(390.0, 65.0, size=observations))
    submitted_limit_orders = rng.integers(30, 60, size=observations)
    submitted_market_orders = rng.integers(0, 8, size=observations)
    maximum_allocative_surplus = np.maximum(0.0, traded_volume * spread)
    allocative_efficiency = np.clip(rng.normal(0.86, 0.06, size=observations), 0.0, 1.0)
    realized_allocative_surplus = maximum_allocative_surplus * allocative_efficiency
    wealth_gini_coefficient = np.clip(
        0.18 + np.linspace(0.0, 0.05, observations) + np.abs(shocks) * 2.0,
        0.0,
        1.0,
    )

    step_timeseries = pd.DataFrame(
        {
            "row_index": np.arange(observations),
            "phase": ["initial", *["warmup"] * 9, *["simulation"] * (observations - 10)],
            "simulation_step": [np.nan, *[np.nan] * 9, *range(1, observations - 9)],
            "reference_price": np.nan,
            "market_price": market_price,
            "fundamental_price": fundamental_price,
            "submitted_orders": 50,
            "net_demand": rng.normal(0.0, 1.0, size=observations),
            "traded_volume": traded_volume,
            "notional_imbalance": rng.normal(0.0, 1.0, size=observations),
            "normalized_imbalance": rng.normal(0.0, 0.2, size=observations),
            "fundamental_signal": rng.normal(0.0, 0.1, size=observations),
            "random_shock": shocks,
            "raw_return": np.r_[np.nan, np.diff(market_price) / market_price[:-1]],
            "log_return": np.r_[np.nan, np.diff(np.log(market_price))],
            "submitted_limit_orders": submitted_limit_orders,
            "submitted_market_orders": submitted_market_orders,
            "cancelled_orders": rng.integers(0, 5, size=observations),
            "expired_orders": rng.integers(0, 4, size=observations),
            "executed_trades": rng.integers(0, 12, size=observations),
            "total_transaction_costs": traded_volume * market_price * 0.001,
            "realized_allocative_surplus": realized_allocative_surplus,
            "maximum_allocative_surplus": maximum_allocative_surplus,
            "allocative_efficiency": allocative_efficiency,
            "last_trade_price": market_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_ask_spread": spread,
            "mid_quote": (best_bid + best_ask) / 2.0,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "resting_bid_orders": rng.integers(20, 80, size=observations),
            "resting_ask_orders": rng.integers(20, 80, size=observations),
            "wealth_gini_coefficient": wealth_gini_coefficient,
        }
    )
    step_timeseries.to_csv(run_dir / "step_timeseries.csv", index=False)

    final_wealth = 1000.0 + rng.normal(0.0, 50.0, size=12)
    summary = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "experiment_name": "synthetic",
                "run_label": "pytest",
                "created_at_local": "2026-04-27T14:30:12",
                "status": "completed",
                "seed": seed,
                "time_steps": observations - 10,
                "warmup_steps": 9,
                "num_fundamentalists": 20,
                "num_chartists": 30,
                "num_noise_traders": 5,
                "num_buy_and_hold_agents": 2,
                "prospect_theory_enabled": int("_1_" in run_id),
                "prospect_heterogeneity_enabled": 1,
                "social_enabled": 1,
                "short_selling_enabled": 1,
                "final_market_price": float(market_price[-1]),
                "final_fundamental_price": float(fundamental_price[-1]),
                "final_wealth_gini_coefficient": _non_negative_gini(final_wealth),
                "total_traded_volume": float(traded_volume.sum()),
                "mean_allocative_efficiency": float(np.nanmean(allocative_efficiency)),
                "allocative_efficiency_observations": int(
                    np.count_nonzero(maximum_allocative_surplus > 1e-12)
                ),
                "mean_log_return": float(np.nanmean(step_timeseries["log_return"])),
                "log_return_std_dev": float(np.nanstd(step_timeseries["log_return"], ddof=1)),
                "excess_kurtosis": 1.0,
                "max_drawdown": 0.2,
                "lag1_return_autocorrelation": 0.01,
                "lag1_abs_return_autocorrelation": 0.08,
                "lag1_squared_return_autocorrelation": 0.06,
            }
        ]
    )
    summary.to_csv(run_dir / "summary_metrics.csv", index=False)

    agents = pd.DataFrame(
        {
            "agent_id": np.arange(12),
            "initial_strategy_type": ["fundamentalist"] * 6 + ["chartist"] * 6,
            "current_strategy_type": ["fundamentalist"] * 5 + ["chartist"] * 7,
            "initial_wealth": 1000.0,
            "final_wealth": final_wealth,
            "final_cash": np.maximum(0.0, rng.normal(650.0, 75.0, size=12)),
            "final_stock": rng.normal(4.0, 1.2, size=12),
            "number_of_trades": rng.integers(0, 25, size=12),
            "traded_volume": np.maximum(0.0, rng.normal(55.0, 18.0, size=12)),
            "average_entry_price": np.maximum(0.01, rng.normal(100.0, 2.0, size=12)),
            "recent_peak_wealth": 1060.0 + rng.normal(0.0, 45.0, size=12),
            "last_prospect_reference_point": np.maximum(0.01, rng.normal(102.0, 3.0, size=12)),
            "prospect_theory_enabled": 1,
        }
    )
    agents.to_csv(run_dir / "agents_final.csv", index=False)

    trade_agent_ids = rng.integers(0, 12, size=20)
    counterparty_agent_ids = rng.integers(0, 12, size=20)
    trade_agent_ids[:4] = [0, 7, 1, 8]
    counterparty_agent_ids[:4] = [7, 0, 8, 1]
    trades = pd.DataFrame(
        {
            "trade_id": np.arange(20),
            "time": np.arange(20),
            "agent_id": trade_agent_ids,
            "counterparty_agent_id": counterparty_agent_ids,
            "side": rng.choice(["buy", "sell"], size=20),
            "price": market_price[:20],
            "qty": rng.integers(1, 5, size=20),
            "asset": "stock",
            "order_id": np.arange(20),
            "counterparty_order_id": np.arange(20) + 100,
        }
    )
    trades.to_csv(run_dir / "trade_ledger.csv", index=False)


def write_synthetic_asset_timeseries(
    run_dir: Path,
    assets: list[str],
    *,
    seed: int = 7,
    disabled_assets: list[str] | None = None,
    fundamental_correlation: float = 0.3,
    processes: dict[str, str] | None = None,
    observations: int = 190,
) -> None:
    """Add a long-format ``asset_timeseries.csv`` and matching ``config.json``.

    Mirrors the simulator's artefacts closely enough to drive the multi-asset
    analytics and report panels: one row per (row_index, asset), including the
    per-asset portfolio weights that the composition chart consumes.

    ``observations`` shortens the per-asset artefact without touching the run's
    other files, which reproduces an archive whose ``asset_timeseries.csv``
    disagrees with its own ``step_timeseries.csv``. That state exists in the
    wild and consumers have to survive it.
    """

    import json

    rng = np.random.default_rng(seed)
    processes = processes or {}
    rows = []
    row_index = 0
    for step_position in range(observations):
        if step_position == 0:
            phase, simulation_step = "initial", np.nan
        elif step_position <= 9:
            phase, simulation_step = "warmup", np.nan
        else:
            phase, simulation_step = "simulation", step_position - 9

        # Weights must leave room for a positive cash residual so the stacked
        # composition chart sums to one without a negative band.
        weights = rng.dirichlet(np.ones(len(assets) + 1))
        for asset_position, asset_name in enumerate(assets):
            price = 100.0 * (asset_position + 1) * float(np.exp(rng.normal(0.0, 0.01)))
            rows.append(
                {
                    "row_index": row_index,
                    "phase": phase,
                    "simulation_step": simulation_step,
                    "asset": asset_name,
                    "market_price": price,
                    "fundamental_price": price * 1.01,
                    "raw_return": float(rng.normal(0.0, 0.01)),
                    "log_return": float(rng.normal(0.0, 0.01)),
                    "submitted_orders": 12,
                    "submitted_limit_orders": 9,
                    "submitted_market_orders": 3,
                    "traded_volume": float(abs(rng.normal(100.0, 20.0))),
                    "executed_trades": 3,
                    "last_trade_price": price,
                    "best_bid": price - 0.05,
                    "best_ask": price + 0.05,
                    "bid_ask_spread": 0.1,
                    "mid_quote": price,
                    "bid_depth": 100.0,
                    "ask_depth": 100.0,
                    "resting_bid_orders": 5,
                    "resting_ask_orders": 5,
                    "stale_cancelled_orders": 0,
                    "expired_orders": 0,
                    "infeasible_resting_cancellations": 0,
                    "infeasible_incoming_cancellations": 0,
                    "self_trade_preventions": 0,
                    "collar_rejected_orders": 0,
                    "total_transaction_costs": 1.0,
                    "realized_allocative_surplus": 4.0,
                    "maximum_allocative_surplus": 5.0,
                    "allocative_efficiency": 0.8,
                    "mean_agent_portfolio_weight": float(weights[asset_position]),
                    "portfolio_weight_agent_count": 12,
                }
            )
            row_index += 1
    pd.DataFrame(rows).to_csv(run_dir / "asset_timeseries.csv", index=False)

    def _definition(name: str, enabled: bool) -> dict:
        return {
            "name": name,
            "enabled": enabled,
            # Declared assets default to geometric Brownian motion, matching the
            # simulator, so fixtures exercise the process real runs actually use.
            "fundamental_process": processes.get(name, "gbm"),
            "initial_price": 100.0,
            "initial_stock": 50.0,
            "price_tick_size": 0.01,
            "fundamental_shock_std_dev": 0.03,
            "fundamental_drift_per_step": 0.0,
            "minimum_fundamental_value": 1.0,
        }

    config = {
        "schema_version": 7,
        "assets": {
            "primary": assets[0],
            "covariance_window": 50,
            "fundamental_correlation": fundamental_correlation,
            "definitions": [_definition(name, True) for name in assets],
            "disabled_definitions": [
                _definition(name, False) for name in (disabled_assets or [])
            ],
        },
    }
    (run_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


def write_synthetic_protagonist(
    run_dir: Path,
    *,
    agent_id: int | None = None,
    final_wealth: float = 1400.0,
    steps: int = 60,
) -> dict[str, float]:
    """Promote one agent of an existing synthetic run to protagonist.

    Applied on top of ``write_synthetic_run`` rather than folded into it, so the
    default fixture keeps exercising the far more common archive — one with no
    protagonist at all — and the panel's absence path stays under test.

    The agent is appended with the highest id and a ``final_wealth`` above the
    rest of the population, matching the real simulator: he is an additional
    participant, not a relabelled one.

    Returns the expected standing, so a test can assert the dashboard's rank
    against a number derived here rather than against the dashboard's own
    arithmetic.
    """

    agents = pd.read_csv(run_dir / "agents_final.csv")
    protagonist_id = int(agents["agent_id"].max()) + 1 if agent_id is None else agent_id

    agents["is_protagonist"] = 0
    protagonist = agents.iloc[[0]].copy()
    protagonist["agent_id"] = protagonist_id
    protagonist["is_protagonist"] = 1
    protagonist["current_strategy_type"] = "fundamentalist"
    protagonist["initial_strategy_type"] = "fundamentalist"
    protagonist["initial_wealth"] = 1000.0
    protagonist["final_wealth"] = final_wealth
    agents = pd.concat([agents, protagonist], ignore_index=True)
    agents.to_csv(run_dir / "agents_final.csv", index=False)

    population = len(agents)
    poorer = int((agents["final_wealth"] < final_wealth).sum())
    percentile = poorer / population

    wealth_path = np.linspace(1000.0, final_wealth, steps)
    median_path = np.full(steps, float(agents["final_wealth"].median()))
    pd.DataFrame(
        {
            "simulation_step": np.arange(1, steps + 1),
            "agent_id": protagonist_id,
            "cash": wealth_path * 0.4,
            "primary_asset_stock": np.linspace(4.0, 6.0, steps),
            "wealth": wealth_path,
            "risky_weight": np.full(steps, 0.6),
            "cumulative_trades": np.arange(1, steps + 1),
            "cumulative_traded_volume": np.linspace(0.0, 90.0, steps),
            "cumulative_transaction_costs_paid": np.linspace(0.0, 4.0, steps),
            "population_mean_wealth": median_path,
            "population_median_wealth": median_path,
            "wealth_percentile_rank": np.full(steps, percentile),
            "population_size": population,
        }
    ).to_csv(run_dir / "protagonist_timeseries.csv", index=False)

    return {
        "agent_id": float(protagonist_id),
        "final_wealth": final_wealth,
        "percentile": percentile,
        "rank": float(population - poorer),
        "population": float(population),
        "steps": float(steps),
    }


_make_synthetic_experiment = make_synthetic_experiment
_make_synthetic_benchmark_dir = make_synthetic_benchmark_dir
_write_synthetic_run = write_synthetic_run
