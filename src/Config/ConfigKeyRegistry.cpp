// ConfigKeyRegistry.cpp

#include "Config/ConfigKeyRegistry.h"

#include <algorithm>
#include <numeric>
#include <unordered_map>

namespace abm::config_io_detail {
namespace {

constexpr ConfigKeyStatus kCanonical = ConfigKeyStatus::Canonical;
constexpr ConfigKeyStatus kLegacy = ConfigKeyStatus::LegacyScalar;

/*
 * The registry is ordered by research-facing section rather than alphabetically
 * so that the generated reference and the --validate output read in the same
 * order as config/simulation.cfg and the parameter-group table in the README.
 *
 * The `apply` member points at the domain applier that owns the key. Routing
 * dispatch through this table makes it the sole gate on the accepted key set:
 * an applier cannot quietly accept a key that is not described here, because
 * applyRuntimeConfigSetting never reaches an applier without a registry hit.
 */
std::vector<ConfigKeyDescriptor> buildConfigKeyRegistry() {
    return {
        // --- Assets ----------------------------------------------------------
        {"assets", ConfigSection::Assets, kCanonical, "", "one or more unique names",
         "Declares the traded asset universe. Must appear before any asset.<name>.* key.",
         applyAssetSetting},
        {"primary_asset", ConfigSection::Assets, kCanonical, "", "an enabled declared asset",
         "Asset projected into the single-asset step_timeseries.csv view kept for legacy tooling. "
         "It carries no analytical privilege.",
         applyAssetSetting},
        {"asset_fundamental_correlation", ConfigSection::Assets, kCanonical, "correlation",
         "[-1, 1]",
         "Correlation between the standardised fundamental innovations of the declared assets. "
         "Limits the diversification available to the Markowitz allocation rule.",
         applyAssetSetting},

        // --- Population ------------------------------------------------------
        {"num_fundamentalists", ConfigSection::Population, kCanonical, "agents",
         ">= 0; the four counts must not all be zero unless a protagonist is enabled",
         "Number of agents trading on deviations between price and fundamental value.",
         applyCoreSimulationSetting},
        {"num_chartists", ConfigSection::Population, kCanonical, "agents",
         ">= 0; the four counts must not all be zero unless a protagonist is enabled",
         "Number of agents trading on technical rules selected by chartist_strategy_mode.",
         applyCoreSimulationSetting},
        {"num_noise_traders", ConfigSection::Population, kCanonical, "agents",
         ">= 0; the four counts must not all be zero unless a protagonist is enabled",
         "Number of agents submitting random-liquidity orders from zero-mean stochastic beliefs.",
         applyCoreSimulationSetting},
        {"num_buy_and_hold_agents", ConfigSection::Population, kCanonical, "agents",
         ">= 0; the four counts must not all be zero unless a protagonist is enabled",
         "Number of passive long-only investors that accumulate to a target weight and then hold.",
         applyCoreSimulationSetting},

        // --- Protagonist -----------------------------------------------------
        /*
         * One identified individual, added to the population counts above
         * rather than taken out of them. He runs an ordinary strategy; only his
         * parameters are set individually, which is what makes him a traceable
         * case study rather than a new market mechanism.
         */
        {"protagonist_enabled", ConfigSection::Protagonist, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Adds one individually parameterised trader alongside the anonymous population. Disabled "
         "runs are byte-for-byte identical to runs made before the protagonist existed.",
         applyProtagonistSetting},
        {"protagonist_name", ConfigSection::Protagonist, kCanonical, "", "free text",
         "Label carried into the agent snapshot and the dashboard panel. Does not affect the run.",
         applyProtagonistSetting},
        {"protagonist_strategy", ConfigSection::Protagonist, kCanonical, "",
         "fundamentalist, chartist, noise_trader, buy_and_hold",
         "Trading rule he follows for the whole run. The rule itself is the population's; only its "
         "parameters are set individually below.",
         applyProtagonistSetting},
        {"protagonist_chartist_rule", ConfigSection::Protagonist, kCanonical, "",
         "momentum, mean_reversion, rsi, breakout",
         "Concrete technical rule used when protagonist_strategy = chartist. random is rejected: "
         "an "
         "identified individual's rule must be stated rather than sampled.",
         applyProtagonistSetting},
        {"protagonist_initial_cash", ConfigSection::Protagonist, kCanonical, "currency", ">= 0",
         "His cash endowment at initialisation, independent of initial_cash.",
         applyProtagonistSetting},
        {"protagonist_initial_stock", ConfigSection::Protagonist, kCanonical, "shares per asset",
         ">= 0", "His share endowment, applied to every asset in the universe.",
         applyProtagonistSetting},
        {"protagonist_risk_aversion", ConfigSection::Protagonist, kCanonical, "", "> 0",
         "Markowitz risk-aversion coefficient used when sizing his risky allocation.",
         applyProtagonistSetting},
        {"protagonist_min_risky_weight", ConfigSection::Protagonist, kCanonical, "weight",
         "finite and <= protagonist_max_risky_weight",
         "Lower bound on the portfolio weight he allocates to risky assets.",
         applyProtagonistSetting},
        {"protagonist_max_risky_weight", ConfigSection::Protagonist, kCanonical, "weight",
         "finite and >= protagonist_min_risky_weight",
         "Upper bound on the portfolio weight he allocates to risky assets.",
         applyProtagonistSetting},
        {"protagonist_max_gross_exposure", ConfigSection::Protagonist, kCanonical, "weight", "> 0",
         "Cap on his multi-asset gross exposure sum_j |w_j|.", applyProtagonistSetting},
        {"protagonist_mispricing_threshold", ConfigSection::Protagonist, kCanonical,
         "relative deviation", "[0, 1)",
         "Minimum relative deviation from fundamental value before he trades, under the "
         "fundamentalist rule.",
         applyProtagonistSetting},
        {"protagonist_stop_loss_threshold", ConfigSection::Protagonist, kCanonical, "relative loss",
         "[0, 1)", "Relative loss from his entry price at which he closes a position.",
         applyProtagonistSetting},
        {"protagonist_take_profit_threshold", ConfigSection::Protagonist, kCanonical,
         "relative gain", "[0, 1)", "Relative gain from his entry price at which he takes profit.",
         applyProtagonistSetting},
        {"protagonist_volatility_window", ConfigSection::Protagonist, kCanonical, "observations",
         "> 0", "Recent one-period log returns he uses for realised volatility.",
         applyProtagonistSetting},
        {"protagonist_forecast_horizon", ConfigSection::Protagonist, kCanonical, "steps", ">= 1",
         "Steps over which he expects his forecast to play out, under the fundamentalist and "
         "chartist rules. 1 reproduces the one-step rule.",
         applyProtagonistSetting},
        {"protagonist_short_window", ConfigSection::Protagonist, kCanonical, "steps",
         "> 0 and <= protagonist_long_window",
         "Short moving-average window used by his momentum rule.", applyProtagonistSetting},
        {"protagonist_long_window", ConfigSection::Protagonist, kCanonical, "steps",
         "> 0 and >= protagonist_short_window",
         "Long moving-average window used by his momentum and mean-reversion rules.",
         applyProtagonistSetting},
        {"protagonist_momentum_signal_threshold", ConfigSection::Protagonist, kCanonical,
         "relative gap", "[0, 1)", "Deadband applied to weak short-minus-long moving-average gaps.",
         applyProtagonistSetting},
        {"protagonist_breakout_window", ConfigSection::Protagonist, kCanonical, "steps", "> 0",
         "Donchian-style window whose previous high and low define a breakout for him.",
         applyProtagonistSetting},
        {"protagonist_max_short_weight", ConfigSection::Protagonist, kCanonical, "weight", "[0, 1]",
         "His maximum short exposure. Forced to 0 when short_selling_enabled is false.",
         applyProtagonistSetting},
        {"protagonist_noise_belief_shock_std_dev", ConfigSection::Protagonist, kCanonical,
         "log return", "> 0",
         "Standard deviation of the zero-mean shock driving his beliefs, under the noise rule.",
         applyProtagonistSetting},
        {"protagonist_noise_order_size_fraction", ConfigSection::Protagonist, kCanonical,
         "fraction", "(0, 1]", "Fraction of investable wealth he commits to one noise order.",
         applyProtagonistSetting},
        {"protagonist_buy_hold_target_risky_weight", ConfigSection::Protagonist, kCanonical,
         "weight", "(0, 1]",
         "Risky-asset share he accumulates to and then holds, under the passive rule.",
         applyProtagonistSetting},
        {"protagonist_prospect_theory_enabled", ConfigSection::Protagonist, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Applies Cumulative Prospect Theory valuation to his decisions. Set directly rather than "
         "through control_prospect_theory_agent_fraction, whose seeded draw must not decide what "
         "an "
         "identified individual believes.",
         applyProtagonistSetting},
        {"protagonist_loss_aversion", ConfigSection::Protagonist, kCanonical, "ratio",
         "> 0 when protagonist_prospect_theory_enabled", "His loss-aversion coefficient lambda.",
         applyProtagonistSetting},
        {"protagonist_curvature_for_gain", ConfigSection::Protagonist, kCanonical, "exponent",
         "> 0 when protagonist_prospect_theory_enabled", "His value-function curvature over gains.",
         applyProtagonistSetting},
        {"protagonist_curvature_for_loss", ConfigSection::Protagonist, kCanonical, "exponent",
         "> 0 when protagonist_prospect_theory_enabled",
         "His value-function curvature over losses.", applyProtagonistSetting},
        {"protagonist_prob_distortion_for_gain", ConfigSection::Protagonist, kCanonical, "exponent",
         "> 0 when protagonist_prospect_theory_enabled",
         "His probability-weighting parameter over gain-side cumulative probabilities.",
         applyProtagonistSetting},
        {"protagonist_prob_distortion_for_loss", ConfigSection::Protagonist, kCanonical, "exponent",
         "> 0 when protagonist_prospect_theory_enabled",
         "His probability-weighting parameter over loss-side cumulative probabilities.",
         applyProtagonistSetting},

        // --- Run control -----------------------------------------------------
        {"time_steps", ConfigSection::RunControl, kCanonical, "steps", "> 0",
         "Number of trading steps simulated after warm-up.", applyCoreSimulationSetting},
        {"warmup_steps", ConfigSection::RunControl, kCanonical, "steps",
         ">= the longest lookback of every active strategy",
         "Pre-trading steps used to seed price history for volatility and technical indicators.",
         applyCoreSimulationSetting},
        {"seed", ConfigSection::RunControl, kCanonical, "", "unsigned 64-bit integer",
         "Master random seed. The fundamental process uses seed and the agent side uses seed + 1, "
         "so changing agent behaviour cannot perturb the fundamental path.",
         applyCoreSimulationSetting},
        {"agent_activity_rate", ConfigSection::RunControl, kCanonical, "probability per step",
         "finite; clamped to [0, 1]", "Probability that a given agent is activated in a step.",
         applyCoreSimulationSetting},
        {"covariance_window", ConfigSection::RunControl, kCanonical, "observations", ">= 2",
         "Trailing log-return observations used to estimate the asset covariance matrix that feeds "
         "the Markowitz portfolio rule.",
         applyCoreSimulationSetting},
        {"initial_cash", ConfigSection::RunControl, kCanonical, "currency", ">= 0",
         "Cash endowment granted to every agent at initialisation.", applyCoreSimulationSetting},
        {"risk_free_rate", ConfigSection::RunControl, kCanonical, "return per step", "> -1",
         "Risk-free return earned on cash balances.", applyCoreSimulationSetting},
        {"warmup_price_noise_std_dev", ConfigSection::RunControl, kCanonical, "price units", ">= 0",
         "Warm-up price process only. Standard deviation of the noise applied while seeding "
         "pre-trading price history.",
         applyWarmupPriceSetting},
        {"warmup_fundamental_pull_strength", ConfigSection::RunControl, kCanonical, "", ">= 0",
         "Warm-up price process only. Strength with which the seeded price history reverts towards "
         "the fundamental value.",
         applyWarmupPriceSetting},

        // --- Behavioural finance (Cumulative Prospect Theory) ----------------
        {"control_prospect_theory_enabled", ConfigSection::Behavioural, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Switches Cumulative Prospect Theory valuation on. Set to 0 for an expected-utility "
         "baseline run.",
         applyControlSetting},
        {"control_prospect_theory_agent_fraction", ConfigSection::Behavioural, kCanonical,
         "fraction", "[0, 1]",
         "Fraction of the population assigned to use CPT when enabled. Assignment is seeded and "
         "reproducible for the same run seed.",
         applyControlSetting},
        {"control_prospect_heterogeneity_enabled", ConfigSection::Behavioural, kCanonical,
         "boolean", "true/false, on/off, yes/no, 1/0",
         "Draws lambda_i, alpha_i, beta_i and gamma_i per agent instead of using shared values.",
         applyControlSetting},
        {"control_loss_aversion", ConfigSection::Behavioural, kCanonical, "ratio",
         "> 0 when prospect theory is enabled",
         "Loss-aversion coefficient lambda: the factor by which losses loom larger than equivalent "
         "gains.",
         applyControlSetting},
        {"control_loss_aversion_std_dev", ConfigSection::Behavioural, kCanonical, "ratio",
         ">= 0 when prospect theory is enabled",
         "Dispersion of lambda_i across agents under heterogeneity.", applyControlSetting},
        {"control_curvature_for_gain", ConfigSection::Behavioural, kCanonical, "exponent",
         "> 0 when prospect theory is enabled",
         "Value-function curvature alpha over gains; below 1 gives diminishing sensitivity.",
         applyControlSetting},
        {"control_curvature_for_gain_std_dev", ConfigSection::Behavioural, kCanonical, "exponent",
         ">= 0 when prospect theory is enabled",
         "Dispersion of alpha_i across agents under heterogeneity.", applyControlSetting},
        {"control_curvature_for_loss", ConfigSection::Behavioural, kCanonical, "exponent",
         "> 0 when prospect theory is enabled",
         "Value-function curvature beta over losses; below 1 gives diminishing sensitivity.",
         applyControlSetting},
        {"control_curvature_for_loss_std_dev", ConfigSection::Behavioural, kCanonical, "exponent",
         ">= 0 when prospect theory is enabled",
         "Dispersion of beta_i across agents under heterogeneity.", applyControlSetting},
        {"control_prob_distortion_for_gain", ConfigSection::Behavioural, kCanonical, "exponent",
         "> 0 when prospect theory is enabled",
         "Probability-weighting parameter applied to gain-side cumulative probabilities.",
         applyControlSetting},
        {"control_prob_distortion_for_loss", ConfigSection::Behavioural, kCanonical, "exponent",
         "> 0 when prospect theory is enabled",
         "Probability-weighting parameter applied to loss-side cumulative probabilities.",
         applyControlSetting},
        {"control_probability_distortion_min", ConfigSection::Behavioural, kCanonical, "exponent",
         "> 0 and <= control_probability_distortion_max",
         "Lower bound of the uniform interval heterogeneous gamma_i is drawn from.",
         applyControlSetting},
        {"control_probability_distortion_max", ConfigSection::Behavioural, kCanonical, "exponent",
         ">= control_probability_distortion_min",
         "Upper bound of the uniform interval heterogeneous gamma_i is drawn from.",
         applyControlSetting},
        {"control_reference_point", ConfigSection::Behavioural, kCanonical, "price or wealth",
         "> 0 when prospect theory is enabled",
         "Reference price or wealth scale used when an agent has no personal entry price.",
         applyControlSetting},
        {"control_reference_point_mode", ConfigSection::Behavioural, kCanonical, "",
         "configured, average_purchase_price, recent_peak_wealth, moving_average_price, "
         "initial_wealth",
         "Rule that determines each agent's gain/loss reference point.", applyControlSetting},
        {"control_reference_moving_average_window", ConfigSection::Behavioural, kCanonical, "steps",
         "> 0 when control_reference_point_mode = moving_average_price",
         "Lookback used only by the moving_average_price reference-point rule.",
         applyControlSetting},
        {"control_prospect_scenario_count", ConfigSection::Behavioural, kCanonical, "scenarios",
         "odd integer >= 3",
         "Number of scenarios in the moment-matched return ladder valued by CPT. The ladder "
         "variance equals the forecast volatility squared for every count, so the count sets "
         "only the resolution of the tails; results settle by about 13.",
         applyControlSetting},

        // --- Social influence ------------------------------------------------
        {"social_enabled", ConfigSection::Social, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Switches the spatial social-influence and herding mechanism on.", applySocialSetting},
        {"social_space_width", ConfigSection::Social, kCanonical, "space units", "> 0",
         "Width of the two-dimensional space agents are positioned in.", applySocialSetting},
        {"social_space_height", ConfigSection::Social, kCanonical, "space units", "> 0",
         "Height of the two-dimensional space agents are positioned in.", applySocialSetting},
        {"social_interaction_radius", ConfigSection::Social, kCanonical, "space units", ">= 0",
         "Distance within which two agents are neighbours and exchange opinions.",
         applySocialSetting},
        {"social_opinion_kappa", ConfigSection::Social, kCanonical, "", ">= 0",
         "Sensitivity of an agent's opinion adjustment to its neighbours' opinions.",
         applySocialSetting},
        {"social_hold_tolerance", ConfigSection::Social, kCanonical, "", ">= 0",
         "Opinion deadband within which an agent holds rather than trading.", applySocialSetting},
        {"social_gamma_min", ConfigSection::Social, kCanonical, "weight",
         "[0, 1] and <= social_gamma_max",
         "Lower bound on the weight an agent places on social rather than private information.",
         applySocialSetting},
        {"social_gamma_max", ConfigSection::Social, kCanonical, "weight",
         "[0, 1] and >= social_gamma_min",
         "Upper bound on the weight an agent places on social rather than private information.",
         applySocialSetting},
        {"social_private_signal_std_min", ConfigSection::Social, kCanonical, "",
         ">= 0 and <= social_private_signal_std_max",
         "Lower bound on the standard deviation of an agent's private signal noise.",
         applySocialSetting},
        {"social_private_signal_std_max", ConfigSection::Social, kCanonical, "",
         ">= social_private_signal_std_min",
         "Upper bound on the standard deviation of an agent's private signal noise.",
         applySocialSetting},

        // --- Market microstructure -------------------------------------------
        {"market_microstructure", ConfigSection::Microstructure, kCanonical, "", "continuous_lob",
         "Market clearing mechanism. Only the continuous persistent limit-order book is supported.",
         applyMicrostructureSetting},
        {"order_expiry_steps", ConfigSection::Microstructure, kCanonical, "steps", "> 0",
         "Steps a resting limit order survives before it is removed from the book.",
         applyMicrostructureSetting},
        {"cancellation_base_probability", ConfigSection::Microstructure, kCanonical,
         "probability per step", "[0, 1]",
         "Baseline per-step probability that a resting order is cancelled.",
         applyMicrostructureSetting},
        {"cancellation_mispricing_sensitivity", ConfigSection::Microstructure, kCanonical, "",
         ">= 0", "Increase in cancellation probability as a resting order becomes more mispriced.",
         applyMicrostructureSetting},
        {"market_order_probability", ConfigSection::Microstructure, kCanonical, "probability",
         "[0, 1]",
         "Probability that an activated agent submits a market rather than a limit order.",
         applyMicrostructureSetting},
        {"market_order_log_gap_threshold", ConfigSection::Microstructure, kCanonical, "log price",
         ">= 0",
         "Log distance between belief and reference price above which an agent prefers immediacy.",
         applyMicrostructureSetting},
        {"market_order_price_collar", ConfigSection::Microstructure, kCanonical, "log price",
         ">= 0; 0 disables the collar",
         "Maximum absolute log distance from the reference price at which a market order may "
         "execute.",
         applyMicrostructureSetting},
        {"book_depth_levels", ConfigSection::Microstructure, kCanonical, "levels", "> 0",
         "Number of price levels per side exported in the order-book depth diagnostics.",
         applyMicrostructureSetting},

        // --- Trading rules ---------------------------------------------------
        {"fundamentalist_mispricing_threshold", ConfigSection::Strategy, kCanonical,
         "relative deviation", "[0, 1)",
         "Minimum relative deviation from fundamental value before a fundamentalist trades.",
         applyFundamentalistSetting},
        {"fundamentalist_stop_loss_threshold", ConfigSection::Strategy, kCanonical, "relative loss",
         "[0, 1)", "Relative loss at which a fundamentalist closes a position.",
         applyFundamentalistSetting},
        {"fundamentalist_take_profit_threshold", ConfigSection::Strategy, kCanonical,
         "relative gain", "[0, 1)", "Relative gain at which a fundamentalist closes a position.",
         applyFundamentalistSetting},
        {"fundamentalist_volatility_window", ConfigSection::Strategy, kCanonical, "observations",
         "> 0", "Recent one-period log returns used for realised volatility.",
         applyFundamentalistSetting},
        {"fundamentalist_forecast_horizon", ConfigSection::Strategy, kCanonical, "steps", ">= 1",
         "Steps over which a fundamentalist expects the mispricing to close. Sizing uses the "
         "mispricing divided by this horizon and CPT values the gamble over it. 1 reproduces the "
         "one-step rule.",
         applyFundamentalistSetting},
        {"fundamentalist_risk_aversion", ConfigSection::Strategy, kCanonical, "", "> 0",
         "Markowitz risk-aversion coefficient used when sizing the risky allocation.",
         applyFundamentalistSetting},
        {"fundamentalist_min_risky_weight", ConfigSection::Strategy, kCanonical, "weight",
         "finite and <= fundamentalist_max_risky_weight",
         "Lower bound on the portfolio weight allocated to risky assets.",
         applyFundamentalistSetting},
        {"fundamentalist_max_risky_weight", ConfigSection::Strategy, kCanonical, "weight",
         "finite and >= fundamentalist_min_risky_weight",
         "Upper bound on the portfolio weight allocated to risky assets.",
         applyFundamentalistSetting},
        {"fundamentalist_max_gross_exposure", ConfigSection::Strategy, kCanonical, "weight", "> 0",
         "Cap on multi-asset gross exposure sum_j |w_j|.", applyFundamentalistSetting},
        {"chartist_short_window", ConfigSection::Strategy, kCanonical, "steps",
         "> 0 and <= chartist_long_window",
         "Short moving-average window used by the momentum and mean-reversion rules.",
         applyChartistSetting},
        {"chartist_long_window", ConfigSection::Strategy, kCanonical, "steps",
         "> 0 and >= chartist_short_window",
         "Long moving-average window used by the momentum and mean-reversion rules.",
         applyChartistSetting},
        {"chartist_momentum_signal_threshold", ConfigSection::Strategy, kCanonical, "relative gap",
         "[0, 1)",
         "Deadband for weak short-minus-long moving-average gaps. 0 preserves the historical "
         "crossover rule.",
         applyChartistSetting},
        {"chartist_breakout_window", ConfigSection::Strategy, kCanonical, "steps", "> 0",
         "Donchian-style window whose previous high and low define a breakout.",
         applyChartistSetting},
        {"chartist_volatility_window", ConfigSection::Strategy, kCanonical, "observations", "> 0",
         "Recent one-period log returns used for realised volatility.", applyChartistSetting},
        {"chartist_forecast_horizon", ConfigSection::Strategy, kCanonical, "steps", ">= 1",
         "Steps over which a chartist expects its technical forecast to play out. Sizing uses the "
         "forecast divided by this horizon and CPT values the gamble over it. 1 reproduces the "
         "one-step rule.",
         applyChartistSetting},
        {"chartist_max_short_weight", ConfigSection::Strategy, kCanonical, "weight", "[0, 1]",
         "Maximum short exposure. Forced to 0 when short_selling_enabled is false.",
         applyChartistSetting},
        {"chartist_risk_aversion", ConfigSection::Strategy, kCanonical, "", "> 0",
         "Markowitz risk-aversion coefficient used when sizing the risky allocation.",
         applyChartistSetting},
        {"chartist_min_risky_weight", ConfigSection::Strategy, kCanonical, "weight",
         "finite and <= chartist_max_risky_weight",
         "Lower bound on the portfolio weight allocated to risky assets.", applyChartistSetting},
        {"chartist_max_risky_weight", ConfigSection::Strategy, kCanonical, "weight",
         "finite and >= chartist_min_risky_weight",
         "Upper bound on the portfolio weight allocated to risky assets.", applyChartistSetting},
        {"chartist_max_gross_exposure", ConfigSection::Strategy, kCanonical, "weight", "> 0",
         "Cap on multi-asset gross exposure sum_j |w_j|.", applyChartistSetting},
        {"chartist_strategy_mode", ConfigSection::Strategy, kCanonical, "",
         "random, momentum, mean_reversion, rsi, breakout",
         "Technical rule chartists follow. random samples all four rules with the configured "
         "deterministic seed.",
         applyChartistSetting},
        {"noise_trader_belief_shock_std_dev", ConfigSection::Strategy, kCanonical, "log return",
         "> 0", "Standard deviation of the zero-mean shock driving noise-trader beliefs.",
         applyNoiseTraderSetting},
        {"noise_trader_order_size_fraction", ConfigSection::Strategy, kCanonical, "fraction",
         "(0, 1]", "Fraction of investable wealth a noise trader commits to one order.",
         applyNoiseTraderSetting},
        {"noise_trader_max_short_weight", ConfigSection::Strategy, kCanonical, "weight", "[0, 1]",
         "Maximum short exposure. Forced to 0 when short_selling_enabled is false.",
         applyNoiseTraderSetting},
        {"buy_hold_target_risky_weight", ConfigSection::Strategy, kCanonical, "weight", "(0, 1]",
         "Risky-asset portfolio share buy-and-hold agents accumulate to and then hold.",
         applyBuyAndHoldSetting},

        // --- Risk and costs --------------------------------------------------
        {"short_selling_enabled", ConfigSection::RiskAndCosts, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Permits negative risky positions subject to the short-sale margin and borrow limits.",
         applyCoreSimulationSetting},
        {"short_sale_initial_margin_requirement", ConfigSection::RiskAndCosts, kCanonical,
         "fraction", "> 0 and >= short_sale_maintenance_margin_requirement",
         "Equity fraction required to open a short position, limiting maximum short exposure.",
         applyShortSaleSetting},
        {"short_sale_maintenance_margin_requirement", ConfigSection::RiskAndCosts, kCanonical,
         "fraction", "> 0 and <= short_sale_initial_margin_requirement",
         "Equity fraction below which losses trigger a forced buy-in.", applyShortSaleSetting},
        {"short_sale_borrowable_supply_ratio", ConfigSection::RiskAndCosts, kCanonical, "fraction",
         "[0, 1]",
         "Share of aggregate supply available for lending, capping aggregate short interest.",
         applyShortSaleSetting},
        {"transaction_cost_rate", ConfigSection::RiskAndCosts, kCanonical, "fraction per side",
         "[0, 1)",
         "Proportional one-way cost paid by each executed trade side. 0.001 is 10 basis points.",
         applyTransactionCostSetting},
        {"transaction_cost_affects_decisions", ConfigSection::RiskAndCosts, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Whether agents anticipate transaction costs when valuing a trade, or only pay them.",
         applyTransactionCostSetting},
        {"transaction_cost_apply_to_forced_buy_ins", ConfigSection::RiskAndCosts, kCanonical,
         "boolean", "true/false, on/off, yes/no, 1/0",
         "Whether margin-triggered forced buy-ins also pay the transaction cost.",
         applyTransactionCostSetting},

        // --- Output and archiving --------------------------------------------
        {"experiment_output_enabled", ConfigSection::Output, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Archives each run under experiment_root/experiment_name/<run_id>/ with the config that "
         "produced it.",
         applyExperimentOutputSetting},
        {"experiment_root", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Directory holding every experiment.", applyExperimentOutputSetting},
        {"experiment_name", ConfigSection::Output, kCanonical, "", "a directory name",
         "Experiment the run is archived under and compared within.", applyExperimentOutputSetting},
        {"run_label", ConfigSection::Output, kCanonical, "", "free text",
         "Human-readable note recorded in the run manifest; does not affect the run id.",
         applyExperimentOutputSetting},
        {"simulation_csv_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Single-asset step_timeseries.csv view for the primary asset.",
         applyArtifactOutputSetting},
        {"asset_timeseries_enabled", ConfigSection::Output, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Writes the long-format per-(step, asset) series, the authoritative multi-asset view.",
         applyArtifactOutputSetting},
        {"asset_timeseries_csv_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Destination for the long-format per-(step, asset) series.", applyArtifactOutputSetting},
        {"agent_csv_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "End-of-run wealth, holdings, strategy and behavioural parameters per agent.",
         applyArtifactOutputSetting},
        {"protagonist_timeseries_csv_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Per-step record of the protagonist's position and his standing in the wealth "
         "cross-section. Written only when protagonist_enabled is set, because it is meaningless "
         "without him.",
         applyArtifactOutputSetting},
        {"trade_ledger_enabled", ConfigSection::Output, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Writes the counterparty-level execution audit. Keep disabled for large calibration "
         "sweeps: stylised-fact metrics use aggregate diagnostics and the ledger is costly.",
         applyArtifactOutputSetting},
        {"trade_ledger_csv_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Destination for the counterparty-level trade ledger.", applyArtifactOutputSetting},
        {"summary_metrics_csv_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Destination for the run's headline scalars.", applyArtifactOutputSetting},
        {"stylised_facts_csv_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Destination for the in-simulator stylised-fact screening block per traded asset.",
         applyArtifactOutputSetting},
        {"config_json_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Destination for the resolved configuration dump that backs the run's config hash.",
         applyArtifactOutputSetting},
        {"metadata_json_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory",
         "Destination for build metadata: model version, git commit, dirty flag, compiler.",
         applyArtifactOutputSetting},
        {"run_log_output", ConfigSection::Output, kCanonical, "path",
         "relative paths resolve from the config file's directory", "Destination for the run log.",
         applyArtifactOutputSetting},

        // --- Post-processing --------------------------------------------------
        {"python_analysis_python", ConfigSection::PostProcessing, kCanonical, "path or command",
         "an interpreter path, or a bare command resolved on PATH",
         "Interpreter running the PostgreSQL import; normally the project virtual environment.",
         applyPythonOutputSetting},
        {"database_output_enabled", ConfigSection::PostProcessing, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Imports each completed run into PostgreSQL using the connection URL in database_url_env.",
         applyDatabaseOutputSetting},
        {"database_url_env", ConfigSection::PostProcessing, kCanonical, "",
         "an environment variable name",
         "Environment variable holding the SQLAlchemy database URL.", applyDatabaseOutputSetting},
        {"database_prune_after_import", ConfigSection::PostProcessing, kCanonical, "boolean",
         "true/false, on/off, yes/no, 1/0",
         "Deletes the staging CSV/JSON artefacts once the database import succeeds.",
         applyDatabaseOutputSetting},

        // --- Legacy single-asset spellings -----------------------------------
        /*
         * Retained so studies that predate the multi-asset universe still load.
         * They configure the single implicit asset and cannot be combined with an
         * `assets = ...` declaration, so their absence from a modern config is
         * correct rather than an omission.
         */
        {"asset_name", ConfigSection::Assets, kLegacy, "", "a name without commas, dots or spaces",
         "Legacy single-asset spelling of asset.<name>. Use the assets declaration instead.",
         applyCoreSimulationSetting},
        {"initial_price", ConfigSection::Assets, kLegacy, "price", "> 0",
         "Legacy single-asset spelling of asset.<name>.initial_price.", applyCoreSimulationSetting},
        {"initial_stock", ConfigSection::Assets, kLegacy, "shares per agent", ">= 0",
         "Legacy single-asset spelling of asset.<name>.initial_stock.", applyCoreSimulationSetting},
        {"price_tick_size", ConfigSection::Assets, kLegacy, "price", ">= 0",
         "Legacy single-asset spelling of asset.<name>.price_tick_size.",
         applyCoreSimulationSetting},
        {"fundamental_shock_std_dev", ConfigSection::Assets, kLegacy, "process units", ">= 0",
         "Legacy single-asset spelling of asset.<name>.fundamental_shock_std_dev.",
         applyCoreSimulationSetting},
        {"fundamental_drift_per_step", ConfigSection::Assets, kLegacy, "process units", "finite",
         "Legacy single-asset spelling of asset.<name>.fundamental_drift_per_step.",
         applyCoreSimulationSetting},
        {"minimum_fundamental_value", ConfigSection::Assets, kLegacy, "price", "> 0",
         "Legacy single-asset spelling of asset.<name>.minimum_fundamental_value.",
         applyCoreSimulationSetting},
    };
}

std::vector<PerAssetFieldDescriptor> buildPerAssetFieldRegistry() {
    return {
        {"enabled", "boolean", "true/false, on/off, yes/no, 1/0",
         "Whether the asset is tradable. Disabling every declared asset is rejected."},
        {"fundamental_process", "", "gbm or random_walk",
         "Functional form of the fundamental value process. gbm is multiplicative in log-return "
         "units; random_walk is additive in price units and retained only for older studies."},
        {"initial_price", "price", "> 0", "Fundamental and market price at initialisation."},
        {"initial_stock", "shares per agent", ">= 0",
         "Per-agent endowment; aggregate share supply is num_agents * initial_stock."},
        {"price_tick_size", "price", ">= 0",
         "Grid that quoted and executed prices are rounded to."},
        {"fundamental_shock_std_dev",
         "log return per step under gbm; price units under random_walk",
         ">= 0; under gbm an implausibly large value is rejected as a units mistake",
         "Per-step volatility of the fundamental innovation."},
        {"fundamental_drift_per_step",
         "log return per step under gbm; price units under random_walk", "finite",
         "Per-step expected growth of the fundamental value."},
        {"minimum_fundamental_value", "price", "> 0",
         "Floor applied to the fundamental value so the process cannot reach zero."},
    };
}

/**
 * Levenshtein edit distance, used only to suggest corrections for typed keys.
 *
 * The two-row formulation keeps the working set proportional to the shorter
 * string, which matters only because the suggestion search runs over every
 * registry key for each unknown key encountered.
 */
[[nodiscard]] std::size_t editDistance(const std::string& left, const std::string& right) {
    std::vector<std::size_t> previousRow(right.size() + 1);
    std::vector<std::size_t> currentRow(right.size() + 1);
    std::iota(previousRow.begin(), previousRow.end(), std::size_t{0});

    for (std::size_t leftIndex = 1; leftIndex <= left.size(); ++leftIndex) {
        currentRow[0] = leftIndex;
        for (std::size_t rightIndex = 1; rightIndex <= right.size(); ++rightIndex) {
            const std::size_t substitutionCost =
                left[leftIndex - 1] == right[rightIndex - 1] ? 0 : 1;
            currentRow[rightIndex] =
                std::min({currentRow[rightIndex - 1] + 1, previousRow[rightIndex] + 1,
                          previousRow[rightIndex - 1] + substitutionCost});
        }
        previousRow.swap(currentRow);
    }

    return previousRow[right.size()];
}

/*
 * A cutoff proportional to the key length keeps suggestions trustworthy: a
 * single typo in a long key is still caught, while a short unrelated key never
 * attracts a misleading "did you mean".
 */
[[nodiscard]] std::size_t suggestionCutoff(const std::string& key) {
    return std::min<std::size_t>(4, std::max<std::size_t>(2, key.size() / 4));
}

template <typename Candidates>
[[nodiscard]] std::vector<std::string>
nearestFrom(const Candidates& candidates, const std::string& key, std::size_t maximumSuggestions) {
    if (key.empty() || maximumSuggestions == 0) {
        return {};
    }

    const std::size_t cutoff = suggestionCutoff(key);
    std::vector<std::pair<std::size_t, std::string>> scored;
    for (const auto& candidate : candidates) {
        std::string candidateKey(candidate);
        const std::size_t distance = editDistance(key, candidateKey);
        if (distance <= cutoff) {
            scored.emplace_back(distance, std::move(candidateKey));
        }
    }

    std::sort(scored.begin(), scored.end());
    if (scored.size() > maximumSuggestions) {
        scored.resize(maximumSuggestions);
    }

    std::vector<std::string> suggestions;
    suggestions.reserve(scored.size());
    for (auto& entry : scored) {
        suggestions.push_back(std::move(entry.second));
    }
    return suggestions;
}

} // namespace

std::string_view configSectionName(ConfigSection section) {
    switch (section) {
    case ConfigSection::Assets:
        return "Assets";
    case ConfigSection::Population:
        return "Population";
    case ConfigSection::Protagonist:
        return "Protagonist";
    case ConfigSection::RunControl:
        return "Run control";
    case ConfigSection::Behavioural:
        return "Behavioural finance";
    case ConfigSection::Social:
        return "Social influence";
    case ConfigSection::Microstructure:
        return "Market microstructure";
    case ConfigSection::Strategy:
        return "Trading rules";
    case ConfigSection::RiskAndCosts:
        return "Risk and costs";
    case ConfigSection::Output:
        return "Output and archiving";
    case ConfigSection::PostProcessing:
        return "Post-processing";
    }
    return "Unknown";
}

const std::vector<ConfigKeyDescriptor>& configKeyRegistry() {
    static const std::vector<ConfigKeyDescriptor> registry = buildConfigKeyRegistry();
    return registry;
}

const std::vector<PerAssetFieldDescriptor>& perAssetFieldRegistry() {
    static const std::vector<PerAssetFieldDescriptor> registry = buildPerAssetFieldRegistry();
    return registry;
}

const ConfigKeyDescriptor* findConfigKey(std::string_view key) {
    static const std::unordered_map<std::string_view, const ConfigKeyDescriptor*> index = [] {
        std::unordered_map<std::string_view, const ConfigKeyDescriptor*> built;
        for (const ConfigKeyDescriptor& descriptor : configKeyRegistry()) {
            built.emplace(descriptor.key, &descriptor);
        }
        return built;
    }();

    const auto found = index.find(key);
    return found == index.end() ? nullptr : found->second;
}

std::vector<std::string> nearestConfigKeys(const std::string& key, std::size_t maximumSuggestions) {
    std::vector<std::string_view> candidates;
    candidates.reserve(configKeyRegistry().size());
    for (const ConfigKeyDescriptor& descriptor : configKeyRegistry()) {
        if (descriptor.status == ConfigKeyStatus::Canonical) {
            candidates.push_back(descriptor.key);
        }
    }
    return nearestFrom(candidates, key, maximumSuggestions);
}

std::vector<std::string> nearestPerAssetFields(const std::string& field,
                                               std::size_t maximumSuggestions) {
    std::vector<std::string_view> candidates;
    candidates.reserve(perAssetFieldRegistry().size());
    for (const PerAssetFieldDescriptor& descriptor : perAssetFieldRegistry()) {
        candidates.push_back(descriptor.field);
    }
    return nearestFrom(candidates, field, maximumSuggestions);
}

std::string describeSuggestions(const std::vector<std::string>& suggestions) {
    if (suggestions.empty()) {
        return {};
    }
    if (suggestions.size() == 1) {
        return " Did you mean '" + suggestions.front() + "'?";
    }

    std::string description = " Did you mean '" + suggestions.front() + "'";
    for (std::size_t index = 1; index + 1 < suggestions.size(); ++index) {
        description += ", '" + suggestions[index] + "'";
    }
    description += " or '" + suggestions.back() + "'?";
    return description;
}

} // namespace abm::config_io_detail

namespace abm {

std::vector<std::string> findDefaultedConfigKeys(const RuntimeConfig& runtimeConfig) {
    std::vector<std::string> defaulted;
    for (const auto& descriptor : config_io_detail::configKeyRegistry()) {
        if (descriptor.status != config_io_detail::ConfigKeyStatus::Canonical) {
            continue;
        }
        if (runtimeConfig.provenance.count(std::string(descriptor.key)) == 0) {
            defaulted.emplace_back(descriptor.key);
        }
    }
    return defaulted;
}

} // namespace abm
