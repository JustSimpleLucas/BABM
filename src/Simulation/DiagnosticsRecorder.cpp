// DiagnosticsRecorder.cpp

#include "Simulation/DiagnosticsRecorder.h"

#include "Analysis/StylisedFactMetrics.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>
#include <utility>

namespace abm {

void DiagnosticsRecorder::resetForRun(const SimulationConfig& config, std::size_t populationSize,
                                      const Market& market, bool recordTradeLedger) {
    stats_ = SimulationStats{};
    const std::size_t primaryIndex = config.assets.primaryIndex();
    stats_.finalMarketPrice = market.getMarketValues(primaryIndex).back();
    stats_.finalFundamentalPrice = market.getTrueValues(primaryIndex).back();

    stepDetails_.clear();
    stepDetails_.reserve(config.timeSteps);
    assetStepDetails_.clear();
    assetStepDetails_.reserve(config.timeSteps * std::max<std::size_t>(1, config.assets.size()));
    agentSnapshots_.clear();
    externalTradeLedger_.clear();
    if (recordTradeLedger) {
        externalTradeLedger_.reserve(config.timeSteps * std::max<std::size_t>(2, populationSize));
    } else {
        externalTradeLedger_.shrink_to_fit();
    }
    nextTradeId_ = 1;
}

std::vector<ExternalTradeLedgerRecord>& DiagnosticsRecorder::externalTradeLedger() {
    return externalTradeLedger_;
}

std::size_t* DiagnosticsRecorder::nextTradeIdCounter() {
    return &nextTradeId_;
}

namespace {

/**
 * Maps one asset's clearing outcome onto its per-step record.
 *
 * Both the per-asset series and the primary-asset step series go through this
 * function, so a new per-asset column is wired up in one place. The two used to
 * be separate assignment blocks listing the same twenty-three fields, which
 * could drift apart silently.
 *
 * Fields are assigned by name rather than through a positional initializer
 * list: a positional mistake between adjacent same-typed members would compile
 * cleanly and corrupt the exported research time series.
 */
[[nodiscard]] AssetStepDetails buildAssetStepRecord(std::size_t step, std::size_t assetIndex,
                                                    double referencePrice,
                                                    double fundamentalPrice,
                                                    const MicrostructureStepResult& microstructure,
                                                    const PriceFormationResult& price) {
    AssetStepDetails record{};
    record.step = step;
    record.assetIndex = static_cast<std::uint32_t>(assetIndex);
    record.referencePrice = referencePrice;
    record.marketPrice = price.nextPrice;
    record.fundamentalPrice = fundamentalPrice;
    record.rawReturn = price.rawReturn;
    record.logReturn = price.logReturn;
    record.submittedLimitOrders = microstructure.submittedLimitOrders;
    record.submittedMarketOrders = microstructure.submittedMarketOrders;
    record.tradedVolume = microstructure.tradedVolume;
    record.executedTrades = microstructure.executedTrades;
    record.lastTradePrice = microstructure.lastTradePrice;
    record.bestBid = microstructure.bookMetrics.bestBid;
    record.bestAsk = microstructure.bookMetrics.bestAsk;
    record.bidAskSpread = microstructure.bookMetrics.bidAskSpread;
    record.midQuote = microstructure.bookMetrics.midQuote;
    record.bidDepth = microstructure.bookMetrics.bidDepth;
    record.askDepth = microstructure.bookMetrics.askDepth;
    record.restingBidOrders = microstructure.bookMetrics.restingBidOrders;
    record.restingAskOrders = microstructure.bookMetrics.restingAskOrders;
    record.staleCancelledOrders = microstructure.staleCancelledOrders;
    record.expiredOrders = microstructure.expiredOrders;
    record.infeasibleRestingCancellations = microstructure.infeasibleRestingCancellations;
    record.infeasibleIncomingCancellations = microstructure.infeasibleIncomingCancellations;
    record.selfTradePreventions = microstructure.selfTradePreventions;
    record.collarRejectedOrders = microstructure.collarRejectedOrders;
    record.totalTransactionCosts = microstructure.totalTransactionCosts;
    record.realizedAllocativeSurplus = microstructure.realizedAllocativeSurplus;
    record.maximumAllocativeSurplus = microstructure.maximumAllocativeSurplus;
    record.allocativeEfficiency = microstructure.allocativeEfficiency;
    return record;
}

} // namespace

void DiagnosticsRecorder::recordStep(const StepRecordingRequest& request) {
    const double aggregateStartingCash =
        static_cast<double>(std::max<std::size_t>(1, request.populationSize)) *
        std::max(request.config->initialCash, 1.0);
    const double notionalImbalance =
        request.microstructureResult->netDemand * request.referencePrice;
    const double normalizedImbalance =
        std::clamp(notionalImbalance / aggregateStartingCash, -1.0, 1.0);
    const double fundamentalSignal = (request.newFundamental - request.referencePrice) /
                                     std::max(request.referencePrice, kMinimumPrice);
    constexpr double randomShock = 0.0;
    const double wealthGiniCoefficient =
        request.population != nullptr ? calculateWealthGiniCoefficient(*request.population) : 0.0;

    const MicrostructureStepResult& microstructure = *request.microstructureResult;
    StepDetails stepRecord{};
    stepRecord.asset = buildAssetStepRecord(
        request.step, request.config->assets.primaryIndex(), request.referencePrice,
        request.newFundamental, microstructure, *request.priceResult);
    stepRecord.submittedOrders = request.submittedOrders;
    stepRecord.netDemand = microstructure.netDemand;
    stepRecord.notionalImbalance = notionalImbalance;
    stepRecord.normalizedImbalance = normalizedImbalance;
    stepRecord.fundamentalSignal = fundamentalSignal;
    stepRecord.randomShock = randomShock;
    stepRecord.cancelledOrders = microstructure.cancelledOrders;
    stepRecord.wealthGiniCoefficient = wealthGiniCoefficient;
    stepDetails_.push_back(std::move(stepRecord));

    stats_.completedSteps = request.step;
    stats_.finalMarketPrice = request.priceResult->nextPrice;
    stats_.finalFundamentalPrice = request.newFundamental;
    stats_.totalTradedVolume += request.microstructureResult->tradedVolume;
    stats_.totalTransactionCosts += request.microstructureResult->totalTransactionCosts;
    stats_.averageAbsoluteOrderImbalance += std::abs(notionalImbalance);

    recordAssetSteps(request);
}

void DiagnosticsRecorder::recordAssetSteps(const StepRecordingRequest& request) {
    if (request.perAssetResults == nullptr || request.perAssetPriceResults == nullptr ||
        request.referencePrices == nullptr || request.newFundamentals == nullptr) {
        return;
    }

    const std::size_t assetCount = request.perAssetResults->size();

    /*
     * Portfolio composition is aggregated once per step across all assets, so
     * each agent's wealth is computed a single time rather than once per asset.
     * Only agents with strictly positive wealth contribute: a bankrupt agent's
     * weights are not economically interpretable and, being ratios over a
     * near-zero denominator, would otherwise dominate the cross-sectional mean.
     */
    std::vector<double> meanPortfolioWeights(assetCount, 0.0);
    std::size_t solventAgentCount = 0;
    if (request.population != nullptr) {
        for (const AgentRecord& agentRecord : request.population->records) {
            const Agent& agent = agentRecord.agent;
            double agentWealth = agent.getCash();
            for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
                agentWealth +=
                    agent.getStock(assetIndex) * (*request.perAssetPriceResults)[assetIndex].nextPrice;
            }
            if (!(agentWealth > 0.0)) {
                continue;
            }
            ++solventAgentCount;
            for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
                const double assetValue =
                    agent.getStock(assetIndex) * (*request.perAssetPriceResults)[assetIndex].nextPrice;
                meanPortfolioWeights[assetIndex] += assetValue / agentWealth;
            }
        }
        if (solventAgentCount > 0) {
            for (double& weight : meanPortfolioWeights) {
                weight /= static_cast<double>(solventAgentCount);
            }
        }
    }

    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        const MicrostructureStepResult& microstructure = (*request.perAssetResults)[assetIndex];
        const PriceFormationResult& price = (*request.perAssetPriceResults)[assetIndex];

        AssetStepDetails record = buildAssetStepRecord(
            request.step, assetIndex, (*request.referencePrices)[assetIndex],
            (*request.newFundamentals)[assetIndex], microstructure, price);
        record.meanAgentPortfolioWeight = meanPortfolioWeights[assetIndex];
        record.portfolioWeightAgentCount = solventAgentCount;
        assetStepDetails_.push_back(record);
    }
}

