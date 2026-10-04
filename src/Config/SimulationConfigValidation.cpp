// SimulationConfigValidation.cpp

#include "Config/SimulationConfigValidation.h"

#include "Utility/NumericValidation.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <sstream>
#include <stdexcept>
#include <string>

namespace abm {
namespace {

/*
 * Constraint failures name the parameter in prose and then the configuration key
 * in parentheses. The prose keeps the message readable for a supervisor or
 * examiner reading a run log; the parenthesised key is what lets the diagnostic
 * renderer resolve the line in the config file the reader has to edit.
 */
[[nodiscard]] std::string named(const std::string& prose, const std::string& configKey) {
    return prose + " (" + configKey + ")";
}

/** Formats a numeric value for a diagnostic without trailing zero noise. */
[[nodiscard]] std::string describeValue(double value) {
    std::ostringstream formatted;
    formatted << value;
    return formatted.str();
}

void validateAllocationConfig(const AllocationConfig& allocation, const std::string& ownerName,
                              const std::string& keyPrefix) {
    const std::string riskAversionName =
        named(ownerName + " risk aversion", keyPrefix + "_risk_aversion");
    const std::string minWeightName =
        named(ownerName + " minimum risky weight", keyPrefix + "_min_risky_weight");
    const std::string maxWeightName =
        named(ownerName + " maximum risky weight", keyPrefix + "_max_risky_weight");

    requireStrictlyPositive(allocation.riskAversion, riskAversionName.c_str());
    requireFinite(allocation.minRiskyWeight, minWeightName.c_str());
    requireFinite(allocation.maxRiskyWeight, maxWeightName.c_str());
    const std::string grossExposureName =
        named(ownerName + " maximum gross exposure", keyPrefix + "_max_gross_exposure");
    requireStrictlyPositive(allocation.maxGrossExposure, grossExposureName.c_str());

    if (allocation.minRiskyWeight > allocation.maxRiskyWeight) {
        throw std::invalid_argument(
            ownerName + " allocation minimum risky weight (" + keyPrefix + "_min_risky_weight) = " +
            describeValue(allocation.minRiskyWeight) + " cannot exceed maximum risky weight (" +
            keyPrefix + "_max_risky_weight) = " + describeValue(allocation.maxRiskyWeight) + '.');
    }
}

std::size_t movingAverageWarmupRequirement(std::size_t window) {
    return window == 0 ? 0 : window - 1;
}

std::size_t requiredChartistWarmupSteps(const ChartistConfig& chartist) {
    std::size_t requiredWarmup = chartist.volatilityWindow;

    switch (chartist.strategyMode) {
    case ChartistStrategyMode::Momentum:
    case ChartistStrategyMode::MeanReversion:
        requiredWarmup =
            std::max(requiredWarmup, movingAverageWarmupRequirement(chartist.longWindow));
        break;
    case ChartistStrategyMode::RelativeStrengthIndex:
        requiredWarmup = std::max(requiredWarmup, kRelativeStrengthIndexPeriod);
        break;
    case ChartistStrategyMode::Breakout:
        requiredWarmup = std::max(requiredWarmup, chartist.breakoutWindow);
        break;
    case ChartistStrategyMode::Random:
        requiredWarmup =
            std::max({requiredWarmup, movingAverageWarmupRequirement(chartist.longWindow),
                      kRelativeStrengthIndexPeriod});
        break;
    }

    return requiredWarmup;
}

/**
 * Warm-up observations the protagonist's own indicators need before step one.
 *
 * His lookback windows are configured independently of the population's, so a
 * warm-up long enough for the crowd can still be too short for him. Returning
 * zero for the two rules that read no price history keeps the requirement
 * honest rather than conservative.
 */
std::size_t requiredProtagonistWarmupSteps(const ProtagonistConfig& protagonist) {
    switch (protagonist.strategy) {
    case ProtagonistStrategyKind::Fundamentalist:
        return protagonist.volatilityWindow;
    case ProtagonistStrategyKind::Chartist:
        switch (protagonist.chartistRule) {
        case ChartistStrategyMode::MeanReversion:
        case ChartistStrategyMode::Momentum:
            return std::max(protagonist.volatilityWindow,
                            movingAverageWarmupRequirement(protagonist.longWindow));
        case ChartistStrategyMode::RelativeStrengthIndex:
            return std::max(protagonist.volatilityWindow, kRelativeStrengthIndexPeriod);
        case ChartistStrategyMode::Breakout:
            return std::max(protagonist.volatilityWindow, protagonist.breakoutWindow);
        case ChartistStrategyMode::Random:
            break;
        }
        // Unreachable: validation rejects a sampled rule for an identified individual.
        return protagonist.volatilityWindow;
    case ProtagonistStrategyKind::NoiseTrader:
    case ProtagonistStrategyKind::BuyAndHold:
        return 0;
    }

    return 0;
}

void requireWarmupAtLeast(std::size_t configuredWarmup, std::size_t requiredWarmup,
                          const std::string& reason) {
    if (configuredWarmup < requiredWarmup) {
        throw std::invalid_argument(
            "Warm-up steps (warmup_steps) must be at least " + std::to_string(requiredWarmup) +
            " for " + reason + ". Configured warm-up steps: " + std::to_string(configuredWarmup) +
            ".");
    }
}

void validatePopulationConfig(const SimulationConfig& config) {
    requirePositiveSize(config.timeSteps, named("Simulation time steps", "time_steps").c_str());
    /*
     * The protagonist counts towards the requirement. A market of one named
     * trader is degenerate but well defined, and refusing to construct it would
     * make the isolated single-agent diagnostic impossible to run.
     */
    if (config.numFundamentalists + config.numChartists + config.numNoiseTraders +
                config.numBuyAndHoldAgents ==
            0 &&
        !config.protagonist.enabled) {
        throw std::invalid_argument(
            "At least one agent is required: num_fundamentalists, num_chartists, "
            "num_noise_traders and num_buy_and_hold_agents are all zero, and no protagonist is "
            "enabled.");
    }
}

/*
 * Market state that is not per-asset. The price level, inventory, tick grid,
 * and fundamental-process parameters are validated once per asset in
 * validateAssetDefinitions, which covers the legacy single-asset spelling too
 * because an undeclared universe still holds one asset.
 */
void validateMarketStateConfig(const SimulationConfig& config) {
    requireNonNegative(config.initialCash, named("Initial cash", "initial_cash").c_str());
    requireFinite(config.riskFreeRate, named("Risk-free rate", "risk_free_rate").c_str());
    requireFinite(config.agentActivityRate,
                  named("Agent activity rate", "agent_activity_rate").c_str());
    requireNonNegative(config.warmupPriceProcess.noiseStdDev,
                       named("Warm-up price noise stddev", "warmup_price_noise_std_dev").c_str());
    requireNonNegative(
        config.warmupPriceProcess.fundamentalPullStrength,
        named("Warm-up fundamental pull strength", "warmup_fundamental_pull_strength").c_str());

    if (config.riskFreeRate <= -1.0) {
        throw std::invalid_argument(
            "Risk-free rate (risk_free_rate) = " + describeValue(config.riskFreeRate) +
            " must be greater than -1.0.");
    }
    if (config.covarianceWindow < 2) {
        throw std::invalid_argument(
            "Covariance window (covariance_window) = " + std::to_string(config.covarianceWindow) +
            " must be at least 2.");
    }
}

void validateMicrostructureConfig(const MicrostructureConfig& microstructure) {
    requirePositiveSize(microstructure.orderExpirySteps,
                        named("Order expiry steps", "order_expiry_steps").c_str());
    requireInClosedUnitInterval(
        microstructure.cancellationBaseProbability,
        named("Cancellation base probability", "cancellation_base_probability").c_str());
    requireNonNegative(
        microstructure.cancellationMispricingSensitivity,
        named("Cancellation mispricing sensitivity", "cancellation_mispricing_sensitivity")
            .c_str());
    requireInClosedUnitInterval(
        microstructure.marketOrderProbability,
        named("Market order probability", "market_order_probability").c_str());
    requireNonNegative(
        microstructure.marketOrderLogGapThreshold,
        named("Market order log-gap threshold", "market_order_log_gap_threshold").c_str());
    requireNonNegative(microstructure.marketOrderPriceCollar,
                       named("Market order price collar", "market_order_price_collar").c_str());
    requirePositiveSize(microstructure.bookDepthLevels,
                        named("Book depth levels", "book_depth_levels").c_str());
}

void validateShortSaleConfig(const ShortSaleConfig& shortSale) {
    requireStrictlyPositive(
        shortSale.initialMarginRequirement,
        named("Short-sale initial margin requirement", "short_sale_initial_margin_requirement")
            .c_str());
    requireStrictlyPositive(shortSale.maintenanceMarginRequirement,
                            named("Short-sale maintenance margin requirement",
                                  "short_sale_maintenance_margin_requirement")
                                .c_str());
    requireInClosedUnitInterval(
        shortSale.borrowableSupplyRatio,
        named("Short-sale borrowable supply ratio", "short_sale_borrowable_supply_ratio").c_str());
    if (shortSale.maintenanceMarginRequirement > shortSale.initialMarginRequirement) {
        throw std::invalid_argument(
            "Short-sale maintenance margin (short_sale_maintenance_margin_requirement) = " +
            describeValue(shortSale.maintenanceMarginRequirement) +
            " cannot exceed initial margin (short_sale_initial_margin_requirement) = " +
            describeValue(shortSale.initialMarginRequirement) + '.');
    }
}

void validateTransactionCostConfig(const TransactionCostConfig& transactionCosts) {
    requireNonNegative(transactionCosts.rate,
                       named("Transaction cost rate", "transaction_cost_rate").c_str());
    if (transactionCosts.rate >= 1.0) {
        throw std::invalid_argument("Transaction cost rate (transaction_cost_rate) = " +
                                    describeValue(transactionCosts.rate) + " must be less than 1.");
    }
}

void validateControlFiniteValues(const ControlParameters& control) {
    requireInClosedUnitInterval(
        control.prospectTheoryAgentFraction,
        named("Control Prospect Theory agent fraction", "control_prospect_theory_agent_fraction")
            .c_str());
    requireFinite(control.lossAversion,
                  named("Control loss aversion", "control_loss_aversion").c_str());
    requireFinite(control.lossAversionStdDev,
                  named("Control loss aversion stddev", "control_loss_aversion_std_dev").c_str());
    requireFinite(control.curvatureForGain,
                  named("Control curvature for gain", "control_curvature_for_gain").c_str());
    requireFinite(
        control.curvatureForGainStdDev,
        named("Control curvature for gain stddev", "control_curvature_for_gain_std_dev").c_str());
    requireFinite(control.curvatureForLoss,
                  named("Control curvature for loss", "control_curvature_for_loss").c_str());
    requireFinite(
        control.curvatureForLossStdDev,
        named("Control curvature for loss stddev", "control_curvature_for_loss_std_dev").c_str());
    requireFinite(control.probDistortionForGain, named("Control probability distortion for gain",
                                                       "control_prob_distortion_for_gain")
                                                     .c_str());
    requireFinite(control.probDistortionForLoss, named("Control probability distortion for loss",
                                                       "control_prob_distortion_for_loss")
                                                     .c_str());
    requireFinite(
        control.probabilityDistortionMin,
        named("Control probability distortion min", "control_probability_distortion_min").c_str());
    requireFinite(
        control.probabilityDistortionMax,
        named("Control probability distortion max", "control_probability_distortion_max").c_str());
    requireFinite(control.referencePoint,
                  named("Control reference point", "control_reference_point").c_str());
}

void validateEnabledProspectTheoryConfig(const ControlParameters& control) {
    if (!control.prospectTheoryEnabled) {
        return;
    }

    requireStrictlyPositive(control.lossAversion,
                            named("Control loss aversion", "control_loss_aversion").c_str());
    requireNonNegative(
        control.lossAversionStdDev,
        named("Control loss aversion stddev", "control_loss_aversion_std_dev").c_str());
    requireStrictlyPositive(
        control.curvatureForGain,
        named("Control curvature for gain", "control_curvature_for_gain").c_str());
    requireNonNegative(
        control.curvatureForGainStdDev,
        named("Control curvature for gain stddev", "control_curvature_for_gain_std_dev").c_str());
    requireStrictlyPositive(
        control.curvatureForLoss,
        named("Control curvature for loss", "control_curvature_for_loss").c_str());
    requireNonNegative(
        control.curvatureForLossStdDev,
        named("Control curvature for loss stddev", "control_curvature_for_loss_std_dev").c_str());
    requireStrictlyPositive(
        control.probDistortionForGain,
        named("Control probability distortion for gain", "control_prob_distortion_for_gain")
            .c_str());
    requireStrictlyPositive(
        control.probDistortionForLoss,
        named("Control probability distortion for loss", "control_prob_distortion_for_loss")
            .c_str());
    requireStrictlyPositive(
        control.probabilityDistortionMin,
        named("Control probability distortion min", "control_probability_distortion_min").c_str());
    requireStrictlyPositive(
        control.probabilityDistortionMax,
        named("Control probability distortion max", "control_probability_distortion_max").c_str());
    requireStrictlyPositive(control.referencePoint,
                            named("Control reference point", "control_reference_point").c_str());
    if (control.referencePointMode == ProspectReferencePointMode::MovingAveragePrice) {
        requirePositiveSize(control.referenceMovingAverageWindow,
                            named("Control reference moving-average window",
                                  "control_reference_moving_average_window")
                                .c_str());
    }
    if (control.prospectScenarioCount < 3 || control.prospectScenarioCount % 2 == 0) {
        throw std::invalid_argument(
            "Control prospect scenario count (control_prospect_scenario_count) = " +
            std::to_string(control.prospectScenarioCount) +
            " must be an odd integer greater than or equal to 3.");
    }
    if (control.probabilityDistortionMin > control.probabilityDistortionMax) {
        throw std::invalid_argument(
            "Control probability distortion bounds must satisfy min <= max, but "
            "(control_probability_distortion_min) = " +
            describeValue(control.probabilityDistortionMin) +
            " exceeds (control_probability_distortion_max) = " +
            describeValue(control.probabilityDistortionMax) + '.');
    }
}

void validateFundamentalistConfig(const FundamentalistConfig& fundamentalist) {
    requireInHalfOpenUnitInterval(
        fundamentalist.mispricingThreshold,
        named("Fundamentalist mispricing threshold", "fundamentalist_mispricing_threshold")
            .c_str());
    requireInHalfOpenUnitInterval(
        fundamentalist.stopLossThreshold,
        named("Fundamentalist stop-loss threshold", "fundamentalist_stop_loss_threshold").c_str());
    requireInHalfOpenUnitInterval(
        fundamentalist.takeProfitThreshold,
        named("Fundamentalist take-profit threshold", "fundamentalist_take_profit_threshold")
            .c_str());
    requirePositiveSize(
        fundamentalist.volatilityWindow,
        named("Fundamentalist volatility window", "fundamentalist_volatility_window").c_str());
    requireAtLeast(
        fundamentalist.forecastHorizon, 1.0,
        named("Fundamentalist forecast horizon", "fundamentalist_forecast_horizon").c_str());
    validateAllocationConfig(fundamentalist.allocation, "Fundamentalist", "fundamentalist");
}

void validateChartistConfig(const ChartistConfig& chartist) {
    requirePositiveSize(chartist.shortWindow,
                        named("Chartist short window", "chartist_short_window").c_str());
    requirePositiveSize(chartist.longWindow,
                        named("Chartist long window", "chartist_long_window").c_str());
    requireInHalfOpenUnitInterval(
        chartist.momentumSignalThreshold,
        named("Chartist momentum signal threshold", "chartist_momentum_signal_threshold").c_str());
    requirePositiveSize(chartist.breakoutWindow,
                        named("Chartist breakout window", "chartist_breakout_window").c_str());
    requirePositiveSize(chartist.volatilityWindow,
                        named("Chartist volatility window", "chartist_volatility_window").c_str());
    requireAtLeast(chartist.forecastHorizon, 1.0,
                   named("Chartist forecast horizon", "chartist_forecast_horizon").c_str());
    if (chartist.shortWindow > chartist.longWindow) {
        throw std::invalid_argument("Chartist short window (chartist_short_window) = " +
                                    std::to_string(chartist.shortWindow) +
                                    " cannot exceed long window (chartist_long_window) = " +
                                    std::to_string(chartist.longWindow) + '.');
    }
    requireInClosedUnitInterval(
        chartist.maxShortWeight,
        named("Chartist max short weight", "chartist_max_short_weight").c_str());
    validateAllocationConfig(chartist.allocation, "Chartist", "chartist");
}

void validateNoiseTraderConfig(const NoiseTraderConfig& noiseTrader) {
    requireStrictlyPositive(
        noiseTrader.beliefShockStdDev,
        named("Noise-trader belief shock stddev", "noise_trader_belief_shock_std_dev").c_str());
    requireInClosedUnitInterval(
        noiseTrader.orderSizeFraction,
        named("Noise-trader order size fraction", "noise_trader_order_size_fraction").c_str());
    if (noiseTrader.orderSizeFraction <= 0.0) {
        throw std::invalid_argument(
            "Noise-trader order size fraction (noise_trader_order_size_fraction) = " +
            describeValue(noiseTrader.orderSizeFraction) + " must be greater than 0.");
    }
    requireInClosedUnitInterval(
        noiseTrader.maxShortWeight,
        named("Noise-trader max short weight", "noise_trader_max_short_weight").c_str());
}

void validateBuyAndHoldConfig(const BuyAndHoldConfig& buyAndHold) {
    requireInClosedUnitInterval(
        buyAndHold.targetRiskyWeight,
        named("Buy-and-hold target risky weight", "buy_hold_target_risky_weight").c_str());
    if (buyAndHold.targetRiskyWeight <= 0.0) {
        throw std::invalid_argument(
            "Buy-and-hold target risky weight (buy_hold_target_risky_weight) = " +
            describeValue(buyAndHold.targetRiskyWeight) + " must be greater than 0.");
    }
}

/**
 * Validates the individually specified participant.
 *
 * Every rule parameter is checked, not only the block belonging to the selected
 * strategy. A protagonist described as a chartist may well carry stop-loss and
 * mispricing settings from an earlier experiment, and a nonsense value there
 * should fail the run rather than lie dormant until the strategy is switched.
 *
 * The whole group is skipped when the protagonist is disabled, so a
 * configuration that never intends to use him is not obliged to keep his
 * parameters meaningful.
 */
void validateProtagonistConfig(const ProtagonistConfig& protagonist) {
    if (!protagonist.enabled) {
        return;
    }

    requireNonNegative(protagonist.initialCash,
                       named("Protagonist initial cash", "protagonist_initial_cash").c_str());
    requireNonNegative(protagonist.initialStock,
                       named("Protagonist initial stock", "protagonist_initial_stock").c_str());
    validateAllocationConfig(protagonist.allocation, "Protagonist", "protagonist");

    requireInHalfOpenUnitInterval(
        protagonist.mispricingThreshold,
        named("Protagonist mispricing threshold", "protagonist_mispricing_threshold").c_str());
    requireInHalfOpenUnitInterval(
        protagonist.stopLossThreshold,
        named("Protagonist stop-loss threshold", "protagonist_stop_loss_threshold").c_str());
    requireInHalfOpenUnitInterval(
        protagonist.takeProfitThreshold,
        named("Protagonist take-profit threshold", "protagonist_take_profit_threshold").c_str());
    requirePositiveSize(
        protagonist.volatilityWindow,
        named("Protagonist volatility window", "protagonist_volatility_window").c_str());
    requireAtLeast(protagonist.forecastHorizon, 1.0,
                   named("Protagonist forecast horizon", "protagonist_forecast_horizon").c_str());

    requirePositiveSize(protagonist.shortWindow,
                        named("Protagonist short window", "protagonist_short_window").c_str());
    requirePositiveSize(protagonist.longWindow,
                        named("Protagonist long window", "protagonist_long_window").c_str());
    if (protagonist.shortWindow > protagonist.longWindow) {
        throw std::invalid_argument("Protagonist short window (protagonist_short_window) = " +
                                    std::to_string(protagonist.shortWindow) +
                                    " cannot exceed long window (protagonist_long_window) = " +
                                    std::to_string(protagonist.longWindow) + '.');
    }
    requireInHalfOpenUnitInterval(
        protagonist.momentumSignalThreshold,
        named("Protagonist momentum signal threshold", "protagonist_momentum_signal_threshold")
            .c_str());
    requirePositiveSize(
        protagonist.breakoutWindow,
        named("Protagonist breakout window", "protagonist_breakout_window").c_str());
    requireInClosedUnitInterval(
        protagonist.maxShortWeight,
        named("Protagonist max short weight", "protagonist_max_short_weight").c_str());

    requireStrictlyPositive(
        protagonist.noiseBeliefShockStdDev,
        named("Protagonist noise belief shock stddev", "protagonist_noise_belief_shock_std_dev")
            .c_str());
    requireInClosedUnitInterval(
        protagonist.noiseOrderSizeFraction,
        named("Protagonist noise order size fraction", "protagonist_noise_order_size_fraction")
            .c_str());
    if (protagonist.noiseOrderSizeFraction <= 0.0) {
        throw std::invalid_argument(
            "Protagonist noise order size fraction (protagonist_noise_order_size_fraction) = " +
            describeValue(protagonist.noiseOrderSizeFraction) + " must be greater than 0.");
    }

    requireInClosedUnitInterval(protagonist.buyHoldTargetRiskyWeight,
                                named("Protagonist buy-and-hold target risky weight",
                                      "protagonist_buy_hold_target_risky_weight")
                                    .c_str());
    if (protagonist.buyHoldTargetRiskyWeight <= 0.0) {
        throw std::invalid_argument("Protagonist buy-and-hold target risky weight "
                                    "(protagonist_buy_hold_target_risky_weight) = " +
                                    describeValue(protagonist.buyHoldTargetRiskyWeight) +
                                    " must be greater than 0.");
    }

    if (!protagonist.prospectTheoryEnabled) {
        return;
    }
    requireStrictlyPositive(
        protagonist.lossAversion,
        named("Protagonist loss aversion", "protagonist_loss_aversion").c_str());
    requireStrictlyPositive(
        protagonist.curvatureForGain,
        named("Protagonist curvature for gain", "protagonist_curvature_for_gain").c_str());
    requireStrictlyPositive(
        protagonist.curvatureForLoss,
        named("Protagonist curvature for loss", "protagonist_curvature_for_loss").c_str());
    requireStrictlyPositive(
        protagonist.probDistortionForGain,
        named("Protagonist probability distortion for gain", "protagonist_prob_distortion_for_gain")
            .c_str());
    requireStrictlyPositive(
        protagonist.probDistortionForLoss,
        named("Protagonist probability distortion for loss", "protagonist_prob_distortion_for_loss")
            .c_str());
}

void validateSocialConfig(const SocialInfluenceConfig& social) {
    requireStrictlyPositive(social.spaceWidth,
                            named("Social space width", "social_space_width").c_str());
    requireStrictlyPositive(social.spaceHeight,
                            named("Social space height", "social_space_height").c_str());
    requireNonNegative(social.interactionRadius,
                       named("Social interaction radius", "social_interaction_radius").c_str());
    requireNonNegative(social.opinionKappa,
                       named("Social opinion kappa", "social_opinion_kappa").c_str());
    requireNonNegative(social.holdTolerance,
                       named("Social hold tolerance", "social_hold_tolerance").c_str());
    requireInClosedUnitInterval(social.gammaMin,
                                named("Social gamma min", "social_gamma_min").c_str());
    requireInClosedUnitInterval(social.gammaMax,
                                named("Social gamma max", "social_gamma_max").c_str());
    requireNonNegative(
        social.privateSignalStdMin,
        named("Social private signal stddev min", "social_private_signal_std_min").c_str());
    requireNonNegative(
        social.privateSignalStdMax,
        named("Social private signal stddev max", "social_private_signal_std_max").c_str());

    if (social.gammaMin > social.gammaMax) {
        throw std::invalid_argument(
            "Social gamma bounds must satisfy 0 <= min <= max <= 1, but "
            "(social_gamma_min) = " +
            describeValue(social.gammaMin) +
            " exceeds (social_gamma_max) = " + describeValue(social.gammaMax) + '.');
    }
    if (social.privateSignalStdMax < social.privateSignalStdMin) {
        throw std::invalid_argument(
            "Private signal stddev bounds must satisfy 0 <= min <= max, but "
            "(social_private_signal_std_min) = " +
            describeValue(social.privateSignalStdMin) +
            " exceeds (social_private_signal_std_max) = " +
            describeValue(social.privateSignalStdMax) + '.');
    }
}

void validateAssetDefinitions(const SimulationConfig& config) {
    if (config.assets.declared() && !config.legacyAssetScalarKeySeen.empty()) {
        throw std::invalid_argument(
            "Config mixes the multi-asset 'assets' declaration with legacy single-asset key '" +
            config.legacyAssetScalarKeySeen +
            "'. Use asset.<name>.* keys for every asset instead.");
    }

    for (std::size_t assetIndex = 0; assetIndex < config.assets.size(); ++assetIndex) {
        const AssetDefinition& asset = config.assets[assetIndex];
        if (asset.name.empty() || asset.name.find_first_of(", \t.") != std::string::npos) {
            throw std::invalid_argument(
                "Asset name '" + asset.name +
                "' is invalid: names must be non-empty and must not contain commas, dots, or "
                "whitespace.");
        }
        for (std::size_t otherIndex = assetIndex + 1; otherIndex < config.assets.size();
             ++otherIndex) {
            if (config.assets[otherIndex].name == asset.name) {
                throw std::invalid_argument("Duplicate asset name '" + asset.name + "'.");
            }
        }

        const std::string prefix = "Asset '" + asset.name + "' ";
        const std::string keyPrefix = "asset." + asset.name + '.';
        requireStrictlyPositive(
            asset.initialPrice,
            named(prefix + "initial price", keyPrefix + "initial_price").c_str());
        requireNonNegative(asset.initialStock,
                           named(prefix + "initial stock", keyPrefix + "initial_stock").c_str());
        requireNonNegative(
            asset.priceTickSize,
            named(prefix + "price tick size", keyPrefix + "price_tick_size").c_str());
        requireNonNegative(
            asset.fundamentalShockStdDev,
            named(prefix + "fundamental shock stddev", keyPrefix + "fundamental_shock_std_dev")
                .c_str());
        requireFinite(asset.fundamentalDriftPerStep, named(prefix + "fundamental drift per step",
                                                           keyPrefix + "fundamental_drift_per_step")
                                                         .c_str());
        requireStrictlyPositive(
            asset.minimumFundamentalValue,
            named(prefix + "minimum fundamental value", keyPrefix + "minimum_fundamental_value")
                .c_str());

        /*
         * Under GBM the drift and shock are per-step log returns, not price
         * increments. Copying an arithmetic-walk shock such as 0.03 (three
         * price units) into a GBM asset silently produces a 3% per-step
         * volatility, whereas copying a price-unit shock of 3.0 would produce
         * a 300% per-step volatility and an economically meaningless path.
         * Rejecting the latter turns the most likely units mistake into a
         * clear configuration error instead of a plausible-looking run.
         */
        if (asset.fundamentalProcess == FundamentalProcessType::GeometricBrownianMotion &&
            asset.fundamentalShockStdDev > kMaximumGeometricProcessLogStdDev) {
            throw std::invalid_argument(
                prefix + "uses fundamental_process = gbm, where (" + keyPrefix +
                "fundamental_shock_std_dev) is a per-step log-return standard deviation rather "
                "than a price increment. The configured value " +
                describeValue(asset.fundamentalShockStdDev) + " exceeds " +
                std::to_string(kMaximumGeometricProcessLogStdDev) +
                ", which implies an implausible per-step volatility; check the units.");
        }
    }

    if (!config.primaryAssetName.empty()) {
        bool found = false;
        for (const AssetDefinition& asset : config.assets) {
            if (asset.name == config.primaryAssetName) {
                if (!asset.enabled) {
                    throw std::invalid_argument(
                        "Primary asset '" + config.primaryAssetName +
                        "' is disabled. Enable it or nominate a different (primary_asset).");
                }
                found = true;
                break;
            }
        }
        if (!found) {
            throw std::invalid_argument("Primary asset '" + config.primaryAssetName +
                                        "' is not among the configured assets (primary_asset).");
        }
    }

    const bool anyEnabled = std::any_of(config.assets.begin(), config.assets.end(),
                                        [](const AssetDefinition& asset) { return asset.enabled; });
    if (!anyEnabled) {
        throw std::invalid_argument(
            "Every declared asset is disabled; the market needs at least one tradable asset.");
    }
}

/**
 * Validates the cross-asset fundamental correlation.
 *
 * The equicorrelation matrix over n assets is positive semi-definite exactly on
 * rho in [-1/(n-1), 1]; outside that range no joint distribution exists. The
 * enabled-asset count is not known until normalisation, so only the universal
 * [-1, 1] bound is enforced here and the tighter bound is checked when the
 * innovations are drawn.
 */
void validateAssetCorrelation(const SimulationConfig& config) {
    requireFinite(config.assetFundamentalCorrelation,
                  named("Asset fundamental correlation", "asset_fundamental_correlation").c_str());
    if (config.assetFundamentalCorrelation < -1.0 || config.assetFundamentalCorrelation > 1.0) {
        throw std::invalid_argument("Asset fundamental correlation (asset_fundamental_correlation) "
                                    "= " +
                                    describeValue(config.assetFundamentalCorrelation) +
                                    " must lie in [-1, 1].");
    }
}

void validateWarmupRequirements(const SimulationConfig& config) {
    if (config.numFundamentalists > 0) {
        requireWarmupAtLeast(config.warmupSteps, config.fundamentalist.volatilityWindow,
                             "active fundamentalist volatility estimation");
    }
    if (config.numChartists > 0) {
        requireWarmupAtLeast(config.warmupSteps, requiredChartistWarmupSteps(config.chartist),
                             "active chartist lookback indicators");
    }
    if (config.protagonist.enabled) {
        requireWarmupAtLeast(config.warmupSteps, requiredProtagonistWarmupSteps(config.protagonist),
                             "the protagonist's lookback indicators");
    }
}

/*
 * The validation groups, in the order they are reported.
 *
 * Running each group independently is what lets one pass surface several
 * unrelated configuration mistakes. Within a group the first failure still
 * stops that group, because later checks there often depend on the earlier ones
 * holding.
 */
using ValidationGroup = void (*)(const SimulationConfig&);

void runPopulationGroup(const SimulationConfig& config) {
    validatePopulationConfig(config);
}
void runControlFiniteGroup(const SimulationConfig& config) {
    validateControlFiniteValues(config.control);
}
void runMarketStateGroup(const SimulationConfig& config) {
    validateMarketStateConfig(config);
}
void runAssetDefinitionGroup(const SimulationConfig& config) {
    validateAssetDefinitions(config);
}
void runAssetCorrelationGroup(const SimulationConfig& config) {
    validateAssetCorrelation(config);
}
void runMicrostructureGroup(const SimulationConfig& config) {
    validateMicrostructureConfig(config.microstructure);
}
void runShortSaleGroup(const SimulationConfig& config) {
    validateShortSaleConfig(config.shortSale);
}
void runTransactionCostGroup(const SimulationConfig& config) {
    validateTransactionCostConfig(config.transactionCosts);
}
void runFundamentalistGroup(const SimulationConfig& config) {
    validateFundamentalistConfig(config.fundamentalist);
}
void runChartistGroup(const SimulationConfig& config) {
    validateChartistConfig(config.chartist);
}
void runNoiseTraderGroup(const SimulationConfig& config) {
    validateNoiseTraderConfig(config.noiseTrader);
}
void runBuyAndHoldGroup(const SimulationConfig& config) {
    validateBuyAndHoldConfig(config.buyAndHold);
}
void runProtagonistGroup(const SimulationConfig& config) {
    validateProtagonistConfig(config.protagonist);
}
void runSocialGroup(const SimulationConfig& config) {
    validateSocialConfig(config.social);
}
void runProspectTheoryGroup(const SimulationConfig& config) {
    validateEnabledProspectTheoryConfig(config.control);
}
void runWarmupGroup(const SimulationConfig& config) {
    validateWarmupRequirements(config);
}

[[nodiscard]] const std::vector<ValidationGroup>& validationGroups() {
    static const std::vector<ValidationGroup> groups{
        runPopulationGroup,      runControlFiniteGroup,    runMarketStateGroup,
        runAssetDefinitionGroup, runAssetCorrelationGroup, runMicrostructureGroup,
        runShortSaleGroup,       runTransactionCostGroup,  runFundamentalistGroup,
        runChartistGroup,        runNoiseTraderGroup,      runBuyAndHoldGroup,
        runProtagonistGroup,     runSocialGroup,           runProspectTheoryGroup,
        runWarmupGroup,
    };
    return groups;
}

} // namespace

void validateSimulationConfig(const SimulationConfig& config) {
    for (const ValidationGroup group : validationGroups()) {
        group(config);
    }
}

void collectSimulationConfigDiagnostics(const SimulationConfig& config,
                                        const ConfigProvenance& provenance,
                                        std::vector<ConfigDiagnostic>& diagnostics) {
    for (const ValidationGroup group : validationGroups()) {
        try {
            group(config);
        } catch (const std::exception& error) {
            std::string message = error.what();
            ConfigSourceLocation location = locateMessageKey(message, provenance);
            diagnostics.push_back(ConfigDiagnostic{ConfigDiagnosticSeverity::Error,
                                                   std::move(message), std::move(location)});
        }
    }
}

void normaliseSimulationConfig(SimulationConfig& config) {
    /*
     * One asset pipeline for both configuration spellings: the universe is
     * non-empty whether or not an `assets = ...` declaration was parsed, so
     * there is no legacy branch to synthesise a one-element vector, and no
     * mirror block copying the primary asset back into scalar duplicates. The
     * single-asset projections on SimulationConfig read the primary asset
     * directly.
     */
    config.assets.normalise(config.primaryAssetName);
    config.primaryAssetName = config.primaryAsset().name;

    if (!config.shortSellingEnabled) {
        config.chartist.maxShortWeight = 0.0;
        config.noiseTrader.maxShortWeight = 0.0;
        config.protagonist.maxShortWeight = 0.0;
    }

    config.agentActivityRate = std::clamp(config.agentActivityRate, 0.0, 1.0);
}

} // namespace abm
