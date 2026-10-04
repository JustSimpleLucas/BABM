// ProspectTheoryTests.cpp

#include "tests/cpp/TestSupport.h"

#include "Agent/Agent.h"
#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/FundamentalistStrategy.h"
#include "AgentStrategy/StrategyMarketHelpers.h"
#include "AgentStrategy/TradingStrategy.h"
#include "BehaviouralFinance/ProspectTheory.h"
#include "Config/MarketConfig.h"
#include "Market/Market.h"
#include "OrderBook/Order.h"
#include "Simulation/SimulationEngine.h"
#include "Utility/CholeskyFactorization.h"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>
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

/** Loss aversion of the shipped configuration (config/simulation.cfg). */
constexpr double kShippedLossAversion = 3.30477818806;

/**
 * Builds CPT preferences with the Tversky and Kahneman (1992) curvature and
 * probability weighting, so the property tests below pin the transform at the
 * parameters the model actually runs with.
 */
abm::ProspectTheory tverskyKahnemanPreferences(double lossAversion, std::size_t scenarioCount) {
    abm::ProspectTheoryParameters parameters{};
    parameters.lossAversion = lossAversion;
    parameters.curvatureForGain = 0.88;
    parameters.curvatureForLoss = 0.88;
    parameters.probDistortionForGain = 0.61;
    parameters.probDistortionForLoss = 0.69;
    parameters.scenarioCount = scenarioCount;
    return abm::ProspectTheory(parameters);
}

/** Builds CPT preferences with linear probability weights, isolating value-function curvature. */
abm::ProspectTheory linearWeightPreferences(double lossAversion, double curvature,
                                            std::size_t scenarioCount) {
    abm::ProspectTheoryParameters parameters{};
    parameters.lossAversion = lossAversion;
    parameters.curvatureForGain = curvature;
    parameters.curvatureForLoss = curvature;
    parameters.probDistortionForGain = 1.0;
    parameters.probDistortionForLoss = 1.0;
    parameters.scenarioCount = scenarioCount;
    return abm::ProspectTheory(parameters);
}

/*
 * P1, moment matching. The scenario ladder must reproduce the subjective
 * one-step distribution it stands for: mean r_f + forecast and variance
 * sigma^2, whatever the scenario count.
 */
void testScenarioLadderMatchesForecastMoments(int& failures) {
    const abm::ProspectReturnForecast forecast{0.01, 0.02, 0.03, 0.001};
    for (const std::size_t scenarioCount : {3U, 5U, 13U, 21U, 101U}) {
        const std::vector<abm::ProspectOutcome> scenarios =
            tverskyKahnemanPreferences(kShippedLossAversion, scenarioCount)
                .returnScenarios(forecast);

        double totalProbability = 0.0;
        double mean = 0.0;
        for (const abm::ProspectOutcome& scenario : scenarios) {
            totalProbability += scenario.probability;
            mean += scenario.probability * (scenario.relativeOutcome + forecast.referenceLogReturn);
        }
        double variance = 0.0;
        for (const abm::ProspectOutcome& scenario : scenarios) {
            const double deviation = scenario.relativeOutcome + forecast.referenceLogReturn - mean;
            variance += scenario.probability * deviation * deviation;
        }

        const std::string label = " (n = " + std::to_string(scenarioCount) + ")";
        abm::test::expect(scenarios.size() == scenarioCount,
                          "the ladder should hold one outcome per scenario" + label, failures);
        abm::test::expect(abm::test::nearlyEqual(totalProbability, 1.0, 1e-12),
                          "scenario probabilities should sum to one" + label, failures);
        abm::test::expect(abm::test::nearlyEqual(mean, 0.011, 1e-12),
                          "the ladder mean should equal the risk-free plus forecast return" + label,
                          failures);
        abm::test::expect(abm::test::nearlyEqual(variance, 0.0004, 1e-12),
                          "the ladder variance should equal sigma^2" + label, failures);
    }
}

/** The inverse value function recovers the gain or loss that produced a value. */
void testInverseValueFunctionRecoversOutcomes(int& failures) {
    const abm::ProspectTheory preferences = tverskyKahnemanPreferences(kShippedLossAversion, 13);
    for (const double outcome : {-0.3, -0.01, 0.0, 0.01, 0.3}) {
        abm::test::expect(abm::test::nearlyEqual(
                              preferences.inverseValueFunction(preferences.valueFunction(outcome)),
                              outcome, 1e-14),
                          "the inverse value function should recover the original gain or loss",
                          failures);
    }
}