void DiagnosticsRecorder::completeRun(const SimulationPopulation& population) {
    if (stats_.completedSteps > 0) {
        stats_.averageAbsoluteOrderImbalance /= static_cast<double>(stats_.completedSteps);
    }

    refreshAgentSnapshots(population);
}

SimulationRunResult DiagnosticsRecorder::buildResult(const SimulationConfig& config,
                                                     const Market& market) {
    MultiAssetRunData multiAssetData;
    for (std::size_t assetIndex = 0; assetIndex < config.assets.size(); ++assetIndex) {
        multiAssetData.assetNames.push_back(config.assets[assetIndex].name);
        multiAssetData.marketPriceHistories.push_back(market.getMarketValues(assetIndex));
        multiAssetData.fundamentalPriceHistories.push_back(market.getTrueValues(assetIndex));
    }
    multiAssetData.assetStepDetails = std::move(assetStepDetails_);

    return {config,
            stats_,
            std::move(stepDetails_),
            std::move(agentSnapshots_),
            std::move(externalTradeLedger_),
            std::move(multiAssetData)};
}

const SimulationStats& DiagnosticsRecorder::stats() const {
    return stats_;
}

const std::vector<StepDetails>& DiagnosticsRecorder::stepDetails() const {
    return stepDetails_;
}

