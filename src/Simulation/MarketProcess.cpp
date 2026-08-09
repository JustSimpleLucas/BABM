// MarketProcess.cpp

#include "Simulation/MarketProcess.h"

#include "RandomGenerator/RandomGenerator.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>

namespace abm {
namespace {

FundamentalValueProcessParameters fundamentalProcessParameters(const AssetDefinition& asset) {
    FundamentalValueProcessParameters parameters;
    parameters.processType = asset.fundamentalProcess;
    parameters.driftPerStep = asset.fundamentalDriftPerStep;
    parameters.shockStdDev = asset.fundamentalShockStdDev;
    parameters.minimumValue = asset.minimumFundamentalValue;
    return parameters;
}

/** Collects the per-asset process parameters for a joint advance, in index order. */
std::vector<FundamentalValueProcessParameters> jointFundamentalParameters(
    const AssetUniverse& assets) {
    std::vector<FundamentalValueProcessParameters> parameters;
    parameters.reserve(assets.size());
    for (const AssetDefinition& asset : assets) {
        parameters.push_back(fundamentalProcessParameters(asset));
    }
    return parameters;
}

/** Returns the asset names in index order, for the market's diagnostic labels. */
std::vector<std::string> assetNames(const AssetUniverse& assets) {
    std::vector<std::string> names;
    names.reserve(assets.size());
    for (const AssetDefinition& asset : assets) {
        names.push_back(asset.name);
    }
    return names;
}

} // namespace

MarketInitializationResult MarketProcess::initializeMarket(Market& market,
                                                           const SimulationConfig& config,
                                                           RandomEngine& random) {
    const AssetUniverse& assets = config.assets;
    const std::size_t primaryIndex = assets.primaryIndex();

    market.configureAssets(assetNames(assets));

    std::vector<double> previousFundamental(assets.size());
    std::vector<double> previousMarket(assets.size());
    for (std::size_t assetIndex = 0; assetIndex < assets.size(); ++assetIndex) {
        const AssetDefinition& asset = assets[assetIndex];
        market.storeTrueValue(assetIndex, asset.initialPrice);
        market.storeMarketValue(assetIndex, asset.initialPrice);
        previousFundamental[assetIndex] = asset.initialPrice;
        previousMarket[assetIndex] = asset.initialPrice;
    }

    const std::vector<FundamentalValueProcessParameters> warmupParameters =
        jointFundamentalParameters(assets);

    for (std::size_t i = 0; i < config.warmupSteps; ++i) {
        /*
         * Fundamentals for every asset advance together so their innovations
         * share the configured cross-asset correlation. Assets are drawn in
         * declared index order, which is the same order the previous per-asset
         * loop consumed the market engine in, so single-asset warm-up
         * histories are unchanged. The warm-up price noise below is drawn from
         * a separate engine and is therefore unaffected by this regrouping.
         */
        const std::vector<double> stepFundamentals = market.generateCorrelatedFundamentalValues(
            warmupParameters, config.assetFundamentalCorrelation);

        for (std::size_t assetIndex = 0; assetIndex < assets.size(); ++assetIndex) {
            previousFundamental[assetIndex] = stepFundamentals[assetIndex];

            /*
             * Formula note:
             * m_t = (F_t - P_t) / P_t,
             * r_t^warm = clamp(beta_warm * m_t + xi_t^warm, -0.95, 0.95),
             * P_{t+1} = max(P_min, P_t * (1 + r_t^warm)).
             *
             * Warm-up uses a simple fundamental-pull process only to initialise
             * price history before the analysed continuous-LOB phase begins.
             */
            const double mispricing = (previousFundamental[assetIndex] -
                                       previousMarket[assetIndex]) /
                                      std::max(previousMarket[assetIndex], kMinimumPrice);
            const double noise =
                random.generateNormalDist(0.0, config.warmupPriceProcess.noiseStdDev);
            const double rawReturn = std::clamp(
                (config.warmupPriceProcess.fundamentalPullStrength * mispricing) + noise, -0.95,
                0.95);
            previousMarket[assetIndex] =
                std::max(kMinimumPrice, previousMarket[assetIndex] * (1.0 + rawReturn));
            market.storeMarketValue(assetIndex, previousMarket[assetIndex]);
        }
    }

    return {previousMarket[primaryIndex], previousFundamental[primaryIndex]};
}

void MarketProcess::accrueRiskFreeCash(SimulationPopulation& population,
                                       double riskFreeRate) {
    /*
     * Formula note:
     * c_i,t+1 = c_i,t * (1 + r_f).
     */
    const double accrualFactor = 1.0 + riskFreeRate;

    for (AgentRecord& record : population.records) {
        Agent& agent = record.agent;
        agent.updateCash(agent.getCash() * accrualFactor);
    }
}

std::vector<double> MarketProcess::generateNextFundamentals(Market& market,
                                                            const SimulationConfig& config) {
    return market.generateCorrelatedFundamentalValues(jointFundamentalParameters(config.assets),
                                                      config.assetFundamentalCorrelation);
}

PriceFormationResult
MarketProcess::resolvePriceAfterClearing(double referencePrice,
                                         const MicrostructureStepResult& result) {
    PriceFormationResult priceResult{};
    priceResult.nextPrice = referencePrice;

    if (result.tradedVolume > kMinimumOrderQuantity) {
        /*
         * In the continuous LOB, the official market price is the last
         * realised transaction price. Fundamental pull, order imbalance, and
         * exogenous noise affect prices only through future orders.
         *
         * Formula note:
         * P_t = last_trade_price,
         * raw_return_t = (P_t - P_{t-1}) / P_{t-1},
         * log_return_t = log(P_t / P_{t-1}).
         */
        priceResult.nextPrice = std::max(kMinimumPrice, result.lastTradePrice);
        priceResult.rawReturn =
            (priceResult.nextPrice - referencePrice) / std::max(referencePrice, kMinimumPrice);
        priceResult.logReturn = std::log(priceResult.nextPrice / referencePrice);
    }

    return priceResult;
}

void MarketProcess::initializeAgentWealths(SimulationPopulation& population,
                                           const std::vector<double>& marketPrices) {
    for (AgentRecord& record : population.records) {
        record.agent.initializeWealth(marketPrices);
    }
}

void MarketProcess::refreshAgentWealths(SimulationPopulation& population,
                                        const std::vector<double>& marketPrices) {
    for (AgentRecord& record : population.records) {
        record.agent.updateWealth(marketPrices);
    }
}

} // namespace abm
