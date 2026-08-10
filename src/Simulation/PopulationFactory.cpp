// PopulationFactory.cpp

#include "Simulation/PopulationFactory.h"

#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/BuyAndHoldStrategy.h"
#include "AgentStrategy/ChartistStrategyFactory.h"
#include "AgentStrategy/FundamentalistStrategy.h"
#include "AgentStrategy/NoiseTraderStrategy.h"
#include "BehaviouralFinance/ProspectPreferenceSampler.h"

#include <algorithm>
#include <cmath>
#include <memory>
#include <numeric>
#include <string>
#include <utility>
#include <vector>

namespace abm {
namespace {

enum class InitialStrategyKind : std::uint8_t {
    Fundamentalist,
    Chartist,
    NoiseTrader,
    BuyAndHold,
};

std::uint64_t noiseTraderSeed(std::uint64_t simulationSeed, std::uint32_t agentId) {
    return simulationSeed + 0x9E3779B97F4A7C15ULL +
           (static_cast<std::uint64_t>(agentId) * 0xBF58476D1CE4E5B9ULL);
}

std::uint64_t prospectAssignmentSeed(std::uint64_t simulationSeed) {
    return simulationSeed ^ 0xD1B54A32D192ED03ULL;
}

std::vector<bool> selectProspectTheoryUsers(const SimulationConfig& config,
                                            std::size_t totalAgents) {
    std::vector<bool> selected(totalAgents, false);
    if (!config.control.prospectTheoryEnabled || totalAgents == 0) {
        return selected;
    }

    const double requestedAgents =
        std::round(config.control.prospectTheoryAgentFraction * static_cast<double>(totalAgents));
    const std::size_t enabledAgents =
        std::min(totalAgents, static_cast<std::size_t>(std::max(0.0, requestedAgents)));
    if (enabledAgents == 0) {
        return selected;
    }

    std::vector<std::size_t> shuffledPositions(totalAgents);
    std::iota(shuffledPositions.begin(), shuffledPositions.end(), std::size_t{0});

    /*
     * Assignment uses its own deterministic stream so changing the fraction
     * does not consume the main simulation stream used for strategies,
     * preference heterogeneity, and later market dynamics.
     */
    RandomEngine assignmentRandom(prospectAssignmentSeed(config.seed));
    assignmentRandom.shuffle(shuffledPositions.begin(), shuffledPositions.end());

    auto shuffledPositionIt = shuffledPositions.cbegin();
    for (std::size_t assignedAgents = 0; assignedAgents < enabledAgents;
         ++assignedAgents, ++shuffledPositionIt) {
        selected.at(*shuffledPositionIt) = true;
    }
    return selected;
}

} // namespace

SimulationPopulation PopulationFactory::createPopulation(const SimulationConfig& config,
                                                         RandomEngine& random) {
    const std::size_t totalAgents = config.numFundamentalists + config.numChartists +
                                    config.numNoiseTraders + config.numBuyAndHoldAgents;

    SimulationPopulation population;
    population.records.reserve(totalAgents);
    population.agentsById.assign(totalAgents + 1, nullptr);

    const AssetAllocationLine fundamentalistAllocation(
        config.fundamentalist.allocation.riskAversion,
        config.fundamentalist.allocation.minRiskyWeight,
        config.fundamentalist.allocation.maxRiskyWeight);
    FundamentalistStrategyParameters fundamentalistParameters;
    fundamentalistParameters.assetIndex = config.assets.primaryIndex();
    fundamentalistParameters.allocationLine = fundamentalistAllocation;
    fundamentalistParameters.mispricingThreshold = config.fundamentalist.mispricingThreshold;
    fundamentalistParameters.riskThresholds = FundamentalistRiskThresholds{
        config.fundamentalist.stopLossThreshold, config.fundamentalist.takeProfitThreshold};
    fundamentalistParameters.volatilityWindow = config.fundamentalist.volatilityWindow;
    fundamentalistParameters.riskFreeRate = config.riskFreeRate;
    fundamentalistParameters.referencePointMode = config.control.referencePointMode;
    fundamentalistParameters.referenceMovingAverageWindow =
        config.control.referenceMovingAverageWindow;
    fundamentalistParameters.maxGrossExposure = config.fundamentalist.allocation.maxGrossExposure;
    const AssetAllocationLine chartistAllocation(config.chartist.allocation.riskAversion,
                                                 config.chartist.allocation.minRiskyWeight,
                                                 config.chartist.allocation.maxRiskyWeight);

    std::vector<InitialStrategyKind> initialAssignments;
    initialAssignments.reserve(totalAgents);
    for (std::size_t i = 0; i < config.numFundamentalists; ++i) {
        initialAssignments.push_back(InitialStrategyKind::Fundamentalist);
    }
    for (std::size_t i = 0; i < config.numChartists; ++i) {
        initialAssignments.push_back(InitialStrategyKind::Chartist);
    }
    for (std::size_t i = 0; i < config.numNoiseTraders; ++i) {
        initialAssignments.push_back(InitialStrategyKind::NoiseTrader);
    }
    for (std::size_t i = 0; i < config.numBuyAndHoldAgents; ++i) {
        initialAssignments.push_back(InitialStrategyKind::BuyAndHold);
    }

    /*
     * Initial strategy composition is controlled by the configured counts, but
     * the assignment is shuffled before numerical IDs are allocated. Agent IDs
     * therefore represent persistent identities only, not membership in a
     * strategy-specific container or contiguous strategy block.
     */
    random.shuffle(initialAssignments.begin(), initialAssignments.end());
    const std::vector<bool> prospectTheoryUsers =
        selectProspectTheoryUsers(config, initialAssignments.size());

    AgentEndowment initialEndowment{config.initialCash, {}};
    initialEndowment.stockByAsset.reserve(config.assets.size());
    for (const AssetDefinition& asset : config.assets) {
        initialEndowment.stockByAsset.push_back(asset.initialStock);
    }

    std::uint32_t nextId = 1;
    std::size_t creationIndex = 0;
    for (InitialStrategyKind strategyKind : initialAssignments) {
        const ProspectTheory prospectPreferences = drawProspectPreferences(config.control, random);
        const bool agentUsesProspectTheory = prospectTheoryUsers.at(creationIndex);
        Agent agent(nextId, initialEndowment, prospectPreferences, agentUsesProspectTheory);

        std::unique_ptr<TradingStrategy> strategy;
        if (strategyKind == InitialStrategyKind::Fundamentalist) {
            strategy = std::make_unique<FundamentalistStrategy>(fundamentalistParameters);
        } else if (strategyKind == InitialStrategyKind::Chartist) {
            strategy = createChartistStrategy(config, chartistAllocation, random);
        } else if (strategyKind == InitialStrategyKind::NoiseTrader) {
            strategy = std::make_unique<NoiseTraderStrategy>(
                config.assets.primaryIndex(), config.noiseTrader.beliefShockStdDev,
                config.noiseTrader.orderSizeFraction, config.noiseTrader.maxShortWeight,
                noiseTraderSeed(config.seed, nextId));
        } else {
            strategy = std::make_unique<BuyAndHoldStrategy>(config.assets.primaryIndex(),
                                                            config.buyAndHold.targetRiskyWeight);
        }

        const std::string initialStrategyType = strategy->strategyType();
        population.records.push_back(AgentRecord{agent, initialStrategyType, std::move(strategy)});
        population.agentsById.at(nextId) = &population.records.back().agent;
        ++nextId;
        ++creationIndex;
    }

    return population;
}

void PopulationFactory::resetRunState(SimulationPopulation& population) {
    for (AgentRecord& record : population.records) {
        record.agent.resetTradeStats();
    }
    auto agentIt = population.agentsById.begin();
    if (agentIt != population.agentsById.end()) {
        ++agentIt;
    }
    for (; agentIt != population.agentsById.end(); ++agentIt) {
        Agent* agent = *agentIt;
        if (agent != nullptr) {
            agent->setOpinions(0.0, 0.0);
        }
    }
}

} // namespace abm