/*
 * P3, comparison with cash. The premium is the certainty equivalent of holding
 * minus that of cash, and the inverse value function is strictly increasing,
 * so the premium must be positive exactly when CPT values holding above the
 * sure outcome of selling, r_f - r_ref.
 */
void testPremiumSignMatchesHoldVersusCashChoice(int& failures) {
    const abm::ProspectTheory preferences = tverskyKahnemanPreferences(kShippedLossAversion, 13);
    int cases = 0;
    int violations = 0;
    for (const double riskFree : {0.0, 0.001}) {
        for (const double forecast : {-0.02, -0.005, 0.0, 0.005, 0.02}) {
            for (const double volatility : {0.005, 0.0187, 0.05}) {
                for (const double reference : {-0.2, -0.05, -0.01, 0.0, 0.01, 0.05, 0.2}) {
                    const abm::ProspectReturnForecast candidate{forecast, volatility, reference,
                                                                riskFree};
                    const double holdValue =
                        preferences.calculateProspectValue(preferences.returnScenarios(candidate));
                    const double cashValue = preferences.valueFunction(riskFree - reference);
                    if (std::abs(holdValue - cashValue) < 1e-12) {
                        continue; // Indifference leaves the sign undefined.
                    }
                    ++cases;
                    const bool premiumPositive =
                        preferences.prospectAdjustedReturn(candidate) > 0.0;
                    violations += premiumPositive == (holdValue > cashValue) ? 0 : 1;
                }
            }
        }
    }
    abm::test::expect(violations == 0,
                      "the CPT premium should be positive exactly when holding beats cash (" +
                          std::to_string(violations) + " of " + std::to_string(cases) +
                          " cases disagree)",
                      failures);
}

/*
 * Cash earns the risk-free rate, so it is the benchmark: a riskless asset keeps
 * its excess forecast as its premium whatever r_f, and an asset that only
 * matches the risk-free return carries no premium.
 */
void testRiskFreeRateIsTheCashBenchmark(int& failures) {
    const abm::ProspectTheory preferences = tverskyKahnemanPreferences(kShippedLossAversion, 13);
    for (const double reference : {-0.05, 0.0, 0.05}) {
        abm::test::expect(
            abm::test::nearlyEqual(
                preferences.prospectAdjustedReturn({0.002, 0.0, reference, 0.001}), 0.002, 1e-12),
            "a riskless excess forecast should keep its premium when cash earns r_f", failures);
        abm::test::expect(
            abm::test::nearlyEqual(preferences.prospectAdjustedReturn({0.0, 0.0, reference, 0.001}),
                                   0.0, 1e-12),
            "an asset that only matches the risk-free return should carry no premium", failures);
    }
}

/*
 * P2, riskless invariance. Prospect theory changes how agents treat risk, not
 * how they read a sure return: with zero volatility every scenario is the
 * forecast itself, so its certainty equivalent must be the forecast whatever
 * the agent's reference point or loss aversion.
 */
void testRisklessForecastPassesThroughUnchanged(int& failures) {
    int violations = 0;
    for (const double lossAversion : {1.0, 2.25, kShippedLossAversion}) {
        const abm::ProspectTheory preferences = tverskyKahnemanPreferences(lossAversion, 13);
        for (const double reference : {-0.2, -0.05, 0.0, 0.05, 0.2}) {
            for (const double forecast : {-0.03, 0.0, 0.004, 0.02}) {
                const double adjusted =
                    preferences.prospectAdjustedReturn({forecast, 0.0, reference});
                violations += abm::test::nearlyEqual(adjusted, forecast, 1e-12) ? 0 : 1;
            }
        }
    }
    abm::test::expect(violations == 0,
                      "a riskless forecast should pass through the CPT transform unchanged (" +
                          std::to_string(violations) + " of 60 cases differ)",
                      failures);
}

/*
 * P9, the scenario count sets resolution only. The ladder approximates one
 * subjective return distribution, so adding scenarios must refine the result
 * rather than move it; a count-dependent result would let a numerical setting
 * act as a preference parameter.
 */
