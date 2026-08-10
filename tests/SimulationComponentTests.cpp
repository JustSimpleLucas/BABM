// SimulationComponentTests.cpp

#include "tests/TestSupport.h"

#include "Agent/Agent.h"
#include "AgentStrategy/FundamentalistStrategy.h"
#include "Market/FundamentalValueProcess.h"
#include "Market/Market.h"
#include "Metrics/AllocativeEfficiency.h"
#include "Metrics/StylisedFactMetrics.h"
#include "RiskManagement/ShortSaleRiskControls.h"
#include "Simulation/AgentActivationScheduler.h"
#include "Simulation/DiagnosticsRecorder.h"
#include "Simulation/MarketClearingEngine.h"
#include "Simulation/RiskControlService.h"
#include "Simulation/SimulationClock.h"
#include "Simulation/SocialInfluenceModel.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <utility>
#include <vector>

namespace {

abm::Order makeOrder(int orderId, int ownerAgentId, abm::OrderType side, abm::OrderStyle style,
                     double price, double quantity) {
    abm::Order order{};
    order.orderId = orderId;
    order.ownerAgentId = ownerAgentId;
    order.type = side;
    order.style = style;
    order.price = price;
    order.quantity = quantity;
    order.remainingQuantity = quantity;
    order.timeStep = 1;
    order.creationTimeStep = 1;
    order.expiryTimeStep = 5;
    return order;
}

abm::SimulationPopulation makePopulation(std::vector<abm::Agent> agents) {
    abm::SimulationPopulation population;
    population.records.reserve(agents.size());
    std::uint32_t maxAgentId = 0;
    for (const abm::Agent& agent : agents) {
        maxAgentId = std::max(maxAgentId, agent.getNumericalId());
        population.records.push_back(abm::AgentRecord{agent, "test_agent", nullptr});
    }

    population.agentsById.assign(static_cast<std::size_t>(maxAgentId) + 1, nullptr);
    for (abm::AgentRecord& record : population.records) {
        population.agentsById[record.agent.getNumericalId()] = &record.agent;
    }
    return population;
}

void testSimulationClockReportsProgress(int& failures) {
    abm::SimulationClock clock(3);
    std::vector<std::size_t> completedSteps;
    std::vector<std::size_t> totalSteps;

    for (std::size_t step = 1; step <= clock.totalSteps(); ++step) {
        clock.markStepCompleted(
            step, [&completedSteps, &totalSteps](std::size_t completed, std::size_t total) {
                completedSteps.push_back(completed);
                totalSteps.push_back(total);
            });
    }

    abm::test::expect(clock.completedSteps() == 3,
                      "simulation clock should track the completed step count", failures);
    abm::test::expect(completedSteps == std::vector<std::size_t>{1, 2, 3},
                      "simulation clock should report each completed step", failures);
    abm::test::expect(totalSteps == std::vector<std::size_t>{3, 3, 3},
                      "simulation clock should report a stable total step count", failures);
}

void testNonNegativeGiniCoefficientUsesBoundedWealthIndex(int& failures) {
    abm::test::expect(abm::test::nearlyEqual(
                          abm::calculateNonNegativeGiniCoefficient({100.0, 100.0, 100.0}), 0.0),
                      "equal non-negative wealth should have zero Gini coefficient", failures);

    abm::test::expect(
        abm::test::nearlyEqual(abm::calculateNonNegativeGiniCoefficient({0.0, 0.0, 100.0}),
                               2.0 / 3.0, 1e-12),
        "one wealthy agent among three should produce the expected concentration Gini", failures);

    abm::test::expect(
        abm::test::nearlyEqual(abm::calculateNonNegativeGiniCoefficient({-50.0, 0.0, 100.0}),
                               2.0 / 3.0, 1e-12),
        "negative wealth should be floored to zero before calculating Gini", failures);
}

/**
 * Builds the minimal per-asset payload a well-formed result carries.
 *
 * SimulationRunResult derives its primary-asset price histories from this, so a
 * fixture that omits it would have no histories to project.
 */
abm::MultiAssetRunData singleAssetRunData(const abm::SimulationConfig& config) {
    abm::MultiAssetRunData data;
    data.assetNames.push_back(config.assetName());
    data.marketPriceHistories.emplace_back();
    data.fundamentalPriceHistories.emplace_back();
    return data;
}

void testRunMetricsCalculatesFinalWealthGiniFromAgentSnapshots(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();

    std::vector<abm::AgentSnapshot> snapshots(3);
    snapshots[0].finalWealth = -50.0;
    snapshots[1].finalWealth = 0.0;
    snapshots[2].finalWealth = 100.0;

    const abm::SimulationRunResult result{
        config, abm::SimulationStats{}, {}, std::move(snapshots), {}, singleAssetRunData(config)};
    const abm::RunMetrics metrics = abm::calculateRunMetrics(result);

    abm::test::expect(abm::test::nearlyEqual(metrics.finalWealthGiniCoefficient, 2.0 / 3.0, 1e-12),
                      "run metrics should calculate final wealth Gini from final agent snapshots",
                      failures);
}

void testRunMetricsAveragesOnlyPositiveOpportunityEfficiencySteps(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    std::vector<abm::StepDetails> steps(3);
    steps[0].asset.maximumAllocativeSurplus = 10.0;
    steps[0].asset.allocativeEfficiency = 0.8;
    steps[1].asset.maximumAllocativeSurplus = 0.0;
    steps[1].asset.allocativeEfficiency = 0.0;
    steps[2].asset.maximumAllocativeSurplus = 5.0;
    steps[2].asset.allocativeEfficiency = 1.0;

    const abm::SimulationRunResult result{config, abm::SimulationStats{},    std::move(steps), {},
                                          {},     singleAssetRunData(config)};
    const abm::RunMetrics metrics = abm::calculateRunMetrics(result);

    abm::test::expect(metrics.allocativeEfficiencyObservations == 2 &&
                          abm::test::nearlyEqual(metrics.meanAllocativeEfficiency, 0.9),
                      "run metrics should average allocative efficiency only over "
                      "positive-surplus opportunity steps",
                      failures);
}

/**
 * Both markets are screened on identical terms, so a two-asset run must report
 * two independent verdicts rather than the primary asset's verdict twice.
 */
void testAssetRunMetricsScreenEachAssetIndependently(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();

    abm::MultiAssetRunData multiAsset;
    multiAsset.assetNames = {"alpha", "beta"};
    multiAsset.marketPriceHistories = {{100.0}, {40.0}};
    multiAsset.fundamentalPriceHistories = {{100.0}, {40.0}};

    /*
     * Alpha alternates sign so its lag-1 return autocorrelation is strongly
     * negative; beta repeats one value so its returns are constant. Screening
     * them together would smear both signals into one indeterminate verdict.
     */
    const std::vector<double> alphaReturns{0.02, -0.02, 0.02, -0.02};
    const std::vector<double> betaReturns{0.01, 0.01, 0.01, 0.01};
    for (std::size_t step = 0; step < alphaReturns.size(); ++step) {
        abm::AssetStepDetails alpha{};
        alpha.step = step + 1;
        alpha.assetIndex = 0;
        alpha.logReturn = alphaReturns[step];
        alpha.marketPrice = 100.0;
        alpha.tradedVolume = 2.0;
        multiAsset.assetStepDetails.push_back(alpha);

        abm::AssetStepDetails beta{};
        beta.step = step + 1;
        beta.assetIndex = 1;
        beta.logReturn = betaReturns[step];
        beta.marketPrice = 40.0;
        beta.tradedVolume = 6.0;
        multiAsset.assetStepDetails.push_back(beta);
    }

    const abm::SimulationRunResult result{config, abm::SimulationStats{}, {}, {},
                                          {},     std::move(multiAsset)};
    const std::vector<abm::AssetRunMetrics> assetMetrics = abm::calculateAssetRunMetrics(result);

    abm::test::expect(assetMetrics.size() == 2 && assetMetrics[0].assetName == "alpha" &&
                          assetMetrics[1].assetName == "beta",
                      "asset run metrics should report one record per asset in declared order",
                      failures);
    if (assetMetrics.size() != 2) {
        return;
    }

    abm::test::expect(assetMetrics[0].metrics.observationCount == alphaReturns.size() &&
                          assetMetrics[1].metrics.observationCount == betaReturns.size(),
                      "each asset's metrics should count only that asset's return observations",
                      failures);
    abm::test::expect(assetMetrics[0].metrics.lag1ReturnAutocorrelation < -0.5,
                      "an alternating return series should screen as autocorrelated", failures);
    abm::test::expect(abm::test::nearlyEqual(assetMetrics[1].metrics.logReturnStdDev, 0.0, 1e-12),
                      "a constant return series should screen as having zero return dispersion",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(assetMetrics[0].metrics.meanTradedVolume, 2.0) &&
                          abm::test::nearlyEqual(assetMetrics[1].metrics.meanTradedVolume, 6.0),
                      "traded volume should be averaged within each asset", failures);
}

void testAllocativeEfficiencyMaximumSurplusUsesSortedSchedules(int& failures) {
    const std::vector<abm::AllocativeEfficiencyOrder> orders{
        {abm::OrderType::BUY, 105.0, 1.0},
        {abm::OrderType::BUY, 103.0, 2.0},
        {abm::OrderType::SELL, 99.0, 2.0},
        {abm::OrderType::SELL, 101.0, 2.0},
    };

    const double maximumSurplus = abm::calculateMaximumAllocativeSurplus(orders);

    abm::test::expect(abm::test::nearlyEqual(maximumSurplus, 12.0),
                      "allocative-efficiency benchmark should match highest-value buyers with "
                      "lowest-cost sellers",
                      failures);
}

void testAllocativeEfficiencyZeroWhenNoPositiveSurplusExists(int& failures) {
    const std::vector<abm::AllocativeEfficiencyOrder> orders{
        {abm::OrderType::BUY, 99.0, 4.0},
        {abm::OrderType::SELL, 100.0, 4.0},
    };

    const abm::AllocativeEfficiencyResult result = abm::calculateAllocativeEfficiency(orders, {});

    abm::test::expect(abm::test::nearlyEqual(result.maximumSurplus, 0.0) &&
                          abm::test::nearlyEqual(result.efficiency, 0.0),
                      "allocative efficiency should report zero when no positive-surplus "
                      "double-auction allocation exists",
                      failures);
}

void testAllocativeEfficiencyRealizedSurplusUsesExecutedReservations(int& failures) {
    const std::vector<abm::AllocativeEfficiencyTrade> trades{
        {105.0, 99.0, 2.0},
        {102.0, 100.0, 1.5},
    };

    const double realizedSurplus = abm::calculateRealizedAllocativeSurplus(trades);

    abm::test::expect(abm::test::nearlyEqual(realizedSurplus, 15.0),
                      "realized allocative surplus should sum executed buyer-seller reservation "
                      "price gaps times filled quantity",
                      failures);
}

void testActivationSchedulerIsSeedReproducible(int& failures) {
    abm::AgentActivationScheduler firstScheduler;
    abm::AgentActivationScheduler secondScheduler;
    abm::RandomEngine firstRandom(123U);
    abm::RandomEngine secondRandom(123U);

    const std::vector<std::size_t> firstActive =
        firstScheduler.schedule(abm::AgentActivationRequest{8, 1.0}, firstRandom);
    const std::vector<std::size_t> secondActive =
        secondScheduler.schedule(abm::AgentActivationRequest{8, 1.0}, secondRandom);

    abm::test::expect(firstActive == secondActive,
                      "activation scheduler should be reproducible for a fixed seed", failures);
    abm::test::expect(firstActive.size() == 8,
                      "unit activity rate should schedule every agent after shuffling", failures);

    abm::RandomEngine zeroActivityRandom(123U);
    abm::AgentActivationScheduler zeroActivityScheduler;
    const std::vector<std::size_t> inactive =
        zeroActivityScheduler.schedule(abm::AgentActivationRequest{8, 0.0}, zeroActivityRandom);
    abm::test::expect(inactive.empty(), "zero activity rate should schedule no active agents",
                      failures);
}

void testSocialInfluenceModelUpdatesAndRespectsDisabledBaseline(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.social.enabled = true;
    config.social.interactionRadius = 2.0;
    config.social.gammaMin = 1.0;
    config.social.gammaMax = 1.0;
    config.social.privateSignalStdMin = 0.0;
    config.social.privateSignalStdMax = 0.0;

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{1000.0, {1.0}}),
                        abm::Agent(2U, abm::AgentEndowment{1000.0, {1.0}})});
    abm::RandomEngine random(99U);
    abm::SocialInfluenceModel socialModel;
    socialModel.initialize(population, config.social, random);
    socialModel.prepareForRun(population);

    population.agentsById[1]->setOpinions(1.0, 1.0);
    population.agentsById[2]->setOpinions(-1.0, -1.0);
    socialModel.updateOpinions(population, config.social, random);

    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getCurrentOpinion(), -1.0),
                      "connected social agents should adopt the neighbour signal when gamma is one",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[2]->getCurrentOpinion(), 1.0),
                      "social influence should use lagged neighbour opinions symmetrically",
                      failures);

    config.social.enabled = false;
    population.agentsById[1]->setOpinions(0.5, 0.5);
    socialModel.updateOpinions(population, config.social, random);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getCurrentOpinion(), 0.5),
                      "disabled social influence should leave opinions unchanged", failures);
}

