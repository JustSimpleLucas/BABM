// ProspectTheoryTests.cpp

#include "tests/cpp/TestSupport.h"

#include "Agent/Agent.h"
#include "AgentStrategy/StrategyMarketHelpers.h"
#include "BehaviouralFinance/ProspectTheory.h"
#include "Market/Market.h"
#include "Simulation/SimulationEngine.h"

#include <cmath>
#include <cstdint>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {

void applyExecutedTrade(abm::Agent& agent, abm::OrderType side, double executionPrice,
                        double quantity) {
    agent.recordExecutedTrade(0, abm::ExecutedTrade{side, executionPrice, quantity});
    const double signedQuantity = side == abm::OrderType::BUY ? quantity : -quantity;
    agent.updateStock(0, agent.getStock(0) + signedQuantity);
}

std::vector<std::uint32_t> prospectTheoryAgentIds(const abm::SimulationRunResult& result) {
    std::vector<std::uint32_t> selectedIds;
    for (const abm::AgentSnapshot& snapshot : result.agentSnapshots()) {
        if (snapshot.prospectTheoryEnabled) {
            selectedIds.push_back(snapshot.agentId);
        }
    }
    return selectedIds;
}

void testProspectTheoryPreferences(int& failures) {
    abm::ProspectTheoryParameters parameters{};
    parameters.lossAversion = 2.25;
    parameters.curvatureForGain = 1.0;
    parameters.curvatureForLoss = 1.0;
    parameters.probDistortionForGain = 1.0;
    parameters.probDistortionForLoss = 1.0;
    parameters.referencePoint = 100.0;
    const abm::ProspectTheory prospectTheory(parameters);

    abm::test::expect(abm::test::nearlyEqual(prospectTheory.valueFunction(10.0), 10.0),
                      "gain-domain value should equal the gain when curvature is one", failures);
    abm::test::expect(abm::test::nearlyEqual(prospectTheory.valueFunction(-10.0), -22.5),
                      "loss-domain value should apply the loss-aversion multiplier", failures);
    abm::test::expect(abm::test::nearlyEqual(
                          prospectTheory.probabilityWeight(0.25, abm::ProspectDomain::Gain), 0.25),
                      "probability weighting should be identity when gamma is one", failures);

    const std::vector<abm::ProspectOutcome> outcomes{
        {10.0, 0.5},
        {-10.0, 0.5},
    };
    abm::test::expect(
        abm::test::nearlyEqual(prospectTheory.calculateProspectValue(outcomes), -6.25),
        "mixed equal-probability outcomes should reflect loss aversion", failures);
    abm::test::expect(
        abm::test::nearlyEqual(prospectTheory.prospectAdjustedReturn({0.02, 0.0, 0.0}), 0.02),
        "a certain positive return should remain unchanged with linear preferences", failures);
    abm::test::expect(
        abm::test::nearlyEqual(prospectTheory.prospectAdjustedReturn({-0.02, 0.0, 0.0}), -0.045),
        "a certain negative return should be magnified by loss aversion", failures);
}

void testCumulativeProspectTheoryDecisionWeights(int& failures) {
    abm::ProspectTheoryParameters parameters{};
    parameters.lossAversion = 1.0;
    parameters.curvatureForGain = 1.0;
    parameters.curvatureForLoss = 1.0;
    parameters.probDistortionForGain = 0.5;
    parameters.probDistortionForLoss = 0.5;
    parameters.referencePoint = 100.0;
    const abm::ProspectTheory prospectTheory(parameters);

    const std::vector<abm::ProspectOutcome> outcomes{
        {5.0, 0.3},
        {-10.0, 0.5},
        {20.0, 0.2},
    };

    const double bestGainWeight = prospectTheory.probabilityWeight(0.2, abm::ProspectDomain::Gain);
    const double smallerGainWeight =
        prospectTheory.probabilityWeight(0.5, abm::ProspectDomain::Gain) -
        prospectTheory.probabilityWeight(0.2, abm::ProspectDomain::Gain);
    const double worstLossWeight = prospectTheory.probabilityWeight(0.5, abm::ProspectDomain::Loss);
    const double expectedCumulativeValue =
        bestGainWeight * 20.0 + smallerGainWeight * 5.0 - worstLossWeight * 10.0;

    abm::test::expect(abm::test::nearlyEqual(prospectTheory.calculateProspectValue(outcomes),
                                             expectedCumulativeValue),
                      "CPT valuation should use rank-dependent cumulative decision weights",
                      failures);

    const std::vector<abm::ProspectOutcome> reorderedOutcomes{
        {20.0, 0.2},
        {5.0, 0.3},
        {-10.0, 0.5},
    };
    abm::test::expect(
        abm::test::nearlyEqual(prospectTheory.calculateProspectValue(outcomes),
                               prospectTheory.calculateProspectValue(reorderedOutcomes)),
        "CPT valuation should be invariant to input order after ranking outcomes", failures);
}

