# Configuration key reference

Generated from the compiled-in key registry by `simulate --config-reference`.
Do not edit by hand: a CTest regenerates this file and fails on any difference.

`config/simulation.cfg` is read as plain `key = value` lines. Unknown keys are
rejected, and `assets = ...` must appear before any `asset.<name>.*` key because
per-asset settings are resolved against an already-declared universe.

Check a file without running anything:

```bash
build/debug/simulate --validate --config config/simulation.cfg
```

## Assets

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `assets` |  | one or more unique names | Declares the traded asset universe. Must appear before any asset.<name>.* key. |
| `primary_asset` |  | an enabled declared asset | Asset projected into the single-asset step_timeseries.csv view kept for legacy tooling. It carries no analytical privilege. |
| `asset_fundamental_correlation` | correlation | [-1, 1] | Correlation between the standardised fundamental innovations of the declared assets. Limits the diversification available to the Markowitz allocation rule. |

Each declared asset is configured with `asset.<name>.<field>`:

| Field | Units | Valid range | Description |
| --- | --- | --- | --- |
| `enabled` | boolean | true/false, on/off, yes/no, 1/0 | Whether the asset is tradable. Disabling every declared asset is rejected. |
| `fundamental_process` |  | gbm or random_walk | Functional form of the fundamental value process. gbm is multiplicative in log-return units; random_walk is additive in price units and retained only for older studies. |
| `initial_price` | price | > 0 | Fundamental and market price at initialisation. |
| `initial_stock` | shares per agent | >= 0 | Per-agent endowment; aggregate share supply is num_agents * initial_stock. |
| `price_tick_size` | price | >= 0 | Grid that quoted and executed prices are rounded to. |
| `fundamental_shock_std_dev` | log return per step under gbm; price units under random_walk | >= 0; under gbm an implausibly large value is rejected as a units mistake | Per-step volatility of the fundamental innovation. |
| `fundamental_drift_per_step` | log return per step under gbm; price units under random_walk | finite | Per-step expected growth of the fundamental value. |
| `minimum_fundamental_value` | price | > 0 | Floor applied to the fundamental value so the process cannot reach zero. |

## Population

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `num_fundamentalists` | agents | >= 0; the four counts must not all be zero unless a protagonist is enabled | Number of agents trading on deviations between price and fundamental value. |
| `num_chartists` | agents | >= 0; the four counts must not all be zero unless a protagonist is enabled | Number of agents trading on technical rules selected by chartist_strategy_mode. |
| `num_noise_traders` | agents | >= 0; the four counts must not all be zero unless a protagonist is enabled | Number of agents submitting random-liquidity orders from zero-mean stochastic beliefs. |
| `num_buy_and_hold_agents` | agents | >= 0; the four counts must not all be zero unless a protagonist is enabled | Number of passive long-only investors that accumulate to a target weight and then hold. |