void testScenarioCountOnlySetsResolution(int& failures) {
    const abm::ProspectReturnForecast forecast{0.005, 0.0187, 0.0};
    const double limit =
        tverskyKahnemanPreferences(kShippedLossAversion, 201).prospectAdjustedReturn(forecast);
    for (const std::size_t scenarioCount : {13U, 21U, 51U, 101U}) {
        const double adjusted = tverskyKahnemanPreferences(kShippedLossAversion, scenarioCount)
                                    .prospectAdjustedReturn(forecast);
        abm::test::expect(abm::test::nearlyEqual(adjusted, limit, 1e-4),
                          "the CPT premium should converge as scenarios are added (n = " +
                              std::to_string(scenarioCount) + ")",
                          failures);
    }
}

/*
 * P4, return units. With equal gain and loss curvature the value function is
 * homogeneous of degree alpha and its inverse of degree 1/alpha, so the
 * certainty-equivalent premium scales one-for-one with the returns. A raw CPT
 * value would scale by c^alpha instead and so depend on the time unit of a step.
 */
void testPremiumIsMeasuredInReturnUnits(int& failures) {
    const abm::ProspectTheory preferences = tverskyKahnemanPreferences(kShippedLossAversion, 13);
    const double forecast = 0.005;
    const double volatility = 0.0187;
    const double reference = 0.02;
    const double base = preferences.prospectAdjustedReturn({forecast, volatility, reference});
    for (const double scale : {0.5, 2.0, 4.0}) {
        const double scaled = preferences.prospectAdjustedReturn(
            {scale * forecast, scale * volatility, scale * reference});
        abm::test::expect(abm::test::nearlyEqual(scaled, scale * base, 1e-12),
                          "scaling every return by c should scale the CPT premium by c", failures);
    }
}

/*
 * P5, loss aversion cancels within one domain. When every scenario is a loss,
 * lambda multiplies every value and is divided out again by the inverse value
 * function; when every scenario is a gain it never appears. Loss aversion
 * therefore matters only for mixed prospects, as in the theory.
 */
void testLossAversionCancelsWithinOneDomain(int& failures) {
    for (const double reference : {0.3, -0.3}) {
        const abm::ProspectReturnForecast forecast{0.005, 0.0187, reference};
        const double atOne = tverskyKahnemanPreferences(1.0, 13).prospectAdjustedReturn(forecast);
        for (const double lossAversion : {2.25, kShippedLossAversion, 5.0}) {
            const double adjusted =
                tverskyKahnemanPreferences(lossAversion, 13).prospectAdjustedReturn(forecast);
            abm::test::expect(abm::test::nearlyEqual(adjusted, atOne, 1e-12),
                              reference > 0.0
                                  ? "loss aversion should cancel when every scenario is a loss"
                                  : "loss aversion should not affect an all-gain prospect",
                              failures);
        }
    }
}

/*
 * P6 and P7, reflection and the disposition direction (Kahneman and Tversky,
 * 1979; Shefrin and Statman, 1985). When the paper loss or gain delta is large
 * enough that next step's gamble lies entirely in losses (reference +delta) or
 * entirely in gains (reference -delta), the convex loss domain makes the agent
 * risk seeking and the concave gain domain risk averse:
 *
 *     premium(+delta) > forecast > premium(-delta).
 *
 * The agent holding a loser is therefore more willing to keep it than the agent
 * holding a winner. Near break-even, where the gamble straddles the reference,
 * prospect theory makes no clear prediction (Barberis and Xiong, 2009; Kaustia,
 * 2010), so the property is pinned only under its single-domain condition
 * delta > |forecast| + sigma * sqrt(n - 1). The ordering is a theorem for linear
 * weights (power-mean inequality) and was verified numerically for the
 * Tversky-Kahneman weights on this grid.
 */
void testReflectionImpliesDispositionDirection(int& failures) {
    int cases = 0;
    int violations = 0;
    for (const bool linearWeights : {false, true}) {
        for (const double lossAversion : {1.0, 2.25, kShippedLossAversion}) {
            for (const std::size_t scenarioCount : {3U, 13U, 21U}) {
                const abm::ProspectTheory preferences =
                    linearWeights ? linearWeightPreferences(lossAversion, 0.88, scenarioCount)
                                  : tverskyKahnemanPreferences(lossAversion, scenarioCount);
                for (const double forecast : {-0.01, 0.0, 0.01}) {
                    for (const double volatility : {0.005, 0.0187, 0.05}) {
                        const double delta =
                            std::abs(forecast) +
                            (volatility * std::sqrt(static_cast<double>(scenarioCount - 1))) + 0.01;
                        const double holdingLoser =
                            preferences.prospectAdjustedReturn({forecast, volatility, delta});
                        const double holdingWinner =
                            preferences.prospectAdjustedReturn({forecast, volatility, -delta});
                        ++cases;
                        violations += (holdingLoser > forecast && forecast > holdingWinner) ? 0 : 1;
                    }
                }
            }
        }
    }
    abm::test::expect(violations == 0,
                      "single-domain gambles should give premium(paper loss) > forecast > "
                      "premium(paper gain) (" +
                          std::to_string(violations) + " of " + std::to_string(cases) +
                          " cases violate)",
                      failures);
}