void testProspectTheoryScenarioCountIsConfigurable(int& failures) {
    abm::ProspectTheoryParameters parameters{};
    parameters.lossAversion = 1.0;
    parameters.curvatureForGain = 1.0;
    parameters.curvatureForLoss = 1.0;
    parameters.probDistortionForGain = 1.0;
    parameters.probDistortionForLoss = 1.0;
    parameters.referencePoint = 100.0;
    parameters.scenarioCount = 5;
    const abm::ProspectTheory fiveScenarioProspectTheory(parameters);

    abm::test::expect(fiveScenarioProspectTheory.scenarioCount() == 5,
                      "Prospect Theory should store the configured odd scenario count", failures);
    abm::test::expect(abm::test::nearlyEqual(fiveScenarioProspectTheory.prospectAdjustedReturn(
                                                 abm::ProspectReturnForecast{0.02, 0.0, 0.0}),
                                             0.02),
                      "five-scenario valuation should preserve a certain positive linear return",
                      failures);

    try {
        parameters.scenarioCount = 4;
        const abm::ProspectTheory invalidProspectTheory(parameters);
        static_cast<void>(invalidProspectTheory);
        abm::test::expect(false, "Prospect Theory should reject even scenario counts", failures);
    } catch (const std::invalid_argument&) {
        abm::test::expect(true, "Prospect Theory should reject even scenario counts", failures);
    }
}

void testProspectTheoryCanBeDisabled(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.control.prospectTheoryEnabled = false;
    config.control.lossAversion = 0.0;
    config.control.curvatureForGain = 0.0;
    config.control.curvatureForLoss = 0.0;
    config.control.probDistortionForGain = 0.0;
    config.control.probDistortionForLoss = 0.0;
    config.control.referencePoint = 0.0;

    try {
        abm::SimulationEngine simulation(config);
        const abm::SimulationRunResult simulationResult = simulation.run();
        abm::test::expect(simulationResult.stepDetails().size() == config.timeSteps,
                          "disabled Prospect Theory should run the baseline simulation path",
                          failures);
        abm::test::expect(std::isfinite(simulationResult.stats().finalMarketPrice) &&
                              simulationResult.stats().finalMarketPrice > 0.0,
                          "disabled Prospect Theory should still produce a valid final price",
                          failures);
        for (const abm::AgentSnapshot& snapshot : simulationResult.agentSnapshots()) {
            abm::test::expect(!snapshot.prospectTheoryEnabled,
                              "disabled Prospect Theory should override the CPT agent fraction",
                              failures);
        }
    } catch (const std::exception& error) {
        std::cerr << "FAIL: disabled Prospect Theory should not validate inactive "
                     "Prospect Theory parameters: "
                  << error.what() << '\n';
        ++failures;
    }
}

void testProspectTheoryAgentFractionSelectsExactSeededSubset(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 2;
    config.numFundamentalists = 3;
    config.numChartists = 3;
    config.numNoiseTraders = 5;
    config.agentActivityRate = 0.0;
    config.social.enabled = false;
    config.control.prospectTheoryEnabled = true;
    config.control.prospectTheoryAgentFraction = 0.45;

    const abm::SimulationRunResult firstResult = abm::SimulationEngine(config).run();
    const abm::SimulationRunResult secondResult = abm::SimulationEngine(config).run();

    const std::vector<std::uint32_t> firstSelectedIds = prospectTheoryAgentIds(firstResult);
    const std::vector<std::uint32_t> secondSelectedIds = prospectTheoryAgentIds(secondResult);

    abm::test::expect(firstSelectedIds.size() == 5,
                      "CPT agent fraction should select round(fraction * total agents)", failures);
    abm::test::expect(firstSelectedIds == secondSelectedIds,
                      "CPT agent fraction assignment should be reproducible for a fixed seed",
                      failures);
}