## Protagonist

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `protagonist_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Adds one individually parameterised trader alongside the anonymous population. Disabled runs are byte-for-byte identical to runs made before the protagonist existed. |
| `protagonist_name` |  | free text | Label carried into the agent snapshot and the dashboard panel. Does not affect the run. |
| `protagonist_strategy` |  | fundamentalist, chartist, noise_trader, buy_and_hold | Trading rule he follows for the whole run. The rule itself is the population's; only its parameters are set individually below. |
| `protagonist_chartist_rule` |  | momentum, mean_reversion, rsi, breakout | Concrete technical rule used when protagonist_strategy = chartist. random is rejected: an identified individual's rule must be stated rather than sampled. |
| `protagonist_initial_cash` | currency | >= 0 | His cash endowment at initialisation, independent of initial_cash. |
| `protagonist_initial_stock` | shares per asset | >= 0 | His share endowment, applied to every asset in the universe. |
| `protagonist_risk_aversion` |  | > 0 | Markowitz risk-aversion coefficient used when sizing his risky allocation. |
| `protagonist_min_risky_weight` | weight | finite and <= protagonist_max_risky_weight | Lower bound on the portfolio weight he allocates to risky assets. |
| `protagonist_max_risky_weight` | weight | finite and >= protagonist_min_risky_weight | Upper bound on the portfolio weight he allocates to risky assets. |
| `protagonist_max_gross_exposure` | weight | > 0 | Cap on his multi-asset gross exposure sum_j \|w_j\|. |
| `protagonist_mispricing_threshold` | relative deviation | [0, 1) | Minimum relative deviation from fundamental value before he trades, under the fundamentalist rule. |
| `protagonist_stop_loss_threshold` | relative loss | [0, 1) | Relative loss from his entry price at which he closes a position. |
| `protagonist_take_profit_threshold` | relative gain | [0, 1) | Relative gain from his entry price at which he takes profit. |
| `protagonist_volatility_window` | observations | > 0 | Recent one-period log returns he uses for realised volatility. |
| `protagonist_short_window` | steps | > 0 and <= protagonist_long_window | Short moving-average window used by his momentum rule. |
| `protagonist_long_window` | steps | > 0 and >= protagonist_short_window | Long moving-average window used by his momentum and mean-reversion rules. |
| `protagonist_momentum_signal_threshold` | relative gap | [0, 1) | Deadband applied to weak short-minus-long moving-average gaps. |
| `protagonist_breakout_window` | steps | > 0 | Donchian-style window whose previous high and low define a breakout for him. |
| `protagonist_max_short_weight` | weight | [0, 1] | His maximum short exposure. Forced to 0 when short_selling_enabled is false. |
| `protagonist_noise_belief_shock_std_dev` | log return | > 0 | Standard deviation of the zero-mean shock driving his beliefs, under the noise rule. |
| `protagonist_noise_order_size_fraction` | fraction | (0, 1] | Fraction of investable wealth he commits to one noise order. |
| `protagonist_buy_hold_target_risky_weight` | weight | (0, 1] | Risky-asset share he accumulates to and then holds, under the passive rule. |
| `protagonist_prospect_theory_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Applies Cumulative Prospect Theory valuation to his decisions. Set directly rather than through control_prospect_theory_agent_fraction, whose seeded draw must not decide what an identified individual believes. |
| `protagonist_loss_aversion` | ratio | > 0 when protagonist_prospect_theory_enabled | His loss-aversion coefficient lambda. |
| `protagonist_curvature_for_gain` | exponent | > 0 when protagonist_prospect_theory_enabled | His value-function curvature over gains. |
| `protagonist_curvature_for_loss` | exponent | > 0 when protagonist_prospect_theory_enabled | His value-function curvature over losses. |
| `protagonist_prob_distortion_for_gain` | exponent | > 0 when protagonist_prospect_theory_enabled | His probability-weighting parameter over gain-side cumulative probabilities. |
| `protagonist_prob_distortion_for_loss` | exponent | > 0 when protagonist_prospect_theory_enabled | His probability-weighting parameter over loss-side cumulative probabilities. |

## Run control

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `time_steps` | steps | > 0 | Number of trading steps simulated after warm-up. |
| `warmup_steps` | steps | >= the longest lookback of every active strategy | Pre-trading steps used to seed price history for volatility and technical indicators. |
| `seed` |  | unsigned 64-bit integer | Master random seed. The fundamental process uses seed and the agent side uses seed + 1, so changing agent behaviour cannot perturb the fundamental path. |
| `agent_activity_rate` | probability per step | finite; clamped to [0, 1] | Probability that a given agent is activated in a step. |
| `covariance_window` | observations | >= 2 | Trailing log-return observations used to estimate the asset covariance matrix that feeds the Markowitz portfolio rule. |
| `initial_cash` | currency | >= 0 | Cash endowment granted to every agent at initialisation. |
| `risk_free_rate` | return per step | > -1 | Risk-free return earned on cash balances. |
| `warmup_price_noise_std_dev` | price units | >= 0 | Warm-up price process only. Standard deviation of the noise applied while seeding pre-trading price history. |
| `warmup_fundamental_pull_strength` |  | >= 0 | Warm-up price process only. Strength with which the seeded price history reverts towards the fundamental value. |