void DiagnosticsRecorder::refreshAgentSnapshots(const SimulationPopulation& population) {
    agentSnapshots_.clear();
    agentSnapshots_.reserve(population.records.size());

    /*
     * As with StepDetails, the snapshot fields are assigned by name because the
     * struct holds many adjacent doubles; positional initialization would make
     * silent field-order mistakes possible when the snapshot schema evolves.
     */
    for (const AgentRecord& record : population.records) {
        const Agent& agent = record.agent;
        AgentSnapshot snapshot{};
        snapshot.agentId = agent.getNumericalId();
        snapshot.initialStrategyType = record.initialStrategyType;
        snapshot.currentStrategyType =
            record.currentStrategy != nullptr ? record.currentStrategy->strategyType() : "none";
        snapshot.initialCash = agent.getInitialCash();
        snapshot.initialStock = agent.getInitialStock(0);
        snapshot.initialWealth = agent.getInitialWealth();
        snapshot.xCoordinate = agent.getXCoordinate();
        snapshot.yCoordinate = agent.getYCoordinate();
        snapshot.socialGamma = agent.getSocialGamma();
        snapshot.privateSignalStdDev = agent.getPrivateSignalStdDev();
        snapshot.finalOpinion = agent.getCurrentOpinion();
        snapshot.finalCash = agent.getCash();
        snapshot.finalStock = agent.getStock(0);
        snapshot.tradeCount = agent.getExecutedTradeCount();
        snapshot.tradedVolume = agent.getExecutedTradeVolume();
        snapshot.cumulativeTransactionCostsPaid = agent.getCumulativeTransactionCostsPaid();
        snapshot.finalWealth = agent.getWealth();
        snapshot.averageEntryPrice = agent.getAverageEntryPrice(0);
        snapshot.recentPeakWealth = agent.getRecentPeakWealth();
        snapshot.lastProspectReferencePoint = agent.getLastProspectReferencePoint();
        snapshot.prospectTheoryEnabled = agent.usesProspectTheory();
        snapshot.prospectLossAversion = agent.prospectTheory().lossAversion();
        snapshot.prospectCurvatureForGain = agent.prospectTheory().curvatureForGain();
        snapshot.prospectCurvatureForLoss = agent.prospectTheory().curvatureForLoss();
        snapshot.prospectProbabilityDistortionForGain =
            agent.prospectTheory().probDistortionForGain();
        snapshot.prospectProbabilityDistortionForLoss =
            agent.prospectTheory().probDistortionForLoss();
        snapshot.prospectScenarioCount = agent.prospectTheory().scenarioCount();
        agentSnapshots_.push_back(std::move(snapshot));
    }
}

double DiagnosticsRecorder::calculateWealthGiniCoefficient(const SimulationPopulation& population) {
    std::vector<double> wealthValues;
    wealthValues.reserve(population.records.size());
    for (const AgentRecord& record : population.records) {
        wealthValues.push_back(record.agent.getWealth());
    }
    return calculateNonNegativeGiniCoefficient(std::move(wealthValues));
}

} // namespace abm
