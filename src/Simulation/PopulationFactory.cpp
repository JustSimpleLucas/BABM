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
#include <cstdint>
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

/**
 * Builds the protagonist's Cumulative Prospect Theory preferences.
 *
 * Deliberately not routed through drawProspectPreferences: that function samples
 * from the population's dispersion parameters, which is the correct treatment
 * for an anonymous crowd and the wrong one for a named individual. Reading his
 * five parameters straight out of the configuration keeps his psychology stated
 * rather than drawn, and — because nothing is sampled — leaves the shared agent
 * random stream untouched.
 *
 * The scenario count and reference-point scale stay population-wide: they
 * describe how any CPT valuation is discretised in this model, not what one
 * investor believes.
 */
ProspectTheory buildProtagonistPreferences(const SimulationConfig& config) {
    ProspectTheoryParameters parameters;
    parameters.lossAversion = config.protagonist.lossAversion;
    parameters.curvatureForGain = config.protagonist.curvatureForGain;
    parameters.curvatureForLoss = config.protagonist.curvatureForLoss;
    parameters.probDistortionForGain = config.protagonist.probDistortionForGain;
    parameters.probDistortionForLoss = config.protagonist.probDistortionForLoss;
    parameters.referencePoint = config.control.referencePoint;
    parameters.scenarioCount = config.control.prospectScenarioCount;
    return ProspectTheory(parameters);
}

/**
 * Builds the protagonist's trading strategy from his own parameters.
 *
 * He runs one of the four ordinary rules, so this mirrors the four branches of
 * the population loop; the only difference is where the numbers come from. His
 * chartist rule is taken from configuration rather than sampled, so no branch
 * here consumes a random draw.
 */
std::unique_ptr<TradingStrategy> createProtagonistStrategy(const SimulationConfig& config,
                                                           std::uint32_t agentId) {
    const ProtagonistConfig& protagonist = config.protagonist;
    const AssetAllocationLine allocationLine(protagonist.allocation.riskAversion,
                                             protagonist.allocation.minRiskyWeight,
                                             protagonist.allocation.maxRiskyWeight);

    switch (protagonist.strategy) {
    case ProtagonistStrategyKind::Chartist: {
        ChartistRuleSettings settings;
        settings.assetIndex = config.assets.primaryIndex();
        settings.allocationLine = allocationLine;
        settings.shortWindow = protagonist.shortWindow;
        settings.longWindow = protagonist.longWindow;
        settings.momentumSignalThreshold = protagonist.momentumSignalThreshold;
        settings.breakoutWindow = protagonist.breakoutWindow;
        settings.volatilityWindow = protagonist.volatilityWindow;
        settings.maxShortWeight = protagonist.maxShortWeight;
        settings.maxGrossExposure = protagonist.allocation.maxGrossExposure;
        settings.forecastHorizon = protagonist.forecastHorizon;
        settings.riskFreeRate = config.riskFreeRate;
        settings.referencePointMode = config.control.referencePointMode;
        settings.referenceMovingAverageWindow = config.control.referenceMovingAverageWindow;
        return createChartistStrategy(protagonist.chartistRule, settings);
    }
    case ProtagonistStrategyKind::NoiseTrader:
        return std::make_unique<NoiseTraderStrategy>(
            config.assets.primaryIndex(), protagonist.noiseBeliefShockStdDev,
            protagonist.noiseOrderSizeFraction, protagonist.maxShortWeight,
            noiseTraderSeed(config.seed, agentId));
    case ProtagonistStrategyKind::BuyAndHold:
        return std::make_unique<BuyAndHoldStrategy>(config.assets.primaryIndex(),
                                                    protagonist.buyHoldTargetRiskyWeight);
    case ProtagonistStrategyKind::Fundamentalist:
        break;
    }

    FundamentalistStrategyParameters parameters;
    parameters.assetIndex = config.assets.primaryIndex();
    parameters.allocationLine = allocationLine;
    parameters.mispricingThreshold = protagonist.mispricingThreshold;
    parameters.riskThresholds = FundamentalistRiskThresholds{protagonist.stopLossThreshold,
                                                             protagonist.takeProfitThreshold};
    parameters.volatilityWindow = protagonist.volatilityWindow;
    parameters.riskFreeRate = config.riskFreeRate;
    parameters.referencePointMode = config.control.referencePointMode;
    parameters.referenceMovingAverageWindow = config.control.referenceMovingAverageWindow;
    parameters.maxGrossExposure = protagonist.allocation.maxGrossExposure;
    parameters.forecastHorizon = protagonist.forecastHorizon;
    return std::make_unique<FundamentalistStrategy>(parameters);
}

} // namespace

SimulationPopulation PopulationFactory::createPopulation(const SimulationConfig& config,
                                                         RandomEngine& random) {
    const std::size_t totalAgents = config.numFundamentalists + config.numChartists +
                                    config.numNoiseTraders + config.numBuyAndHoldAgents;

    const std::size_t protagonistCount = config.protagonist.enabled ? 1U : 0U;

    SimulationPopulation population;
    population.records.reserve(totalAgents + protagonistCount);
    population.agentsById.assign(totalAgents + protagonistCount + 1, nullptr);

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
    fundamentalistParameters.forecastHorizon = config.fundamentalist.forecastHorizon;
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

    /*
     * The protagonist is created last, and only after every anonymous agent has
     * drawn its preferences and its strategy. That ordering is what makes the
     * construct safe to switch on and off: the shuffle above, the CPT assignment
     * and every per-agent draw are already complete, and nothing in this block
     * touches `random`. A configuration with `protagonist_enabled = 0` therefore
     * produces exactly the population it produced before he existed.
     *
     * He takes the highest agent id, which is also what lets the analysis layer
     * recognise him in an archive written before the is_protagonist column
     * existed.
     */
    if (config.protagonist.enabled) {
        AgentEndowment protagonistEndowment{config.protagonist.initialCash, {}};
        protagonistEndowment.stockByAsset.assign(config.assets.size(),
                                                 config.protagonist.initialStock);

        Agent protagonist(nextId, protagonistEndowment, buildProtagonistPreferences(config),
                          config.protagonist.prospectTheoryEnabled);
        std::unique_ptr<TradingStrategy> strategy = createProtagonistStrategy(config, nextId);

        const std::string initialStrategyType = strategy->strategyType();
        population.records.push_back(
            AgentRecord{protagonist, initialStrategyType, std::move(strategy)});
        population.agentsById.at(nextId) = &population.records.back().agent;
        population.protagonistRecordIndex = population.records.size() - 1;
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