## Behavioural finance

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `control_prospect_theory_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Switches Cumulative Prospect Theory valuation on. Set to 0 for an expected-utility baseline run. |
| `control_prospect_theory_agent_fraction` | fraction | [0, 1] | Fraction of the population assigned to use CPT when enabled. Assignment is seeded and reproducible for the same run seed. |
| `control_prospect_heterogeneity_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Draws lambda_i, alpha_i, beta_i and gamma_i per agent instead of using shared values. |
| `control_loss_aversion` | ratio | > 0 when prospect theory is enabled | Loss-aversion coefficient lambda: the factor by which losses loom larger than equivalent gains. |
| `control_loss_aversion_std_dev` | ratio | >= 0 when prospect theory is enabled | Dispersion of lambda_i across agents under heterogeneity. |
| `control_curvature_for_gain` | exponent | > 0 when prospect theory is enabled | Value-function curvature alpha over gains; below 1 gives diminishing sensitivity. |
| `control_curvature_for_gain_std_dev` | exponent | >= 0 when prospect theory is enabled | Dispersion of alpha_i across agents under heterogeneity. |
| `control_curvature_for_loss` | exponent | > 0 when prospect theory is enabled | Value-function curvature beta over losses; below 1 gives diminishing sensitivity. |
| `control_curvature_for_loss_std_dev` | exponent | >= 0 when prospect theory is enabled | Dispersion of beta_i across agents under heterogeneity. |
| `control_prob_distortion_for_gain` | exponent | > 0 when prospect theory is enabled | Probability-weighting parameter applied to gain-side cumulative probabilities. |
| `control_prob_distortion_for_loss` | exponent | > 0 when prospect theory is enabled | Probability-weighting parameter applied to loss-side cumulative probabilities. |
| `control_probability_distortion_min` | exponent | > 0 and <= control_probability_distortion_max | Lower bound of the uniform interval heterogeneous gamma_i is drawn from. |
| `control_probability_distortion_max` | exponent | >= control_probability_distortion_min | Upper bound of the uniform interval heterogeneous gamma_i is drawn from. |
| `control_reference_point` | price or wealth | > 0 when prospect theory is enabled | Reference price or wealth scale used when an agent has no personal entry price. |
| `control_reference_point_mode` |  | configured, average_purchase_price, recent_peak_wealth, moving_average_price, initial_wealth | Rule that determines each agent's gain/loss reference point. |
| `control_reference_moving_average_window` | steps | > 0 when control_reference_point_mode = moving_average_price | Lookback used only by the moving_average_price reference-point rule. |
| `control_prospect_scenario_count` | scenarios | odd integer >= 3 | Number of subjective return scenarios valued by CPT. Use 3 for the original simple distribution; 5 or more gives richer tails. |