void testProspectTheoryAgentFractionIncludesNoiseTraders(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 2;
    config.warmupSteps = 0;
    config.numFundamentalists = 0;
    config.numChartists = 0;
    config.numNoiseTraders = 6;
    config.agentActivityRate = 0.0;
    config.social.enabled = false;
    config.control.prospectTheoryEnabled = true;
    config.control.prospectTheoryAgentFraction = 0.5;

    const abm::SimulationRunResult result = abm::SimulationEngine(config).run();
    const std::vector<std::uint32_t> selectedIds = prospectTheoryAgentIds(result);

    abm::test::expect(selectedIds.size() == 3,
                      "CPT agent fraction should be applied to noise-trader-only populations",
                      failures);
    for (const abm::AgentSnapshot& snapshot : result.agentSnapshots()) {
        abm::test::expect(snapshot.initialStrategyType == "noise_trader",
                          "noise-only CPT fraction test should keep noise-trader strategies",
                          failures);
    }
}

void testProspectTheoryHeterogeneityAssignsAgentSpecificParameters(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.control.prospectTheoryEnabled = true;
    config.control.prospectParameterHeterogeneityEnabled = true;
    config.control.lossAversion = 2.25;
    config.control.lossAversionStdDev = 0.25;
    config.control.curvatureForGain = 0.88;
    config.control.curvatureForGainStdDev = 0.05;
    config.control.curvatureForLoss = 0.88;
    config.control.curvatureForLossStdDev = 0.05;
    config.control.probabilityDistortionMin = 0.65;
    config.control.probabilityDistortionMax = 0.85;

    abm::SimulationEngine simulation(config);
    const abm::SimulationRunResult simulationResult = simulation.run();

    const auto& snapshots = simulationResult.agentSnapshots();
    abm::test::expect(!snapshots.empty(),
                      "heterogeneous Prospect Theory run should export agent snapshots", failures);

    bool foundDifferentLossAversion = false;
    bool foundDifferentGainCurvature = false;
    if (!snapshots.empty()) {
        const double firstLossAversion = snapshots.front().prospectLossAversion;
        const double firstGainCurvature = snapshots.front().prospectCurvatureForGain;

        for (const abm::AgentSnapshot& snapshot : snapshots) {
            abm::test::expect(
                snapshot.prospectTheoryEnabled,
                "heterogeneous Prospect Theory snapshots should mark valuation as enabled",
                failures);
            abm::test::expect(snapshot.prospectLossAversion > 0.0,
                              "heterogeneous loss aversion draws should be positive", failures);
            abm::test::expect(snapshot.prospectCurvatureForGain > 0.0,
                              "heterogeneous gain curvature draws should be positive", failures);
            abm::test::expect(snapshot.prospectCurvatureForLoss > 0.0,
                              "heterogeneous loss curvature draws should be positive", failures);
            abm::test::expect(snapshot.prospectProbabilityDistortionForGain >=
                                      config.control.probabilityDistortionMin &&
                                  snapshot.prospectProbabilityDistortionForGain <=
                                      config.control.probabilityDistortionMax,
                              "heterogeneous gamma_i should lie inside the configured interval",
                              failures);
            abm::test::expect(abm::test::nearlyEqual(snapshot.prospectProbabilityDistortionForGain,
                                                     snapshot.prospectProbabilityDistortionForLoss),
                              "heterogeneous gamma_i should be shared across gain and loss domains",
                              failures);

            foundDifferentLossAversion =
                foundDifferentLossAversion ||
                !abm::test::nearlyEqual(snapshot.prospectLossAversion, firstLossAversion);
            foundDifferentGainCurvature =
                foundDifferentGainCurvature ||
                !abm::test::nearlyEqual(snapshot.prospectCurvatureForGain, firstGainCurvature);
        }
    }

    abm::test::expect(foundDifferentLossAversion,
                      "heterogeneous lambda_i should vary across agents for the deterministic seed",
                      failures);
    abm::test::expect(foundDifferentGainCurvature,
                      "heterogeneous alpha_i should vary across agents for the deterministic seed",
                      failures);
}

void testProspectTheoryRejectsEvenScenarioCountInEnabledRuns(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.control.prospectTheoryEnabled = true;
    config.control.prospectScenarioCount = 4;

    try {
        abm::SimulationEngine simulation(config);
        static_cast<void>(simulation);
        abm::test::expect(false, "enabled CPT runs should reject even scenario counts", failures);
    } catch (const std::invalid_argument&) {
        abm::test::expect(true, "enabled CPT runs should reject even scenario counts", failures);
    }
}

