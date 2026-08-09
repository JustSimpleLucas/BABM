// SimulationConfigValidation.cpp

#include "ControlParameters/SimulationConfigValidation.h"

#include "Utility/NumericValidation.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <stdexcept>
#include <string>

namespace abm {
namespace {

void validateAllocationConfig(const AllocationConfig& allocation, const std::string& ownerName) {
    const std::string riskAversionName = ownerName + " risk aversion";
    const std::string minWeightName = ownerName + " minimum risky weight";
    const std::string maxWeightName = ownerName + " maximum risky weight";

    requireStrictlyPositive(allocation.riskAversion, riskAversionName.c_str());
    requireFinite(allocation.minRiskyWeight, minWeightName.c_str());
    requireFinite(allocation.maxRiskyWeight, maxWeightName.c_str());
    const std::string grossExposureName = ownerName + " maximum gross exposure";
    requireStrictlyPositive(allocation.maxGrossExposure, grossExposureName.c_str());

    if (allocation.minRiskyWeight > allocation.maxRiskyWeight) {
        throw std::invalid_argument(
            ownerName + " allocation minimum risky weight cannot exceed maximum risky weight.");
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

void requireWarmupAtLeast(std::size_t configuredWarmup, std::size_t requiredWarmup,
                          const std::string& reason) {
    if (configuredWarmup < requiredWarmup) {
        throw std::invalid_argument(
            "Warm-up steps must be at least " + std::to_string(requiredWarmup) + " for " + reason +
            ". Configured warm-up steps: " + std::to_string(configuredWarmup) + ".");
    }
}

void validatePopulationConfig(const SimulationConfig& config) {
    requirePositiveSize(config.timeSteps, "Simulation time steps");
    if (config.numFundamentalists + config.numChartists + config.numNoiseTraders +
            config.numBuyAndHoldAgents ==
        0) {
        throw std::invalid_argument("At least one agent is required.");
    }
}

/*
 * Market state that is not per-asset. The price level, inventory, tick grid,
 * and fundamental-process parameters are validated once per asset in
 * validateAssetDefinitions, which covers the legacy single-asset spelling too
 * because an undeclared universe still holds one asset.
 */
void validateMarketStateConfig(const SimulationConfig& config) {
    requireNonNegative(config.initialCash, "Initial cash");
    requireFinite(config.riskFreeRate, "Risk-free rate");
    requireFinite(config.agentActivityRate, "Agent activity rate");
    requireNonNegative(config.warmupPriceProcess.noiseStdDev, "Warm-up price noise stddev");
    requireNonNegative(config.warmupPriceProcess.fundamentalPullStrength,
                       "Warm-up fundamental pull strength");

    if (config.riskFreeRate <= -1.0) {
        throw std::invalid_argument("Risk-free rate must be greater than -1.0.");
    }
    if (config.covarianceWindow < 2) {
        throw std::invalid_argument("Covariance window must be at least 2.");
    }
}

void validateMicrostructureConfig(const MicrostructureConfig& microstructure) {
    requirePositiveSize(microstructure.orderExpirySteps, "Order expiry steps");
    requireInClosedUnitInterval(microstructure.cancellationBaseProbability,
                                "Cancellation base probability");
    requireNonNegative(microstructure.cancellationMispricingSensitivity,
                       "Cancellation mispricing sensitivity");
    requireInClosedUnitInterval(microstructure.marketOrderProbability, "Market order probability");
    requireNonNegative(microstructure.marketOrderLogGapThreshold, "Market order log-gap threshold");
    requireNonNegative(microstructure.marketOrderPriceCollar, "Market order price collar");
    requirePositiveSize(microstructure.bookDepthLevels, "Book depth levels");
}

void validateShortSaleConfig(const ShortSaleConfig& shortSale) {
    requireStrictlyPositive(shortSale.initialMarginRequirement,
                            "Short-sale initial margin requirement");
    requireStrictlyPositive(shortSale.maintenanceMarginRequirement,
                            "Short-sale maintenance margin requirement");
    requireInClosedUnitInterval(shortSale.borrowableSupplyRatio,
                                "Short-sale borrowable supply ratio");
    if (shortSale.maintenanceMarginRequirement > shortSale.initialMarginRequirement) {
        throw std::invalid_argument("Short-sale maintenance margin cannot exceed initial margin.");
    }
}

void validateTransactionCostConfig(const TransactionCostConfig& transactionCosts) {
    requireNonNegative(transactionCosts.rate, "Transaction cost rate");
    if (transactionCosts.rate >= 1.0) {
        throw std::invalid_argument("Transaction cost rate must be less than 1.");
    }
}

void validateControlFiniteValues(const ControlParameters& control) {
    requireInClosedUnitInterval(control.prospectTheoryAgentFraction,
                                "Control Prospect Theory agent fraction");
    requireFinite(control.lossAversion, "Control loss aversion");
    requireFinite(control.lossAversionStdDev, "Control loss aversion stddev");
    requireFinite(control.curvatureForGain, "Control curvature for gain");
    requireFinite(control.curvatureForGainStdDev, "Control curvature for gain stddev");
    requireFinite(control.curvatureForLoss, "Control curvature for loss");
    requireFinite(control.curvatureForLossStdDev, "Control curvature for loss stddev");
    requireFinite(control.probDistortionForGain, "Control probability distortion for gain");
    requireFinite(control.probDistortionForLoss, "Control probability distortion for loss");
    requireFinite(control.probabilityDistortionMin, "Control probability distortion min");
    requireFinite(control.probabilityDistortionMax, "Control probability distortion max");
    requireFinite(control.referencePoint, "Control reference point");
}

void validateEnabledProspectTheoryConfig(const ControlParameters& control) {
    if (!control.prospectTheoryEnabled) {
        return;
    }

    requireStrictlyPositive(control.lossAversion, "Control loss aversion");
    requireNonNegative(control.lossAversionStdDev, "Control loss aversion stddev");
    requireStrictlyPositive(control.curvatureForGain, "Control curvature for gain");
    requireNonNegative(control.curvatureForGainStdDev, "Control curvature for gain stddev");
    requireStrictlyPositive(control.curvatureForLoss, "Control curvature for loss");
    requireNonNegative(control.curvatureForLossStdDev, "Control curvature for loss stddev");
    requireStrictlyPositive(control.probDistortionForGain,
                            "Control probability distortion for gain");
    requireStrictlyPositive(control.probDistortionForLoss,
                            "Control probability distortion for loss");
    requireStrictlyPositive(control.probabilityDistortionMin, "Control probability distortion min");
    requireStrictlyPositive(control.probabilityDistortionMax, "Control probability distortion max");
    requireStrictlyPositive(control.referencePoint, "Control reference point");
    if (control.referencePointMode == ProspectReferencePointMode::MovingAveragePrice) {
        requirePositiveSize(control.referenceMovingAverageWindow,
                            "Control reference moving-average window");
    }
    if (control.prospectScenarioCount < 3 || control.prospectScenarioCount % 2 == 0) {
        throw std::invalid_argument(
            "Control prospect scenario count must be an odd integer greater than or equal to 3.");
    }
    if (control.probabilityDistortionMin > control.probabilityDistortionMax) {
        throw std::invalid_argument(
            "Control probability distortion bounds must satisfy min <= max.");
    }
}

void validateFundamentalistConfig(const FundamentalistConfig& fundamentalist) {
    requireInHalfOpenUnitInterval(fundamentalist.mispricingThreshold,
                                  "Fundamentalist mispricing threshold");
    requireInHalfOpenUnitInterval(fundamentalist.stopLossThreshold,
                                  "Fundamentalist stop-loss threshold");
    requireInHalfOpenUnitInterval(fundamentalist.takeProfitThreshold,
                                  "Fundamentalist take-profit threshold");
    requirePositiveSize(fundamentalist.volatilityWindow, "Fundamentalist volatility window");
    validateAllocationConfig(fundamentalist.allocation, "Fundamentalist");
}

void validateChartistConfig(const ChartistConfig& chartist) {
    requirePositiveSize(chartist.shortWindow, "Chartist short window");
    requirePositiveSize(chartist.longWindow, "Chartist long window");
    requireInHalfOpenUnitInterval(chartist.momentumSignalThreshold,
                                  "Chartist momentum signal threshold");
    requirePositiveSize(chartist.breakoutWindow, "Chartist breakout window");
    requirePositiveSize(chartist.volatilityWindow, "Chartist volatility window");
    if (chartist.shortWindow > chartist.longWindow) {
        throw std::invalid_argument("Chartist short window cannot exceed long window.");
    }
    requireInClosedUnitInterval(chartist.maxShortWeight, "Chartist max short weight");
    validateAllocationConfig(chartist.allocation, "Chartist");
}

void validateNoiseTraderConfig(const NoiseTraderConfig& noiseTrader) {
    requireStrictlyPositive(noiseTrader.beliefShockStdDev, "Noise-trader belief shock stddev");
    requireInClosedUnitInterval(noiseTrader.orderSizeFraction, "Noise-trader order size fraction");
    if (noiseTrader.orderSizeFraction <= 0.0) {
        throw std::invalid_argument("Noise-trader order size fraction must be greater than 0.");
    }
    requireInClosedUnitInterval(noiseTrader.maxShortWeight, "Noise-trader max short weight");
}

void validateBuyAndHoldConfig(const BuyAndHoldConfig& buyAndHold) {
    requireInClosedUnitInterval(buyAndHold.targetRiskyWeight,
                                "Buy-and-hold target risky weight");
    if (buyAndHold.targetRiskyWeight <= 0.0) {
        throw std::invalid_argument("Buy-and-hold target risky weight must be greater than 0.");
    }
}

void validateSocialConfig(const SocialInfluenceConfig& social) {
    requireStrictlyPositive(social.spaceWidth, "Social space width");
    requireStrictlyPositive(social.spaceHeight, "Social space height");
    requireNonNegative(social.interactionRadius, "Social interaction radius");
    requireNonNegative(social.opinionKappa, "Social opinion kappa");
    requireNonNegative(social.holdTolerance, "Social hold tolerance");
    requireInClosedUnitInterval(social.gammaMin, "Social gamma min");
    requireInClosedUnitInterval(social.gammaMax, "Social gamma max");
    requireNonNegative(social.privateSignalStdMin, "Social private signal stddev min");
    requireNonNegative(social.privateSignalStdMax, "Social private signal stddev max");

    if (social.gammaMin > social.gammaMax) {
        throw std::invalid_argument("Social gamma bounds must satisfy 0 <= min <= max <= 1.");
    }
    if (social.privateSignalStdMax < social.privateSignalStdMin) {
        throw std::invalid_argument("Private signal stddev bounds must satisfy 0 <= min <= max.");
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
        if (asset.name.empty() ||
            asset.name.find_first_of(", \t.") != std::string::npos) {
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
        requireStrictlyPositive(asset.initialPrice, (prefix + "initial price").c_str());
        requireNonNegative(asset.initialStock, (prefix + "initial stock").c_str());
        requireNonNegative(asset.priceTickSize, (prefix + "price tick size").c_str());
        requireNonNegative(asset.fundamentalShockStdDev,
                           (prefix + "fundamental shock stddev").c_str());
        requireFinite(asset.fundamentalDriftPerStep,
                      (prefix + "fundamental drift per step").c_str());
        requireStrictlyPositive(asset.minimumFundamentalValue,
                                (prefix + "minimum fundamental value").c_str());

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
                prefix + "uses fundamental_process = gbm, where fundamental_shock_std_dev is a "
                         "per-step log-return standard deviation rather than a price increment. "
                         "The configured value exceeds " +
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
                        "' is disabled. Enable it or nominate a different primary_asset.");
                }
                found = true;
                break;
            }
        }
        if (!found) {
            throw std::invalid_argument("Primary asset '" + config.primaryAssetName +
                                        "' is not among the configured assets.");
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
    requireFinite(config.assetFundamentalCorrelation, "Asset fundamental correlation");
    if (config.assetFundamentalCorrelation < -1.0 || config.assetFundamentalCorrelation > 1.0) {
        throw std::invalid_argument("Asset fundamental correlation must lie in [-1, 1].");
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
}

} // namespace

void validateSimulationConfig(const SimulationConfig& config) {
    validatePopulationConfig(config);
    validateControlFiniteValues(config.control);
    validateMarketStateConfig(config);
    validateAssetDefinitions(config);
    validateAssetCorrelation(config);
    validateMicrostructureConfig(config.microstructure);
    validateShortSaleConfig(config.shortSale);
    validateTransactionCostConfig(config.transactionCosts);
    validateFundamentalistConfig(config.fundamentalist);
    validateChartistConfig(config.chartist);
    validateNoiseTraderConfig(config.noiseTrader);
    validateBuyAndHoldConfig(config.buyAndHold);
    validateSocialConfig(config.social);
    validateEnabledProspectTheoryConfig(config.control);
    validateWarmupRequirements(config);
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
    }

    config.agentActivityRate = std::clamp(config.agentActivityRate, 0.0, 1.0);
}

} // namespace abm