## Social influence

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `social_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Switches the spatial social-influence and herding mechanism on. |
| `social_space_width` | space units | > 0 | Width of the two-dimensional space agents are positioned in. |
| `social_space_height` | space units | > 0 | Height of the two-dimensional space agents are positioned in. |
| `social_interaction_radius` | space units | >= 0 | Distance within which two agents are neighbours and exchange opinions. |
| `social_opinion_kappa` |  | >= 0 | Sensitivity of an agent's opinion adjustment to its neighbours' opinions. |
| `social_hold_tolerance` |  | >= 0 | Opinion deadband within which an agent holds rather than trading. |
| `social_gamma_min` | weight | [0, 1] and <= social_gamma_max | Lower bound on the weight an agent places on social rather than private information. |
| `social_gamma_max` | weight | [0, 1] and >= social_gamma_min | Upper bound on the weight an agent places on social rather than private information. |
| `social_private_signal_std_min` |  | >= 0 and <= social_private_signal_std_max | Lower bound on the standard deviation of an agent's private signal noise. |
| `social_private_signal_std_max` |  | >= social_private_signal_std_min | Upper bound on the standard deviation of an agent's private signal noise. |

## Market microstructure

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `market_microstructure` |  | continuous_lob | Market clearing mechanism. Only the continuous persistent limit-order book is supported. |
| `order_expiry_steps` | steps | > 0 | Steps a resting limit order survives before it is removed from the book. |
| `cancellation_base_probability` | probability per step | [0, 1] | Baseline per-step probability that a resting order is cancelled. |
| `cancellation_mispricing_sensitivity` |  | >= 0 | Increase in cancellation probability as a resting order becomes more mispriced. |
| `market_order_probability` | probability | [0, 1] | Probability that an activated agent submits a market rather than a limit order. |
| `market_order_log_gap_threshold` | log price | >= 0 | Log distance between belief and reference price above which an agent prefers immediacy. |
| `market_order_price_collar` | log price | >= 0; 0 disables the collar | Maximum absolute log distance from the reference price at which a market order may execute. |
| `book_depth_levels` | levels | > 0 | Number of price levels per side exported in the order-book depth diagnostics. |

## Trading rules

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `fundamentalist_mispricing_threshold` | relative deviation | [0, 1) | Minimum relative deviation from fundamental value before a fundamentalist trades. |
| `fundamentalist_stop_loss_threshold` | relative loss | [0, 1) | Relative loss at which a fundamentalist closes a position. |
| `fundamentalist_take_profit_threshold` | relative gain | [0, 1) | Relative gain at which a fundamentalist closes a position. |
| `fundamentalist_volatility_window` | observations | > 0 | Recent one-period log returns used for realised volatility. |
| `fundamentalist_risk_aversion` |  | > 0 | Markowitz risk-aversion coefficient used when sizing the risky allocation. |
| `fundamentalist_min_risky_weight` | weight | finite and <= fundamentalist_max_risky_weight | Lower bound on the portfolio weight allocated to risky assets. |
| `fundamentalist_max_risky_weight` | weight | finite and >= fundamentalist_min_risky_weight | Upper bound on the portfolio weight allocated to risky assets. |
| `fundamentalist_max_gross_exposure` | weight | > 0 | Cap on multi-asset gross exposure sum_j \|w_j\|. |
| `chartist_short_window` | steps | > 0 and <= chartist_long_window | Short moving-average window used by the momentum and mean-reversion rules. |
| `chartist_long_window` | steps | > 0 and >= chartist_short_window | Long moving-average window used by the momentum and mean-reversion rules. |
| `chartist_momentum_signal_threshold` | relative gap | [0, 1) | Deadband for weak short-minus-long moving-average gaps. 0 preserves the historical crossover rule. |
| `chartist_breakout_window` | steps | > 0 | Donchian-style window whose previous high and low define a breakout. |
| `chartist_volatility_window` | observations | > 0 | Recent one-period log returns used for realised volatility. |
| `chartist_max_short_weight` | weight | [0, 1] | Maximum short exposure. Forced to 0 when short_selling_enabled is false. |
| `chartist_risk_aversion` |  | > 0 | Markowitz risk-aversion coefficient used when sizing the risky allocation. |
| `chartist_min_risky_weight` | weight | finite and <= chartist_max_risky_weight | Lower bound on the portfolio weight allocated to risky assets. |
| `chartist_max_risky_weight` | weight | finite and >= chartist_min_risky_weight | Upper bound on the portfolio weight allocated to risky assets. |
| `chartist_max_gross_exposure` | weight | > 0 | Cap on multi-asset gross exposure sum_j \|w_j\|. |
| `chartist_strategy_mode` |  | random, momentum, mean_reversion, rsi, breakout | Technical rule chartists follow. random samples all four rules with the configured deterministic seed. |
| `noise_trader_belief_shock_std_dev` | log return | > 0 | Standard deviation of the zero-mean shock driving noise-trader beliefs. |
| `noise_trader_order_size_fraction` | fraction | (0, 1] | Fraction of investable wealth a noise trader commits to one order. |
| `noise_trader_max_short_weight` | weight | [0, 1] | Maximum short exposure. Forced to 0 when short_selling_enabled is false. |
| `buy_hold_target_risky_weight` | weight | (0, 1] | Risky-asset portfolio share buy-and-hold agents accumulate to and then hold. |

## Risk and costs

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `short_selling_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Permits negative risky positions subject to the short-sale margin and borrow limits. |
| `short_sale_initial_margin_requirement` | fraction | > 0 and >= short_sale_maintenance_margin_requirement | Equity fraction required to open a short position, limiting maximum short exposure. |
| `short_sale_maintenance_margin_requirement` | fraction | > 0 and <= short_sale_initial_margin_requirement | Equity fraction below which losses trigger a forced buy-in. |
| `short_sale_borrowable_supply_ratio` | fraction | [0, 1] | Share of aggregate supply available for lending, capping aggregate short interest. |
| `transaction_cost_rate` | fraction per side | [0, 1) | Proportional one-way cost paid by each executed trade side. 0.001 is 10 basis points. |
| `transaction_cost_affects_decisions` | boolean | true/false, on/off, yes/no, 1/0 | Whether agents anticipate transaction costs when valuing a trade, or only pay them. |
| `transaction_cost_apply_to_forced_buy_ins` | boolean | true/false, on/off, yes/no, 1/0 | Whether margin-triggered forced buy-ins also pay the transaction cost. |