void testSocialInfluenceSpatialHashMatchesRadiusOracle(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.social.enabled = true;
    config.social.spaceWidth = 1.0;
    config.social.spaceHeight = 1.0;
    config.social.interactionRadius = 0.08;
    config.social.gammaMin = 1.0;
    config.social.gammaMax = 1.0;
    config.social.privateSignalStdMin = 0.0;
    config.social.privateSignalStdMax = 0.0;

    std::vector<abm::Agent> agents;
    agents.reserve(64);
    for (std::uint32_t agentId = 1; agentId <= 64; ++agentId) {
        agents.emplace_back(agentId, abm::AgentEndowment{1000.0, {1.0}});
    }

    abm::SimulationPopulation population = makePopulation(std::move(agents));
    abm::RandomEngine random(20260519U);
    abm::SocialInfluenceModel socialModel;
    socialModel.initialize(population, config.social, random);
    socialModel.prepareForRun(population);

    std::vector<double> previousOpinions(population.agentsById.size(), 0.0);
    for (std::size_t agentId = 1; agentId < population.agentsById.size(); ++agentId) {
        previousOpinions[agentId] = static_cast<double>(static_cast<int>(agentId % 9U) - 4);
        population.agentsById[agentId]->setOpinions(previousOpinions[agentId],
                                                    previousOpinions[agentId]);
    }

    std::vector<double> expectedOpinions(population.agentsById.size(), 0.0);
    std::size_t connectedAgents = 0;
    std::size_t isolatedAgents = 0;
    for (std::size_t lhsId = 1; lhsId < population.agentsById.size(); ++lhsId) {
        const abm::Agent* lhs = population.agentsById[lhsId];
        double weightedOpinionSum = 0.0;
        double totalWeight = 0.0;
        for (std::size_t rhsId = 1; rhsId < population.agentsById.size(); ++rhsId) {
            if (lhsId == rhsId) {
                continue;
            }

            const abm::Agent* rhs = population.agentsById[rhsId];
            const double distance = std::hypot(lhs->getXCoordinate() - rhs->getXCoordinate(),
                                               lhs->getYCoordinate() - rhs->getYCoordinate());
            if (distance > config.social.interactionRadius) {
                continue;
            }

            const double weight = 1.0 / (1.0 + distance);
            weightedOpinionSum += weight * previousOpinions[rhsId];
            totalWeight += weight;
        }

        if (totalWeight > 0.0) {
            expectedOpinions[lhsId] = weightedOpinionSum / totalWeight;
            ++connectedAgents;
        } else {
            ++isolatedAgents;
        }
    }

    abm::test::expect(connectedAgents > 0 && isolatedAgents > 0,
                      "spatial social test should include both connected and isolated agents",
                      failures);

    socialModel.updateOpinions(population, config.social, random);
    for (std::size_t agentId = 1; agentId < population.agentsById.size(); ++agentId) {
        abm::test::expect(
            abm::test::nearlyEqual(population.agentsById[agentId]->getCurrentOpinion(),
                                   expectedOpinions[agentId], 1e-12),
            "spatial hash social opinions should match the radius-search oracle", failures);
    }
}