void testAgentTracksAverageEntryReferenceAcrossPositionChanges(int& failures) {
    abm::Agent agent(1U, abm::AgentEndowment{1000.0, {0.0}}, abm::ProspectTheory{}, true);
    agent.initializeWealth(std::vector<double>{100.0});

    applyExecutedTrade(agent, abm::OrderType::BUY, 100.0, 10.0);
    abm::test::expect(agent.getPositionDirection(0) == 1,
                      "buy execution should create a long position reference", failures);
    abm::test::expect(abm::test::nearlyEqual(agent.getAverageEntryPrice(0), 100.0),
                      "first long entry should set average purchase price", failures);

    applyExecutedTrade(agent, abm::OrderType::BUY, 120.0, 10.0);
    abm::test::expect(abm::test::nearlyEqual(agent.getAverageEntryPrice(0), 110.0),
                      "additional long buys should update weighted average entry", failures);

    applyExecutedTrade(agent, abm::OrderType::SELL, 130.0, 5.0);
    abm::test::expect(abm::test::nearlyEqual(agent.getAverageEntryPrice(0), 110.0),
                      "partial long sells should preserve average entry", failures);

    applyExecutedTrade(agent, abm::OrderType::SELL, 130.0, 15.0);
    abm::test::expect(agent.getPositionDirection(0) == 0,
                      "full liquidation should reset position direction", failures);
    abm::test::expect(!std::isfinite(agent.getAverageEntryPrice(0)),
                      "full liquidation should clear average entry price", failures);

    applyExecutedTrade(agent, abm::OrderType::SELL, 90.0, 4.0);
    abm::test::expect(agent.getPositionDirection(0) == -1,
                      "sell execution from flat should create a short reference", failures);
    abm::test::expect(abm::test::nearlyEqual(agent.getAverageEntryPrice(0), 90.0),
                      "first short sale should set short entry price", failures);

    applyExecutedTrade(agent, abm::OrderType::SELL, 80.0, 2.0);
    abm::test::expect(
        abm::test::nearlyEqual(agent.getAverageEntryPrice(0), (90.0 * 4.0 + 80.0 * 2.0) / 6.0),
        "additional short sales should update weighted short entry", failures);

    applyExecutedTrade(agent, abm::OrderType::BUY, 70.0, 3.0);
    abm::test::expect(
        abm::test::nearlyEqual(agent.getAverageEntryPrice(0), (90.0 * 4.0 + 80.0 * 2.0) / 6.0),
        "partial short covers should preserve short entry price", failures);

    applyExecutedTrade(agent, abm::OrderType::BUY, 75.0, 5.0);
    abm::test::expect(agent.getPositionDirection(0) == 1,
                      "trade through zero should flip the position direction", failures);
    abm::test::expect(abm::test::nearlyEqual(agent.getAverageEntryPrice(0), 75.0),
                      "direction flip should reset average entry to the crossing execution price",
                      failures);
}