/*
 * P8, loss aversion. The premium is non-increasing in lambda, and a centred
 * gamble (zero forecast, reference at today's price) is worth less than cash
 * once losses loom larger than gains (first-order risk aversion at the kink;
 * Segal and Spivak, 1990). The three-scenario linear case is checked against
 * its closed form: scenarios at -sqrt(2)sigma, 0, +sqrt(2)sigma with
 * probabilities 1/4, 1/2, 1/4 give V = (1 - lambda) sqrt(2) sigma / 4, whose
 * certainty equivalent for lambda = 2 is -sqrt(2) sigma / 8.
 */
void testLossAversionLowersThePremium(int& failures) {
    const abm::ProspectReturnForecast mixedForecast{0.005, 0.0187, 0.0};
    double previous = tverskyKahnemanPreferences(1.0, 13).prospectAdjustedReturn(mixedForecast);
    for (const double lossAversion : {2.25, kShippedLossAversion, 5.0}) {
        const double adjusted =
            tverskyKahnemanPreferences(lossAversion, 13).prospectAdjustedReturn(mixedForecast);
        abm::test::expect(adjusted < previous,
                          "the CPT premium of a mixed gamble should fall as loss aversion rises",
                          failures);
        previous = adjusted;
    }

    const abm::ProspectReturnForecast centredForecast{0.0, 0.0187, 0.0};
    abm::test::expect(
        tverskyKahnemanPreferences(2.25, 13).prospectAdjustedReturn(centredForecast) < 0.0,
        "a centred gamble should be worth less than cash under Tversky-Kahneman preferences",
        failures);

    const double volatility = 0.01;
    const double closedForm = -std::sqrt(2.0) * volatility / 8.0;
    abm::test::expect(
        abm::test::nearlyEqual(
            linearWeightPreferences(2.0, 1.0, 3).prospectAdjustedReturn({0.0, volatility, 0.0}),
            closedForm, 1e-15),
        "the three-scenario linear premium should match its closed form -sqrt(2) sigma / 8",
        failures);
}

/*
 * Reference values at the shipped preferences, forecast 0.005, volatility
 * 0.0187 and 13 scenarios. They were computed with an independent
 * re-implementation of docs/formalism.tex (CPT section) and guard against
 * accidental numerical drift that the qualitative properties above would miss.
 */
void testCertaintyEquivalentPremiumReferenceValues(int& failures) {
    const abm::ProspectTheory preferences = tverskyKahnemanPreferences(kShippedLossAversion, 13);
    abm::test::expect(
        abm::test::nearlyEqual(preferences.prospectAdjustedReturn({0.005, 0.0187, 0.05}),
                               0.008529104410294017, 1e-12),
        "CPT premium for a 5% paper loss should match the reference value", failures);
    abm::test::expect(
        abm::test::nearlyEqual(preferences.prospectAdjustedReturn({0.005, 0.0187, 0.0}),
                               -0.002991120365568333, 1e-12),
        "CPT premium at the reference point should match the reference value", failures);
    abm::test::expect(
        abm::test::nearlyEqual(preferences.prospectAdjustedReturn({0.005, 0.0187, -0.05}),
                               -0.0009394597155681222, 1e-12),
        "CPT premium for a 5% paper gain should match the reference value", failures);
}

/**
 * Runs one CPT fundamentalist through the production order path at a given
 * average entry price. The asset is slightly overvalued (fundamental 99.9
 * against price 100), so the valuation quote is a sell; CPT then decides
 * how much of the position the agent still wants to hold.
 */