void testRiskControlServiceForcedBuyIn(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = true;
    config.shortSale.initialMarginRequirement = 0.50;
    config.shortSale.maintenanceMarginRequirement = 0.30;
    abm::test::soleAsset(config).initialStock = -20.0;

    abm::Agent shortSeller(1U, abm::AgentEndowment{3000.0, {-20.0}});
    shortSeller.initializeWealth(std::vector<double>{140.0});
    abm::SimulationPopulation population = makePopulation({shortSeller});

    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    const abm::ForcedBuyInResult forcedBuyIns = riskControls.enforceMaintenanceMargin(
        140.0, 4, config, population.agentsById, ledger, nextTradeId, true);

    abm::test::expect(abm::test::nearlyEqual(forcedBuyIns.volume, 17.142857142857142, 1e-9),
                      "risk controls should calculate the forced cover quantity", failures);
    abm::test::expect(ledger.size() == 1 && nextTradeId == 2,
                      "forced buy-ins should write one external trade-ledger row", failures);
    abm::test::expect(
        abm::test::nearlyEqual(riskControls.aggregateShortInterest(), 2.857142857142858, 1e-9),
        "risk controls should update cached aggregate short interest after buy-in", failures);
}

void testForcedBuyInAppliesTransactionCostsWhenEnabled(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = true;
    config.shortSale.initialMarginRequirement = 0.50;
    config.shortSale.maintenanceMarginRequirement = 0.30;
    config.transactionCosts.rate = 0.01;
    config.transactionCosts.applyToForcedBuyIns = true;
    abm::test::soleAsset(config).initialStock = -20.0;

    abm::Agent shortSeller(1U, abm::AgentEndowment{3000.0, {-20.0}});
    shortSeller.initializeWealth(std::vector<double>{140.0});
    abm::SimulationPopulation population = makePopulation({shortSeller});

    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    const abm::ForcedBuyInResult forcedBuyIns = riskControls.enforceMaintenanceMargin(
        140.0, 4, config, population.agentsById, ledger, nextTradeId, true);

    abm::test::expect(abm::test::nearlyEqual(forcedBuyIns.transactionCosts, 24.0, 1e-9),
                      "forced buy-ins should report proportional transaction costs", failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getCash(), 576.0, 1e-9),
                      "forced buy-ins should debit notional plus transaction cost from cash",
                      failures);
    abm::test::expect(ledger.size() == 1 &&
                          abm::test::nearlyEqual(ledger.front().transactionCost, 24.0) &&
                          abm::test::nearlyEqual(ledger.front().netCashFlow, -2424.0),
                      "forced buy-in ledger rows should expose fee and net cash flow", failures);
}

