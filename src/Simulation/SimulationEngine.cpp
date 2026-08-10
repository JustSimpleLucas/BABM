// SimulationEngine.cpp

#include "Simulation/SimulationEngine.h"

#include "ControlParameters/SimulationConfigValidation.h"
#include "Market/CovarianceEstimator.h"
#include "Simulation/MarketProcess.h"
#include "Simulation/PopulationFactory.h"

#include <utility>

namespace abm {

SimulationEngine::SimulationEngine(SimulationConfig config)
    : config_(std::move(config)), fundamentalProcess_(config_.seed), random_(config_.seed + 1U) {
    validateSimulationConfig(config_);
    normaliseSimulationConfig(config_);

    population_ = PopulationFactory::createPopulation(config_, random_);
    socialInfluenceModel_.initialize(population_, config_.social, random_);
    (void)MarketProcess::initializeMarket(market_, fundamentalProcess_, config_, random_);
    MarketProcess::initializeAgentWealths(population_, latestMarketPrices());
}

std::vector<double> SimulationEngine::latestMarketPrices() const {
    std::vector<double> prices;
    prices.reserve(config_.assets.size());
    for (std::size_t assetIndex = 0; assetIndex < config_.assets.size(); ++assetIndex) {
        prices.push_back(market_.getMarketValues(assetIndex).back());
    }
    return prices;
}

SimulationRunResult SimulationEngine::run(const ProgressCallback& progressCallback,
                                          bool recordTradeLedger) {
    SimulationClock clock(config_.timeSteps);

    const std::size_t assetCount = config_.assets.size();
    const std::size_t primaryIndex = config_.assets.primaryIndex();

    PopulationFactory::resetRunState(population_);
    diagnosticsRecorder_.resetForRun(config_, population_.records.size(), market_,
                                     recordTradeLedger);
    orderCollector_.resetForRun();
    marketClearingEngine_.resetForRun(assetCount);
    riskControlService_.reset(population_, config_);
    socialInfluenceModel_.prepareForRun(population_);

    for (std::size_t step = 1; step <= clock.totalSteps(); ++step) {
        MarketProcess::accrueRiskFreeCash(population_, config_.riskFreeRate);

        const std::vector<double> newFundamentals =
            MarketProcess::generateNextFundamentals(market_, fundamentalProcess_, config_);
        socialInfluenceModel_.updateOpinions(population_, config_.social, random_);

        const std::vector<double> referencePrices = latestMarketPrices();
        std::vector<RestingOrderLifecycleCounts> lifecycleCounts =
            marketClearingEngine_.processRestingOrders(
                RestingOrderProcessingRequest{step, &referencePrices, &config_.microstructure},
                random_);

        const std::vector<std::size_t>& activeAgentIndices = activationScheduler_.schedule(
            AgentActivationRequest{population_.records.size(), config_.agentActivityRate}, random_);
        const SymmetricMatrix covariance =
            estimateLogReturnCovariance(market_, config_.covarianceWindow);
        std::vector<Order> orders = orderCollector_.collectOrders(
            step, activeAgentIndices, population_, market_, config_, random_, covariance);
        const std::size_t submittedOrders = orders.size();

        std::vector<MicrostructureStepResult> microstructureResults =
            marketClearingEngine_.executeOrders(OrderExecutionRequest{
                &orders, &referencePrices, std::move(lifecycleCounts), &config_,
                &population_.agentsById, &riskControlService_,
                &diagnosticsRecorder_.externalTradeLedger(),
                diagnosticsRecorder_.nextTradeIdCounter(), recordTradeLedger});

        std::vector<PriceFormationResult> priceResults(assetCount);
        std::vector<double> nextPrices(assetCount);
        for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
            priceResults[assetIndex] = MarketProcess::resolvePriceAfterClearing(
                referencePrices[assetIndex], microstructureResults[assetIndex]);
            nextPrices[assetIndex] = priceResults[assetIndex].nextPrice;
            market_.storeMarketValue(assetIndex, nextPrices[assetIndex]);
        }
        MarketProcess::refreshAgentWealths(population_, nextPrices);
        const ForcedBuyInResult forcedBuyIns = riskControlService_.enforceMaintenanceMargin(
            nextPrices, step, config_, population_.agentsById,
            diagnosticsRecorder_.externalTradeLedger(), *diagnosticsRecorder_.nextTradeIdCounter(),
            recordTradeLedger);
        for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
            microstructureResults[assetIndex].tradedVolume +=
                forcedBuyIns.volumeByAsset[assetIndex];
            microstructureResults[assetIndex].totalTransactionCosts +=
                forcedBuyIns.transactionCostsByAsset[assetIndex];
        }
        if (forcedBuyIns.volume > 0.0) {
            // Forced buy-ins change agent cash/stock after the first wealth refresh, so only
            // re-run the O(population) wealth pass when a margin call actually traded.
            MarketProcess::refreshAgentWealths(population_, nextPrices);
        }

        diagnosticsRecorder_.recordStep(StepRecordingRequest{
            step, &config_, population_.records.size(), referencePrices[primaryIndex],
            newFundamentals[primaryIndex], submittedOrders, &microstructureResults[primaryIndex],
            &priceResults[primaryIndex], &population_, &microstructureResults, &priceResults,
            &referencePrices, &newFundamentals});

        clock.markStepCompleted(step, progressCallback);
    }

    diagnosticsRecorder_.completeRun(population_);
    return diagnosticsRecorder_.buildResult(config_, market_);
}

const SimulationConfig& SimulationEngine::config() const {
    return config_;
}

} // namespace abm