void testProspectReferencePointResolutionModes(int& failures) {
    abm::Market market;
    market.configureAssets({"asset"});
    market.storeMarketValue(0, 100.0);
    market.storeMarketValue(0, 110.0);
    market.storeMarketValue(0, 120.0);

    abm::Agent agent(1U, abm::AgentEndowment{1000.0, {0.0}}, abm::ProspectTheory{}, true);
    agent.initializeWealth(std::vector<double>{100.0});
    applyExecutedTrade(agent, abm::OrderType::BUY, 150.0, 2.0);

    const double averagePurchaseReference = abm::strategy_detail::resolveProspectReferencePoint(
        agent, market, 0, abm::ProspectReferencePointMode::AveragePurchasePrice, 20, 120.0);
    abm::test::expect(abm::test::nearlyEqual(averagePurchaseReference, 150.0),
                      "average-purchase mode should use the agent's entry price", failures);

    const double configuredReference = abm::strategy_detail::resolveProspectReferencePoint(
        agent, market, 0, abm::ProspectReferencePointMode::Configured, 20, 120.0);
    abm::test::expect(abm::test::nearlyEqual(configuredReference, 100.0),
                      "configured mode should preserve the fixed CPT reference point", failures);

    const double movingAverageReference = abm::strategy_detail::resolveProspectReferencePoint(
        agent, market, 0, abm::ProspectReferencePointMode::MovingAveragePrice, 2, 120.0);
    abm::test::expect(abm::test::nearlyEqual(movingAverageReference, 115.0),
                      "moving-average mode should use the configured price lookback", failures);

    const double movingAverageFallback = abm::strategy_detail::resolveProspectReferencePoint(
        agent, market, 0, abm::ProspectReferencePointMode::MovingAveragePrice, 10, 120.0);
    abm::test::expect(abm::test::nearlyEqual(movingAverageFallback, 120.0),
                      "moving-average mode should fall back to latest price when history is short",
                      failures);

    const double peakWealthReference = abm::strategy_detail::resolveProspectReferencePoint(
        agent, market, 0, abm::ProspectReferencePointMode::RecentPeakWealth, 20, 120.0);
    abm::test::expect(peakWealthReference > 100.0,
                      "recent-peak-wealth mode should use a positive personal wealth scale",
                      failures);

    const double initialWealthReference = abm::strategy_detail::resolveProspectReferencePoint(
        agent, market, 0, abm::ProspectReferencePointMode::InitialWealth, 20, 120.0);
    abm::test::expect(abm::test::nearlyEqual(initialWealthReference, agent.getInitialWealth()),
                      "initial-wealth mode should use the agent's initial wealth", failures);
    abm::test::expect(
        abm::test::nearlyEqual(agent.getLastProspectReferencePoint(), initialWealthReference),
        "reference resolver should store the last selected CPT reference point on the agent",
        failures);
}

/*
 * Regression: the average-purchase anchor must come from the asset being
 * valued. It previously always read asset zero, so in a two-asset run the
 * behavioural reference for one market was the entry price of the other — while
 * the stop-loss and take-profit rules, evaluated for the same decision, used
 * the correct per-asset entry price.
 *
 * The two assets are given deliberately different entry prices so a regression
 * cannot pass by coincidence.
 */
void testProspectReferencePointIsPerAsset(int& failures) {
    abm::Market market;
    market.configureAssets({"alpha", "beta"});
    market.storeMarketValue(0, 100.0);
    market.storeMarketValue(1, 40.0);

    abm::Agent agent(1U, abm::AgentEndowment{10000.0, {0.0, 0.0}}, abm::ProspectTheory{}, true);
    agent.initializeWealth(std::vector<double>{100.0, 40.0});
    agent.recordExecutedTrade(0, abm::ExecutedTrade{abm::OrderType::BUY, 150.0, 2.0});
    agent.updateStock(0, 2.0);
    agent.recordExecutedTrade(1, abm::ExecutedTrade{abm::OrderType::BUY, 55.0, 3.0});
    agent.updateStock(1, 3.0);

    const double alphaReference = abm::strategy_detail::resolveProspectReferencePoint(
        agent, market, 0, abm::ProspectReferencePointMode::AveragePurchasePrice, 20, 100.0);
    const double betaReference = abm::strategy_detail::resolveProspectReferencePoint(
        agent, market, 1, abm::ProspectReferencePointMode::AveragePurchasePrice, 20, 40.0);

    abm::test::expect(abm::test::nearlyEqual(alphaReference, 150.0),
                      "average-purchase mode should anchor asset zero on its own entry price",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(betaReference, 55.0),
                      "average-purchase mode should anchor each asset on its own entry price, "
                      "not on asset zero's",
                      failures);
}

} // namespace

namespace abm::test {

void runProspectTheoryTests(int& failures) {
    testProspectReferencePointIsPerAsset(failures);
    testProspectTheoryPreferences(failures);
    testCumulativeProspectTheoryDecisionWeights(failures);
    testProspectTheoryScenarioCountIsConfigurable(failures);
    testProspectTheoryCanBeDisabled(failures);
    testProspectTheoryAgentFractionSelectsExactSeededSubset(failures);
    testProspectTheoryAgentFractionIncludesNoiseTraders(failures);
    testProspectTheoryHeterogeneityAssignsAgentSpecificParameters(failures);
    testProspectTheoryRejectsEvenScenarioCountInEnabledRuns(failures);
    testAgentTracksAverageEntryReferenceAcrossPositionChanges(failures);
    testProspectReferencePointResolutionModes(failures);
}

} // namespace abm::test