void testRiskControlServicePerAssetShortInterestAndBuyIn(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = true;
    config.shortSale.initialMarginRequirement = 0.50;
    config.shortSale.maintenanceMarginRequirement = 0.30;
    config.assets.declare(
        {abm::test::makeAssetDefinition("alpha", 100.0, 0.0, 0.01, 0.01, 0.0, 1e-6),
         abm::test::makeAssetDefinition("beta", 140.0, -20.0, 0.01, 0.01, 0.0, 1e-6)});

    abm::Agent shortSeller(1U, abm::AgentEndowment{3000.0, {0.0, -20.0}});
    shortSeller.initializeWealth(std::vector<double>{100.0, 140.0});
    abm::SimulationPopulation population = makePopulation({shortSeller});

    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    abm::test::expect(abm::test::nearlyEqual(riskControls.aggregateShortInterest(0), 0.0) &&
                          abm::test::nearlyEqual(riskControls.aggregateShortInterest(1), 20.0),
                      "risk controls should track short interest per asset", failures);

    const abm::ForcedBuyInResult forcedBuyIns =
        riskControls.enforceMaintenanceMargin(std::vector<double>{100.0, 140.0}, 4, config,
                                              population.agentsById, ledger, nextTradeId, true);

    abm::test::expect(
        abm::test::nearlyEqual(forcedBuyIns.volume, 17.142857142857142, 1e-9) &&
            abm::test::nearlyEqual(forcedBuyIns.volumeByAsset[0], 0.0) &&
            abm::test::nearlyEqual(forcedBuyIns.volumeByAsset[1], 17.142857142857142, 1e-9),
        "forced buy-in should cover only the shorted asset", failures);
    abm::test::expect(
        abm::test::nearlyEqual(riskControls.aggregateShortInterest(1), 2.857142857142858, 1e-9) &&
            abm::test::nearlyEqual(riskControls.aggregateShortInterest(0), 0.0),
        "per-asset short interest should update after the buy-in", failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getStock(0), 0.0) &&
                          population.agentsById[1]->getStock(1) > -3.0,
                      "the buy-in should adjust only the shorted asset's inventory", failures);
    abm::test::expect(ledger.size() == 1 && ledger.front().asset == "beta",
                      "the forced buy-in ledger row should carry the shorted asset's name",
                      failures);
}

void testMarketClearingEngineIsolatesAssetBooks(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = false;
    config.assets.declare(
        {abm::test::makeAssetDefinition("alpha", 100.0, 5.0, 0.01, 0.01, 0.0, 1e-6),
         abm::test::makeAssetDefinition("beta", 50.0, 5.0, 0.01, 0.01, 0.0, 1e-6)});

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{1000.0, {0.0, 0.0}}),
                        abm::Agent(2U, abm::AgentEndowment{0.0, {5.0, 5.0}})});
    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    abm::MarketClearingEngine clearingEngine;
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    /*
     * A resting ask on asset 0 must not match a crossing buy on asset 1, even
     * at prices that would cross inside one book.
     */
    abm::Order restingAsk =
        makeOrder(1, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 40.0, 2.0);
    restingAsk.assetIndex = 0;
    abm::Order crossAssetBuy =
        makeOrder(2, 1, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 60.0, 2.0);
    crossAssetBuy.assetIndex = 1;
    const std::vector<abm::Order> orders{restingAsk, crossAssetBuy};

    const std::vector<double> referencePrices{100.0, 50.0};
    const std::vector<abm::MicrostructureStepResult> results =
        clearingEngine.executeOrders(abm::OrderExecutionRequest{&orders,
                                                                &referencePrices,
                                                                {},
                                                                &config,
                                                                &population.agentsById,
                                                                &riskControls,
                                                                &ledger,
                                                                &nextTradeId,
                                                                true});

    abm::test::expect(results.size() == 2, "clearing should report one result per asset", failures);
    abm::test::expect(results[0].executedTrades == 0 && results[1].executedTrades == 0,
                      "orders on different assets must never match each other", failures);
    abm::test::expect(results[0].bookMetrics.restingAskOrders == 1 &&
                          results[1].bookMetrics.restingBidOrders == 1,
                      "each order should rest in its own asset's book", failures);

    /*
     * A same-asset buy must still match the resting ask, updating only that
     * asset's inventory.
     */
    abm::Order sameAssetBuy =
        makeOrder(3, 1, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 2.0);
    sameAssetBuy.assetIndex = 0;
    const std::vector<abm::Order> followUpOrders{sameAssetBuy};
    const std::vector<abm::MicrostructureStepResult> followUpResults =
        clearingEngine.executeOrders(abm::OrderExecutionRequest{&followUpOrders,
                                                                &referencePrices,
                                                                {},
                                                                &config,
                                                                &population.agentsById,
                                                                &riskControls,
                                                                &ledger,
                                                                &nextTradeId,
                                                                true});

    abm::test::expect(followUpResults[0].executedTrades == 1 &&
                          abm::test::nearlyEqual(followUpResults[0].tradedVolume, 2.0),
                      "a same-asset buy should match the resting ask", failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getStock(0), 2.0) &&
                          abm::test::nearlyEqual(population.agentsById[1]->getStock(1), 0.0) &&
                          abm::test::nearlyEqual(population.agentsById[2]->getStock(0), 3.0) &&
                          abm::test::nearlyEqual(population.agentsById[2]->getStock(1), 5.0),
                      "execution should move inventory only in the traded asset", failures);
    abm::test::expect(!ledger.empty() && ledger.back().asset == "alpha",
                      "ledger rows should carry the traded asset's name", failures);
}

void testMarketClearingEngineExecutesConstrainedTrade(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = false;
    abm::test::soleAsset(config).name = "clearing_asset";

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{1000.0, {0.0}}),
                        abm::Agent(2U, abm::AgentEndowment{0.0, {5.0}})});
    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    abm::MarketClearingEngine clearingEngine;
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    const std::vector<abm::Order> orders{
        makeOrder(1, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 2.0),
        makeOrder(2, 1, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 2.0)};
    const std::vector<double> referencePrices{100.0};
    const abm::MicrostructureStepResult result =
        clearingEngine
            .executeOrders(abm::OrderExecutionRequest{&orders,
                                                      &referencePrices,
                                                      {},
                                                      &config,
                                                      &population.agentsById,
                                                      &riskControls,
                                                      &ledger,
                                                      &nextTradeId,
                                                      true})
            .front();

    abm::test::expect(abm::test::nearlyEqual(result.tradedVolume, 2.0),
                      "clearing engine should execute the crossing buy and sell orders", failures);
    abm::test::expect(result.executedTrades == 1 && ledger.size() == 2,
                      "clearing engine should record one execution from both agent viewpoints",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getCash(), 800.0) &&
                          abm::test::nearlyEqual(population.agentsById[1]->getStock(0), 2.0),
                      "clearing engine should update buyer cash and inventory", failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[2]->getCash(), 200.0) &&
                          abm::test::nearlyEqual(population.agentsById[2]->getStock(0), 3.0),
                      "clearing engine should update seller cash and inventory", failures);
}