std::vector<abm::Order> fundamentalistOrdersAtEntryPrice(double entryPrice,
                                                         bool usesProspectTheory) {
    constexpr double kPrice = 100.0;
    abm::Market market;
    market.configureAssets({"asset"});
    market.storeMarketValue(0, kPrice);
    market.storeTrueValue(0, 99.9);

    abm::Agent agent(1U, abm::AgentEndowment{10000.0, {100.0}},
                     tverskyKahnemanPreferences(kShippedLossAversion, 13), usesProspectTheory);
    // Initialising at the entry price anchors the position there; the strategy
    // then marks it to the current price of 100.
    agent.initializeWealth(std::vector<double>{entryPrice});

    abm::FundamentalistStrategyParameters parameters;
    parameters.allocationLine = abm::AssetAllocationLine(3.0, 0.0, 1.0);
    parameters.riskThresholds = abm::FundamentalistRiskThresholds{0.9, 0.9};
    parameters.referencePointMode = abm::ProspectReferencePointMode::AveragePurchasePrice;
    abm::FundamentalistStrategy strategy(parameters);

    abm::AssetUniverse assets;
    assets.declare({abm::test::makeAssetDefinition("asset", kPrice, 100.0, 0.01, 0.01, 0.0, 1e-6)});
    const std::vector<double> prices{kPrice};
    abm::SymmetricMatrix covariance(1);
    covariance.at(0, 0) = 0.0187 * 0.0187;
    const abm::MarketStepView marketView{prices, covariance, assets};

    abm::TradingOrderContext context;
    context.useValuationLimitPrice = true;
    context.priceTickSize = 0.01;
    context.transactionCostAffectsDecisions = false;
    return strategy.generateOrders(agent, market, 1, context, marketView);
}

double soldQuantity(const std::vector<abm::Order>& orders) {
    double quantity = 0.0;
    for (const abm::Order& order : orders) {
        quantity += order.type == abm::OrderType::SELL ? order.quantity : 0.0;
    }
    return quantity;
}

/*
 * The disposition direction end to end, through the production generateOrders
 * path. Two identical CPT fundamentalists face the same slightly overvalued
 * asset; one bought 10% above today's price (a loser), the other 10% below (a
 * winner). Prospect theory predicts the winner realises its gain while the
 * loser keeps the position (Shefrin and Statman, 1985; Odean, 1998). Agents
 * without CPT ignore the entry price and act identically.
 */
void testCptFundamentalistKeepsLoserAndRealisesWinner(int& failures) {
    const double loserEntryPrice = 100.0 * std::exp(0.1);
    const double winnerEntryPrice = 100.0 * std::exp(-0.1);

    const double loserSold = soldQuantity(fundamentalistOrdersAtEntryPrice(loserEntryPrice, true));
    const double winnerSold =
        soldQuantity(fundamentalistOrdersAtEntryPrice(winnerEntryPrice, true));
    abm::test::expect(abm::test::nearlyEqual(loserSold, 0.0),
                      "a CPT fundamentalist with a 10% paper loss should keep the position",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(winnerSold, 100.0),
                      "a CPT fundamentalist with a 10% paper gain should realise it", failures);

    const double loserSoldWithoutCpt =
        soldQuantity(fundamentalistOrdersAtEntryPrice(loserEntryPrice, false));
    const double winnerSoldWithoutCpt =
        soldQuantity(fundamentalistOrdersAtEntryPrice(winnerEntryPrice, false));
    abm::test::expect(abm::test::nearlyEqual(loserSoldWithoutCpt, winnerSoldWithoutCpt),
                      "without CPT the entry price should not change the order", failures);
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
    // A sure outcome is its own certainty equivalent: loss aversion prices the
    // risk of a prospect, not the size of a loss that is certain to occur.
    abm::test::expect(
        abm::test::nearlyEqual(prospectTheory.prospectAdjustedReturn({-0.02, 0.0, 0.0}), -0.02),
        "a certain negative return should pass through unchanged, not be scaled by loss aversion",
        failures);
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
    testScenarioLadderMatchesForecastMoments(failures);
    testInverseValueFunctionRecoversOutcomes(failures);
    testPremiumSignMatchesHoldVersusCashChoice(failures);
    testRiskFreeRateIsTheCashBenchmark(failures);
    testRisklessForecastPassesThroughUnchanged(failures);
    testScenarioCountOnlySetsResolution(failures);
    testPremiumIsMeasuredInReturnUnits(failures);
    testLossAversionCancelsWithinOneDomain(failures);
    testReflectionImpliesDispositionDirection(failures);
    testLossAversionLowersThePremium(failures);
    testCertaintyEquivalentPremiumReferenceValues(failures);
    testCptFundamentalistKeepsLoserAndRealisesWinner(failures);
}

} // namespace abm::test