## Output and archiving

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `experiment_output_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Archives each run under experiment_root/experiment_name/<run_id>/ with the config that produced it. |
| `experiment_root` | path | relative paths resolve from the config file's directory | Directory holding every experiment. |
| `experiment_name` |  | a directory name | Experiment the run is archived under and compared within. |
| `run_label` |  | free text | Human-readable note recorded in the run manifest; does not affect the run id. |
| `simulation_csv_output` | path | relative paths resolve from the config file's directory | Single-asset step_timeseries.csv view for the primary asset. |
| `asset_timeseries_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Writes the long-format per-(step, asset) series, the authoritative multi-asset view. |
| `asset_timeseries_csv_output` | path | relative paths resolve from the config file's directory | Destination for the long-format per-(step, asset) series. |
| `agent_csv_output` | path | relative paths resolve from the config file's directory | End-of-run wealth, holdings, strategy and behavioural parameters per agent. |
| `protagonist_timeseries_csv_output` | path | relative paths resolve from the config file's directory | Per-step record of the protagonist's position and his standing in the wealth cross-section. Written only when protagonist_enabled is set, because it is meaningless without him. |
| `trade_ledger_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Writes the counterparty-level execution audit. Keep disabled for large calibration sweeps: stylised-fact metrics use aggregate diagnostics and the ledger is costly. |
| `trade_ledger_csv_output` | path | relative paths resolve from the config file's directory | Destination for the counterparty-level trade ledger. |
| `summary_metrics_csv_output` | path | relative paths resolve from the config file's directory | Destination for the run's headline scalars. |
| `stylised_facts_csv_output` | path | relative paths resolve from the config file's directory | Destination for the in-simulator stylised-fact screening block per traded asset. |
| `config_json_output` | path | relative paths resolve from the config file's directory | Destination for the resolved configuration dump that backs the run's config hash. |
| `metadata_json_output` | path | relative paths resolve from the config file's directory | Destination for build metadata: model version, git commit, dirty flag, compiler. |
| `run_log_output` | path | relative paths resolve from the config file's directory | Destination for the run log. |

## Post-processing

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `python_analysis_python` | path or command | an interpreter path, or a bare command resolved on PATH | Interpreter running the PostgreSQL import; normally the project virtual environment. |
| `database_output_enabled` | boolean | true/false, on/off, yes/no, 1/0 | Imports each completed run into PostgreSQL using the connection URL in database_url_env. |
| `database_url_env` |  | an environment variable name | Environment variable holding the SQLAlchemy database URL. |
| `database_prune_after_import` | boolean | true/false, on/off, yes/no, 1/0 | Deletes the staging CSV/JSON artefacts once the database import succeeds. |

## Legacy single-asset spellings

Retained so studies that predate the multi-asset universe still load. They
configure the single implicit asset and cannot be combined with an
`assets = ...` declaration.

| Key | Units | Valid range | Description |
| --- | --- | --- | --- |
| `asset_name` |  | a name without commas, dots or spaces | Legacy single-asset spelling of asset.<name>. Use the assets declaration instead. |
| `initial_price` | price | > 0 | Legacy single-asset spelling of asset.<name>.initial_price. |
| `initial_stock` | shares per agent | >= 0 | Legacy single-asset spelling of asset.<name>.initial_stock. |
| `price_tick_size` | price | >= 0 | Legacy single-asset spelling of asset.<name>.price_tick_size. |
| `fundamental_shock_std_dev` | process units | >= 0 | Legacy single-asset spelling of asset.<name>.fundamental_shock_std_dev. |
| `fundamental_drift_per_step` | process units | finite | Legacy single-asset spelling of asset.<name>.fundamental_drift_per_step. |
| `minimum_fundamental_value` | price | > 0 | Legacy single-asset spelling of asset.<name>.minimum_fundamental_value. |