void testMarketClearingEngineAppliesTransactionCosts(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = false;
    abm::test::soleAsset(config).name = "cost_asset";
    config.transactionCosts.rate = 0.01;

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{1000.0, {0.0}}),
                        abm::Agent(2U, abm::AgentEndowment{0.0, {5.0}})});
    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    abm::MarketClearingEngine clearingEngine;
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    const std::vector<abm::Order> orders{
        makeOrder(1, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 2.0),
        makeOrder(2, 1, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 2.0)};
    const std::vector<double> referencePrices{100.0};
    const abm::MicrostructureStepResult result =
        clearingEngine
            .executeOrders(abm::OrderExecutionRequest{&orders,
                                                      &referencePrices,
                                                      {},
                                                      &config,
                                                      &population.agentsById,
                                                      &riskControls,
                                                      &ledger,
                                                      &nextTradeId,
                                                      true})
            .front();

    abm::test::expect(abm::test::nearlyEqual(result.totalTransactionCosts, 4.0),
                      "clearing engine should report costs paid by both trade sides", failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getCash(), 798.0) &&
                          abm::test::nearlyEqual(population.agentsById[2]->getCash(), 198.0),
                      "transaction costs should reduce both buyer and seller cash", failures);
    abm::test::expect(abm::test::nearlyEqual(
                          population.agentsById[1]->getCumulativeTransactionCostsPaid(), 2.0) &&
                          abm::test::nearlyEqual(
                              population.agentsById[2]->getCumulativeTransactionCostsPaid(), 2.0),
                      "agents should accumulate paid transaction costs", failures);
    abm::test::expect(
        ledger.size() == 2 && abm::test::nearlyEqual(ledger.front().grossNotional, 200.0) &&
            abm::test::nearlyEqual(ledger.front().transactionCost, 2.0) &&
            abm::test::nearlyEqual(ledger.front().netCashFlow, -202.0) &&
            abm::test::nearlyEqual(ledger.back().netCashFlow, 198.0),
        "trade ledger should expose gross notional, fee, and net cash flow", failures);
}

void testMarketClearingEngineCostAwareAffordability(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = false;
    config.transactionCosts.rate = 0.01;

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{101.0, {0.0}}),
                        abm::Agent(2U, abm::AgentEndowment{0.0, {5.0}})});
    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    abm::MarketClearingEngine clearingEngine;
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    const std::vector<abm::Order> orders{
        makeOrder(1, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 2.0),
        makeOrder(2, 1, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 2.0)};
    const std::vector<double> referencePrices{100.0};
    const abm::MicrostructureStepResult result =
        clearingEngine
            .executeOrders(abm::OrderExecutionRequest{&orders,
                                                      &referencePrices,
                                                      {},
                                                      &config,
                                                      &population.agentsById,
                                                      &riskControls,
                                                      &ledger,
                                                      &nextTradeId,
                                                      true})
            .front();

    abm::test::expect(abm::test::nearlyEqual(result.tradedVolume, 1.0),
                      "transaction-cost affordability should clip buyer fill quantity", failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getCash(), 0.0),
                      "cost-aware clipped fill should not create negative buyer cash", failures);
}

void testMarketClearingEngineReportsAllocativeEfficiency(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = false;
    abm::test::soleAsset(config).name = "efficiency_asset";

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{1000.0, {0.0}}),
                        abm::Agent(2U, abm::AgentEndowment{0.0, {5.0}})});
    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    abm::MarketClearingEngine clearingEngine;
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    const std::vector<abm::Order> orders{
        makeOrder(1, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 98.0, 2.0),
        makeOrder(2, 1, abm::OrderType::BUY, abm::OrderStyle::MARKET, 105.0, 2.0)};
    const std::vector<double> referencePrices{100.0};
    const abm::MicrostructureStepResult result =
        clearingEngine
            .executeOrders(abm::OrderExecutionRequest{&orders,
                                                      &referencePrices,
                                                      {},
                                                      &config,
                                                      &population.agentsById,
                                                      &riskControls,
                                                      &ledger,
                                                      &nextTradeId,
                                                      true})
            .front();

    abm::test::expect(abm::test::nearlyEqual(result.realizedAllocativeSurplus, 14.0) &&
                          abm::test::nearlyEqual(result.maximumAllocativeSurplus, 14.0) &&
                          abm::test::nearlyEqual(result.allocativeEfficiency, 1.0),
                      "clearing engine should report Smith-style gross allocative efficiency "
                      "from executed reservation-price surplus",
                      failures);
}

void testMarketClearingEnginePreventsSelfTrade(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = false;
    abm::test::soleAsset(config).name = "self_trade_asset";

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{1000.0, {5.0}})});
    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    abm::MarketClearingEngine clearingEngine;
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    const std::vector<abm::Order> orders{
        makeOrder(1, 1, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 2.0),
        makeOrder(2, 1, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 2.0)};
    const std::vector<double> referencePrices{100.0};
    const abm::MicrostructureStepResult result =
        clearingEngine
            .executeOrders(abm::OrderExecutionRequest{&orders,
                                                      &referencePrices,
                                                      {},
                                                      &config,
                                                      &population.agentsById,
                                                      &riskControls,
                                                      &ledger,
                                                      &nextTradeId,
                                                      true})
            .front();

    abm::test::expect(result.selfTradePreventions == 1,
                      "clearing engine should cancel the agent's own resting quote", failures);
    abm::test::expect(result.executedTrades == 0 &&
                          abm::test::nearlyEqual(result.tradedVolume, 0.0),
                      "self-trade prevention should stop the agent trading with itself", failures);
    abm::test::expect(abm::test::nearlyEqual(population.agentsById[1]->getCash(), 1000.0) &&
                          abm::test::nearlyEqual(population.agentsById[1]->getStock(0), 5.0),
                      "self-trade prevention should leave the agent balance sheet unchanged",
                      failures);
    abm::test::expect(result.bookMetrics.restingAskOrders == 0,
                      "cancel-resting self-trade prevention should remove the own ask", failures);
}

void testMarketClearingEngineMarketOrderPriceCollar(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = false;
    abm::test::soleAsset(config).name = "collar_asset";
    config.microstructure.marketOrderPriceCollar = 0.05;

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{1000.0, {0.0}}),
                        abm::Agent(2U, abm::AgentEndowment{0.0, {5.0}})});
    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    abm::MarketClearingEngine clearingEngine;
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    const std::vector<abm::Order> orders{
        makeOrder(1, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 120.0, 2.0),
        makeOrder(2, 1, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 2.0)};
    const std::vector<double> referencePrices{100.0};
    const abm::MicrostructureStepResult result =
        clearingEngine
            .executeOrders(abm::OrderExecutionRequest{&orders,
                                                      &referencePrices,
                                                      {},
                                                      &config,
                                                      &population.agentsById,
                                                      &riskControls,
                                                      &ledger,
                                                      &nextTradeId,
                                                      true})
            .front();

    abm::test::expect(result.collarRejectedOrders == 1,
                      "market order should be rejected when execution breaches the price collar",
                      failures);
    abm::test::expect(result.executedTrades == 0 &&
                          abm::test::nearlyEqual(population.agentsById[2]->getStock(0), 5.0),
                      "collar rejection should leave the resting side untouched", failures);
}

