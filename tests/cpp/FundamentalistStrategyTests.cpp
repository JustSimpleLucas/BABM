// FundamentalistStrategyTests.cpp

#include "tests/cpp/TestSupport.h"

#include "Agent/Agent.h"
#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/FundamentalistStrategy.h"
#include "AgentStrategy/TradingStrategy.h"
#include "BehaviouralFinance/ProspectTheory.h"
#include "Config/MarketConfig.h"
#include "Market/Market.h"
#include "OrderBook/Order.h"
#include "Utility/CholeskyFactorization.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace {

constexpr double kPrice = 100.0;
constexpr double kCash = 10000.0;
constexpr double kVolatility = 0.02;
constexpr double kRiskAversion = 3.0;

/** Tversky-Kahneman preferences at the shipped loss aversion (config/simulation.cfg). */
abm::ProspectTheory shippedPreferences() {
    abm::ProspectTheoryParameters parameters{};
    parameters.lossAversion = 3.30477818806;
    parameters.curvatureForGain = 0.88;
    parameters.curvatureForLoss = 0.88;
    parameters.probDistortionForGain = 0.61;
    parameters.probDistortionForLoss = 0.69;
    parameters.scenarioCount = 13;
    return abm::ProspectTheory(parameters);
}

/**
 * Buy quantity a cash-only fundamentalist submits through the production
 * generateOrders path, for a given log mispricing log(F / P) and forecast
 * horizon. Volatility is fixed through the covariance so the expected
 * Markowitz weight can be written down in closed form.
 */
double fundamentalistBuyQuantity(double logMispricing, double forecastHorizon,
                                 bool usesProspectTheory) {
    abm::Market market;
    market.configureAssets({"asset"});
    market.storeMarketValue(0, kPrice);
    market.storeTrueValue(0, kPrice * std::exp(logMispricing));

    abm::Agent agent(1U, abm::AgentEndowment{kCash, {0.0}}, shippedPreferences(),
                     usesProspectTheory);
    agent.initializeWealth(std::vector<double>{kPrice});

    abm::FundamentalistStrategyParameters parameters;
    parameters.allocationLine = abm::AssetAllocationLine(kRiskAversion, 0.0, 1.0);
    parameters.riskThresholds = abm::FundamentalistRiskThresholds{0.9, 0.9};
    parameters.forecastHorizon = forecastHorizon;
    abm::FundamentalistStrategy strategy(parameters);

    abm::AssetUniverse assets;
    assets.declare({abm::test::makeAssetDefinition("asset", kPrice, 0.0, 0.01, 0.01, 0.0, 1e-6)});
    const std::vector<double> prices{kPrice};
    abm::SymmetricMatrix covariance(1);
    covariance.at(0, 0) = kVolatility * kVolatility;
    const abm::MarketStepView marketView{prices, covariance, assets};

    abm::TradingOrderContext context;
    context.useValuationLimitPrice = true;
    context.priceTickSize = 0.01;
    context.transactionCostAffectsDecisions = false;

    double quantity = 0.0;
    for (const abm::Order& order : strategy.generateOrders(agent, market, 1, context, marketView)) {
        quantity += order.type == abm::OrderType::BUY ? order.quantity : 0.0;
    }
    return quantity;
}

/** Shares bought at an interior Markowitz weight w = expected per-step return / (rho sigma^2). */
double interiorTargetShares(double perStepExcessReturn) {
    const double weight = perStepExcessReturn / (kRiskAversion * kVolatility * kVolatility);
    return kCash * weight / kPrice;
}

/*
 * The mispricing is the log return expected over the forecast horizon, so the
 * Markowitz rule receives it spread over that horizon. With a 1% mispricing,
 * sigma = 2% and rho = 3, the one-step rule asks for a weight of 8.3, which is
 * clipped to the 100% bound and then limited by cash; a 20-step horizon gives
 * an interior weight of 0.42, and doubling the horizon halves the position.
 */
void testForecastHorizonTurnsSaturatedWeightIntoInteriorOne(int& failures) {
    const double mispricing = 0.01;

    const double oneStep = fundamentalistBuyQuantity(mispricing, 1.0, false);
    const double limitPrice = 101.0; // F = 101.005 quantised down to the 0.01 tick.
    abm::test::expect(abm::test::nearlyEqual(oneStep, kCash / limitPrice, 1e-9),
                      "the one-step rule should saturate and spend all cash", failures);

    const double twentySteps = fundamentalistBuyQuantity(mispricing, 20.0, false);
    abm::test::expect(
        abm::test::nearlyEqual(twentySteps, interiorTargetShares(mispricing / 20.0), 1e-9),
        "a 20-step horizon should give the interior Markowitz position for mispricing / 20",
        failures);

    const double fortySteps = fundamentalistBuyQuantity(mispricing, 40.0, false);
    abm::test::expect(abm::test::nearlyEqual(fortySteps, twentySteps / 2.0, 1e-9),
                      "doubling the forecast horizon should halve an interior position", failures);
}

/*
 * A CPT agent values the gamble over its forecast horizon (Benartzi and
 * Thaler, 1995): mean equal to the whole mispricing, volatility
 * sigma * sqrt(horizon). The resulting premium is spread over the horizon for
 * sizing. Judged over one step instead, the same 8% mispricing would be worth
 * less than cash to this loss-averse agent, and it would not buy at all.
 */
void testCptValuesTheGambleOverTheForecastHorizon(int& failures) {
    const double mispricing = 0.08;
    const double horizon = 20.0;
    const abm::ProspectTheory preferences = shippedPreferences();

    const double horizonPremium =
        std::clamp(preferences.prospectAdjustedReturn(
                       {mispricing, kVolatility * std::sqrt(horizon), 0.0, 0.0}),
                   -1.0, 1.0);
    const double oneStepPremium =
        preferences.prospectAdjustedReturn({mispricing / horizon, kVolatility, 0.0, 0.0});
    abm::test::expect(horizonPremium > 0.0,
                      "an 8% mispricing over 20 steps should beat cash for the CPT agent",
                      failures);
    abm::test::expect(oneStepPremium < 0.0,
                      "judged over one step, the same forecast should lose to cash", failures);

    // The weight is interior (about 0.83) and cash is not binding at the
    // 108.32 limit price, so the order is exactly the Markowitz target.
    const double expectedShares = interiorTargetShares(horizonPremium / horizon);
    abm::test::expect(abm::test::nearlyEqual(fundamentalistBuyQuantity(mispricing, horizon, true),
                                             expectedShares, 1e-9),
                      "a CPT fundamentalist should size from the horizon premium / horizon",
                      failures);
}

/** A horizon shorter than the single step on which trades are decided is meaningless. */
void testForecastHorizonBelowOneIsRejected(int& failures) {
    abm::FundamentalistStrategyParameters parameters;
    parameters.forecastHorizon = 0.5;
    try {
        const abm::FundamentalistStrategy strategy(parameters);
        static_cast<void>(strategy);
        abm::test::expect(false, "a forecast horizon below one step should be rejected", failures);
    } catch (const std::invalid_argument&) {
        abm::test::expect(true, "a forecast horizon below one step should be rejected", failures);
    }
}

} // namespace

namespace abm::test {

void runFundamentalistStrategyTests(int& failures) {
    testForecastHorizonTurnsSaturatedWeightIntoInteriorOne(failures);
    testCptValuesTheGambleOverTheForecastHorizon(failures);
    testForecastHorizonBelowOneIsRejected(failures);
}

} // namespace abm::test