void testMarketClearingEngineSplitsCancellationCounters(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.shortSellingEnabled = false;
    abm::test::soleAsset(config).name = "counter_asset";

    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{10000.0, {0.0}}),
                        abm::Agent(2U, abm::AgentEndowment{0.0, {3.0}})});
    abm::RiskControlService riskControls;
    riskControls.reset(population, config);
    abm::MarketClearingEngine clearingEngine;
    std::vector<abm::ExternalTradeLedgerRecord> ledger;
    std::size_t nextTradeId = 1;

    /*
     * The seller rests two 3-unit asks backed by only 3 shares. The market buy
     * fills the first ask fully; the second ask is then inventory-infeasible
     * and must be removed as a resting-side cancellation.
     */
    const std::vector<abm::Order> orders{
        makeOrder(1, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 3.0),
        makeOrder(2, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 101.0, 3.0),
        makeOrder(3, 1, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 6.0)};
    const std::vector<double> referencePrices{100.0};
    const abm::MicrostructureStepResult result =
        clearingEngine
            .executeOrders(abm::OrderExecutionRequest{
                &orders, &referencePrices, std::vector<abm::RestingOrderLifecycleCounts>{{2, 1}},
                &config, &population.agentsById, &riskControls, &ledger, &nextTradeId, true})
            .front();

    abm::test::expect(result.executedTrades == 1 &&
                          abm::test::nearlyEqual(result.tradedVolume, 3.0),
                      "buyer should fill the feasible resting ask only", failures);
    abm::test::expect(result.staleCancelledOrders == 1,
                      "stale lifecycle cancellations should be reported separately", failures);
    abm::test::expect(result.infeasibleRestingCancellations == 1,
                      "inventory-infeasible resting ask should be counted as a resting-side "
                      "cancellation",
                      failures);
    abm::test::expect(result.cancelledOrders == 2,
                      "legacy cancelled-order aggregate should remain stale plus resting-side "
                      "cancellations",
                      failures);
    abm::test::expect(result.expiredOrders == 2 && result.infeasibleIncomingCancellations == 0 &&
                          result.selfTradePreventions == 0 && result.collarRejectedOrders == 0,
                      "unrelated lifecycle and matching counters should stay untouched", failures);
}

void testFundamentalistRiskThresholdDefaultsAgree(int& failures) {
    const abm::FundamentalistRiskThresholds thresholds{};
    abm::test::expect(abm::test::nearlyEqual(thresholds.stopLossThreshold, 0.05) &&
                          abm::test::nearlyEqual(thresholds.takeProfitThreshold, 0.10),
                      "default fundamentalist risk thresholds should match the config defaults",
                      failures);
}

void testFundamentalistTransactionCostHurdleSuppressesWeakMispricing(int& failures) {
    abm::Market market;
    market.configureAssets({"cost_asset"});
    market.storeMarketValue(0, 100.0);
    market.storeMarketValue(0, 100.0);
    market.storeTrueValue(0, 100.5);

    abm::Agent agent(1U, abm::AgentEndowment{1000.0, {0.0}}, abm::ProspectTheory{}, false);
    abm::FundamentalistStrategyParameters parameters;
    parameters.assetIndex = 0;
    parameters.mispricingThreshold = 0.0;
    parameters.allocationLine = abm::AssetAllocationLine(3.0, 0.0, 1.0);
    parameters.volatilityWindow = 1;
    abm::FundamentalistStrategy strategy(parameters);

    abm::TradingOrderContext noCostContext;
    noCostContext.priceTickSize = 0.01;
    noCostContext.transactionCostAffectsDecisions = false;
    const std::optional<abm::Order> noCostOrder =
        strategy.generateOrder(agent, market, 1, noCostContext);

    abm::TradingOrderContext costContext = noCostContext;
    costContext.transactionCostAffectsDecisions = true;
    costContext.transactionCostRate = 0.01;
    const std::optional<abm::Order> costAwareOrder =
        strategy.generateOrder(agent, market, 1, costContext);

    abm::test::expect(noCostOrder.has_value(),
                      "weak fundamental mispricing should trade before applying cost hurdle",
                      failures);
    abm::test::expect(!costAwareOrder.has_value(),
                      "transaction-cost hurdle should suppress weak fundamental mispricing",
                      failures);
}

void testDiagnosticsRecorderBuildsStepAndRunOutput(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    abm::test::soleAsset(config).name = "diagnostic_asset";
    config.timeSteps = 2;
    config.initialCash = 1000.0;

    abm::Market market;
    market.configureAssets({config.assetName()});
    market.storeMarketValue(0, 100.0);
    market.storeTrueValue(0, 100.0);

    abm::DiagnosticsRecorder recorder;
    recorder.resetForRun(config, 2, market, false);
    abm::SimulationPopulation population =
        makePopulation({abm::Agent(1U, abm::AgentEndowment{1000.0, {1.0}}),
                        abm::Agent(2U, abm::AgentEndowment{1000.0, {1.0}})});
    for (abm::AgentRecord& record : population.records) {
        record.agent.initializeWealth(std::vector<double>{100.0});
    }

    abm::MicrostructureStepResult microstructure{};
    microstructure.netDemand = 2.0;
    microstructure.tradedVolume = 1.0;
    microstructure.lastTradePrice = 101.0;
    microstructure.submittedLimitOrders = 1;
    microstructure.executedTrades = 1;
    microstructure.totalTransactionCosts = 3.5;
    microstructure.realizedAllocativeSurplus = 7.0;
    microstructure.maximumAllocativeSurplus = 10.0;
    microstructure.allocativeEfficiency = 0.7;
    microstructure.bookMetrics.bestBid = 99.0;
    microstructure.bookMetrics.bestAsk = 102.0;

    const abm::PriceFormationResult priceResult{101.0, 0.01, std::log(1.01)};
    recorder.recordStep(abm::StepRecordingRequest{1, &config, 2, 100.0, 100.5, 1, &microstructure,
                                                  &priceResult, &population});
    recorder.completeRun(population);

    const abm::SimulationRunResult result = recorder.buildResult(config, market);
    abm::test::expect(result.stepDetails().size() == 1,
                      "diagnostics recorder should expose the recorded step row", failures);
    abm::test::expect(abm::test::nearlyEqual(result.stepDetails().front().normalizedImbalance, 0.1),
                      "diagnostics recorder should normalise notional imbalance by starting cash",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(result.stats().finalMarketPrice, 101.0),
                      "diagnostics recorder should update final market price", failures);
    abm::test::expect(
        abm::test::nearlyEqual(result.stepDetails().front().asset.totalTransactionCosts, 3.5) &&
            abm::test::nearlyEqual(result.stats().totalTransactionCosts, 3.5),
        "diagnostics recorder should export transaction-cost totals", failures);
    abm::test::expect(
        abm::test::nearlyEqual(result.stepDetails().front().wealthGiniCoefficient, 0.0),
        "diagnostics recorder should export wealth Gini from population state", failures);
    abm::test::expect(
        abm::test::nearlyEqual(result.stepDetails().front().asset.realizedAllocativeSurplus, 7.0) &&
            abm::test::nearlyEqual(result.stepDetails().front().asset.maximumAllocativeSurplus,
                                   10.0) &&
            abm::test::nearlyEqual(result.stepDetails().front().asset.allocativeEfficiency, 0.7),
        "diagnostics recorder should export double-auction allocative-efficiency diagnostics",
        failures);
    abm::test::expect(result.agentSnapshots().size() == 2,
                      "diagnostics recorder should export final agent snapshots", failures);
}

} // namespace

namespace abm::test {

/**
 * The correlated multi-asset draw must reproduce the legacy independent draw
 * exactly for a single asset.
 *
 * This is the property the frozen single-asset baseline hash depends on: the
 * joint path draws Normal(0, 1) and scales by sigma, whereas the legacy path
 * drew Normal(0, sigma) directly. If the toolchain ever stopped scaling a
 * normal draw exactly, every archived single-asset baseline would silently
 * drift, so the equivalence is pinned here rather than assumed.
 */
void testCorrelatedFundamentalMatchesLegacySingleAssetDraw(int& failures) {
    abm::FundamentalValueProcessParameters parameters;
    parameters.driftPerStep = 0.02;
    parameters.shockStdDev = 0.03;
    parameters.minimumValue = 1.0;

    abm::Market legacyMarket;
    abm::FundamentalValueProcess legacyProcess(4242U);
    legacyMarket.configureAssets({"alpha"});
    legacyMarket.storeTrueValue(0, 100.0);
    abm::Market jointMarket;
    abm::FundamentalValueProcess jointProcess(4242U);
    jointMarket.configureAssets({"alpha"});
    jointMarket.storeTrueValue(0, 100.0);

    for (int step = 0; step < 64; ++step) {
        const double legacyValue =
            legacyProcess.generateFundamentalValue(legacyMarket, 0, parameters);
        const std::vector<double> jointValues =
            jointProcess.generateCorrelatedFundamentalValues(jointMarket, {parameters}, 0.0);
        abm::test::expect(jointValues.size() == 1U, "Single-asset joint draw returns one value",
                          failures);
        abm::test::expect(legacyValue == jointValues.front(),
                          "Correlated single-asset draw is bit-identical to the legacy draw",
                          failures);
    }
}

/**
 * Zero correlation must leave the draws untouched, and the two assets must
 * receive different innovations drawn in declared index order.
 */
void testIndependentFundamentalsDifferAcrossAssets(int& failures) {
    abm::FundamentalValueProcessParameters parameters;
    parameters.driftPerStep = 0.0;
    parameters.shockStdDev = 0.05;
    parameters.minimumValue = 1.0;

    abm::Market market;
    abm::FundamentalValueProcess fundamentalProcess(99U);
    market.configureAssets({"alpha", "beta"});
    market.storeTrueValue(0, 100.0);
    market.storeTrueValue(1, 100.0);

    bool sawDifference = false;
    for (int step = 0; step < 32; ++step) {
        const std::vector<double> values = fundamentalProcess.generateCorrelatedFundamentalValues(
            market, {parameters, parameters}, 0.0);
        if (values.at(0) != values.at(1)) {
            sawDifference = true;
        }
    }
    abm::test::expect(sawDifference, "Uncorrelated assets receive distinct fundamental innovations",
                      failures);
}

/**
 * Correlated innovations must reproduce the requested correlation.
 *
 * The test compares realised log-increment correlation against the target for
 * a strongly positive and a strongly negative rho, using a tolerance wide
 * enough for sampling error at this sample size but far tighter than the gap
 * between the two cases.
 */
void testCorrelatedFundamentalsReproduceRequestedCorrelation(int& failures) {
    const int sampleCount = 4000;
    const double targets[] = {0.9, -0.9, 0.0};

    for (const double target : targets) {
        abm::FundamentalValueProcessParameters parameters;
        parameters.driftPerStep = 0.0;
        parameters.shockStdDev = 1.0;
        parameters.minimumValue = 1e-12;

        abm::Market market;
        abm::FundamentalValueProcess fundamentalProcess(20260807U);
        market.configureAssets({"alpha", "beta"});
        market.storeTrueValue(0, 0.0);
        market.storeTrueValue(1, 0.0);

        std::vector<double> alphaIncrements;
        std::vector<double> betaIncrements;
        alphaIncrements.reserve(sampleCount);
        betaIncrements.reserve(sampleCount);
        double previousAlpha = 0.0;
        double previousBeta = 0.0;
        for (int sample = 0; sample < sampleCount; ++sample) {
            const std::vector<double> values =
                fundamentalProcess.generateCorrelatedFundamentalValues(
                    market, {parameters, parameters}, target);
            alphaIncrements.push_back(values.at(0) - previousAlpha);
            betaIncrements.push_back(values.at(1) - previousBeta);
            previousAlpha = values.at(0);
            previousBeta = values.at(1);
        }

        double alphaSum = 0.0;
        double betaSum = 0.0;
        for (int sample = 0; sample < sampleCount; ++sample) {
            alphaSum += alphaIncrements[static_cast<std::size_t>(sample)];
            betaSum += betaIncrements[static_cast<std::size_t>(sample)];
        }
        const double alphaMean = alphaSum / sampleCount;
        const double betaMean = betaSum / sampleCount;

        double covariance = 0.0;
        double alphaVariance = 0.0;
        double betaVariance = 0.0;
        for (int sample = 0; sample < sampleCount; ++sample) {
            const double alphaDeviation =
                alphaIncrements[static_cast<std::size_t>(sample)] - alphaMean;
            const double betaDeviation =
                betaIncrements[static_cast<std::size_t>(sample)] - betaMean;
            covariance += alphaDeviation * betaDeviation;
            alphaVariance += alphaDeviation * alphaDeviation;
            betaVariance += betaDeviation * betaDeviation;
        }
        const double realised = covariance / std::sqrt(alphaVariance * betaVariance);

        abm::test::expect(std::abs(realised - target) < 0.05,
                          "Realised fundamental correlation matches the configured rho_AB",
                          failures);
    }
}

/** A geometric process must stay positive and grow multiplicatively. */
void testGeometricBrownianMotionFundamentalProcess(int& failures) {
    abm::FundamentalValueProcessParameters geometric;
    geometric.processType = abm::FundamentalProcessType::GeometricBrownianMotion;
    geometric.driftPerStep = 0.001;
    geometric.shockStdDev = 0.02;
    geometric.minimumValue = 1e-8;

    abm::Market market;
    abm::FundamentalValueProcess fundamentalProcess(7U);
    market.configureAssets({"beta"});
    market.storeTrueValue(0, 40.0);

    bool alwaysPositive = true;
    for (int step = 0; step < 500; ++step) {
        const double value = fundamentalProcess.generateFundamentalValue(market, 0, geometric);
        if (!(value > 0.0)) {
            alwaysPositive = false;
        }
    }
    abm::test::expect(alwaysPositive, "Geometric fundamental values remain strictly positive",
                      failures);

    /*
     * With zero volatility the process is deterministic, so the closed form
     * F_t = F_0 * exp(mu * t) pins the drift convention (mu is the expected
     * arithmetic growth rate, after the Ito correction cancels).
     */
    abm::FundamentalValueProcessParameters deterministic;
    deterministic.processType = abm::FundamentalProcessType::GeometricBrownianMotion;
    deterministic.driftPerStep = 0.01;
    deterministic.shockStdDev = 0.0;
    deterministic.minimumValue = 1e-8;

    abm::Market deterministicMarket;
    abm::FundamentalValueProcess deterministicProcess(11U);
    deterministicMarket.configureAssets({"beta"});
    deterministicMarket.storeTrueValue(0, 50.0);
    double expected = 50.0;
    bool matchesClosedForm = true;
    for (int step = 0; step < 25; ++step) {
        expected *= std::exp(0.01);
        const double value =
            deterministicProcess.generateFundamentalValue(deterministicMarket, 0, deterministic);
        if (!abm::test::nearlyEqual(value, expected, 1e-9)) {
            matchesClosedForm = false;
        }
    }
    abm::test::expect(matchesClosedForm,
                      "Zero-volatility geometric process follows F_0 * exp(mu * t)", failures);
}

/** Two assets may run different processes simultaneously. */
void testAssetsMayUseDifferentProcesses(int& failures) {
    abm::FundamentalValueProcessParameters arithmetic;
    arithmetic.processType = abm::FundamentalProcessType::ArithmeticRandomWalk;
    arithmetic.driftPerStep = 1.0;
    arithmetic.shockStdDev = 0.0;
    arithmetic.minimumValue = 1e-8;

    abm::FundamentalValueProcessParameters geometric;
    geometric.processType = abm::FundamentalProcessType::GeometricBrownianMotion;
    geometric.driftPerStep = 0.1;
    geometric.shockStdDev = 0.0;
    geometric.minimumValue = 1e-8;

    abm::Market market;
    abm::FundamentalValueProcess fundamentalProcess(5U);
    market.configureAssets({"alpha", "beta"});
    market.storeTrueValue(0, 100.0);
    market.storeTrueValue(1, 100.0);

    const std::vector<double> values = fundamentalProcess.generateCorrelatedFundamentalValues(
        market, {arithmetic, geometric}, 0.5);

    abm::test::expect(abm::test::nearlyEqual(values.at(0), 101.0, 1e-9),
                      "Arithmetic asset advances additively by its drift", failures);
    abm::test::expect(abm::test::nearlyEqual(values.at(1), 100.0 * std::exp(0.1), 1e-9),
                      "Geometric asset advances multiplicatively by its drift", failures);
}

/** Correlations outside the positive-semi-definite region must be rejected. */
void testCorrelatedFundamentalsRejectInvalidCorrelation(int& failures) {
    abm::FundamentalValueProcessParameters parameters;
    parameters.shockStdDev = 0.01;
    parameters.minimumValue = 1e-8;

    abm::Market market;
    abm::FundamentalValueProcess fundamentalProcess(3U);
    market.configureAssets({"alpha", "beta", "gamma"});
    market.storeTrueValue(0, 100.0);
    market.storeTrueValue(1, 100.0);
    market.storeTrueValue(2, 100.0);

    bool rejectedOutOfRange = false;
    try {
        const std::vector<double> ignored = fundamentalProcess.generateCorrelatedFundamentalValues(
            market, {parameters, parameters, parameters}, 1.5);
        (void)ignored;
    } catch (const std::invalid_argument&) {
        rejectedOutOfRange = true;
    }
    abm::test::expect(rejectedOutOfRange, "Correlation above 1 is rejected", failures);

    /*
     * Three assets cannot all be correlated at -0.9: the equicorrelation matrix
     * is positive semi-definite only down to -1/(n-1) = -0.5.
     */
    bool rejectedNotPsd = false;
    try {
        const std::vector<double> ignored = fundamentalProcess.generateCorrelatedFundamentalValues(
            market, {parameters, parameters, parameters}, -0.9);
        (void)ignored;
    } catch (const std::invalid_argument&) {
        rejectedNotPsd = true;
    }
    abm::test::expect(rejectedNotPsd,
                      "Equicorrelation below -1/(n-1) is rejected as not positive semi-definite",
                      failures);
}

void runSimulationComponentTests(int& failures) {
    testCorrelatedFundamentalMatchesLegacySingleAssetDraw(failures);
    testIndependentFundamentalsDifferAcrossAssets(failures);
    testCorrelatedFundamentalsReproduceRequestedCorrelation(failures);
    testGeometricBrownianMotionFundamentalProcess(failures);
    testAssetsMayUseDifferentProcesses(failures);
    testCorrelatedFundamentalsRejectInvalidCorrelation(failures);
    testSimulationClockReportsProgress(failures);
    testNonNegativeGiniCoefficientUsesBoundedWealthIndex(failures);
    testRunMetricsCalculatesFinalWealthGiniFromAgentSnapshots(failures);
    testRunMetricsAveragesOnlyPositiveOpportunityEfficiencySteps(failures);
    testAssetRunMetricsScreenEachAssetIndependently(failures);
    testAllocativeEfficiencyMaximumSurplusUsesSortedSchedules(failures);
    testAllocativeEfficiencyZeroWhenNoPositiveSurplusExists(failures);
    testAllocativeEfficiencyRealizedSurplusUsesExecutedReservations(failures);
    testActivationSchedulerIsSeedReproducible(failures);
    testSocialInfluenceModelUpdatesAndRespectsDisabledBaseline(failures);
    testSocialInfluenceSpatialHashMatchesRadiusOracle(failures);
    testRiskControlServiceForcedBuyIn(failures);
    testForcedBuyInAppliesTransactionCostsWhenEnabled(failures);
    testRiskControlServicePerAssetShortInterestAndBuyIn(failures);
    testMarketClearingEngineIsolatesAssetBooks(failures);
    testMarketClearingEngineExecutesConstrainedTrade(failures);
    testMarketClearingEngineAppliesTransactionCosts(failures);
    testMarketClearingEngineCostAwareAffordability(failures);
    testMarketClearingEngineReportsAllocativeEfficiency(failures);
    testMarketClearingEnginePreventsSelfTrade(failures);
    testMarketClearingEngineMarketOrderPriceCollar(failures);
    testMarketClearingEngineSplitsCancellationCounters(failures);
    testFundamentalistRiskThresholdDefaultsAgree(failures);
    testFundamentalistTransactionCostHurdleSuppressesWeakMispricing(failures);
    testDiagnosticsRecorderBuildsStepAndRunOutput(failures);
}

} // namespace abm::test
