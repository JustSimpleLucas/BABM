// ChartistStrategyTests.cpp

#include "tests/cpp/TestSupport.h"

#include "Agent/Agent.h"
#include "AgentStrategy/BreakoutChartistStrategy.h"
#include "AgentStrategy/MeanReversionChartistStrategy.h"
#include "AgentStrategy/MomentumChartistStrategy.h"
#include "AgentStrategy/TradingStrategy.h"
#include "BehaviouralFinance/ProspectTheory.h"
#include "Config/MarketConfig.h"
#include "Market/Market.h"
#include "Utility/CholeskyFactorization.h"

#include <cmath>
#include <optional>
#include <utility>
#include <vector>

namespace {

constexpr char kAssetName[] = "test_asset";

void storePrices(abm::Market& market, const std::vector<double>& prices) {
    market.configureAssets({kAssetName});
    for (const double price : prices) {
        market.storeMarketValue(0, price);
    }
}

abm::ChartistStrategyParameters makeCommonChartistParameters() {
    abm::ChartistStrategyParameters parameters;
    parameters.assetIndex = 0;
    parameters.allocationLine = abm::AssetAllocationLine(3.0, -0.30, 1.0);
    parameters.volatilityWindow = 2;
    parameters.riskFreeRate = 0.0;
    parameters.maxShortWeight = 0.30;
    return parameters;
}

abm::MomentumChartistStrategy makeMomentumStrategy(double momentumSignalThreshold) {
    abm::MomentumChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters();
    parameters.shortWindow = 2;
    parameters.longWindow = 4;
    parameters.momentumSignalThreshold = momentumSignalThreshold;
    return abm::MomentumChartistStrategy(std::move(parameters));
}

abm::BreakoutChartistStrategy makeBreakoutStrategy() {
    abm::BreakoutChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters();
    parameters.breakoutWindow = 3;
    return abm::BreakoutChartistStrategy(std::move(parameters));
}

std::optional<abm::Order> generateMomentumOrder(const std::vector<double>& prices,
                                                double momentumSignalThreshold, double cash,
                                                double stock) {
    abm::Market market;
    storePrices(market, prices);

    abm::Agent agent(1U, abm::AgentEndowment{cash, {stock}}, abm::ProspectTheory{}, false);
    abm::MomentumChartistStrategy strategy = makeMomentumStrategy(momentumSignalThreshold);
    return strategy.generateOrder(agent, market, 1);
}

std::optional<abm::Order> generateMomentumValuationOrder(const std::vector<double>& prices,
                                                         double transactionCostRate,
                                                         bool transactionCostAffectsDecisions) {
    abm::Market market;
    storePrices(market, prices);

    abm::Agent agent(1U, abm::AgentEndowment{100000.0, {0.0}}, abm::ProspectTheory{}, false);
    abm::MomentumChartistStrategy strategy = makeMomentumStrategy(0.0);
    abm::TradingOrderContext context;
    context.useValuationLimitPrice = true;
    context.priceTickSize = 0.01;
    context.transactionCostRate = transactionCostRate;
    context.transactionCostAffectsDecisions = transactionCostAffectsDecisions;
    return strategy.generateOrder(agent, market, 1, context);
}

std::optional<abm::Order> generateBreakoutOrder(const std::vector<double>& prices, double cash,
                                                double stock) {
    abm::Market market;
    storePrices(market, prices);

    abm::Agent agent(1U, abm::AgentEndowment{cash, {stock}}, abm::ProspectTheory{}, false);
    abm::BreakoutChartistStrategy strategy = makeBreakoutStrategy();
    return strategy.generateOrder(agent, market, 1);
}

void testMomentumBuySignalRequiresGapAboveThreshold(int& failures) {
    const std::optional<abm::Order> order =
        generateMomentumOrder({100.0, 100.0, 100.0, 110.0}, 0.01, 100000.0, 0.0);

    abm::test::expect(order.has_value(),
                      "momentum should submit an order when the MA gap is above threshold",
                      failures);
    if (order.has_value()) {
        abm::test::expect(order->type == abm::OrderType::BUY,
                          "positive momentum above threshold should generate a buy order",
                          failures);
        abm::test::expect(order->quantity > 0.0,
                          "positive momentum order should have positive quantity", failures);
    }
}

void testMomentumSellSignalRequiresNegativeGapBelowThreshold(int& failures) {
    const std::optional<abm::Order> order =
        generateMomentumOrder({100.0, 100.0, 100.0, 90.0}, 0.01, 10000.0, 10.0);

    abm::test::expect(order.has_value(),
                      "momentum should submit an order when the negative MA gap is below threshold",
                      failures);
    if (order.has_value()) {
        abm::test::expect(order->type == abm::OrderType::SELL,
                          "negative momentum below threshold should generate a sell order",
                          failures);
        abm::test::expect(order->quantity > 0.0,
                          "negative momentum order should have positive quantity", failures);
    }
}

void testMomentumHoldsInsideThresholdDeadband(int& failures) {
    const std::optional<abm::Order> order =
        generateMomentumOrder({100.0, 100.0, 100.0, 100.1}, 0.01, 100000.0, 0.0);

    abm::test::expect(!order.has_value(),
                      "momentum should hold when the MA gap is inside the threshold deadband",
                      failures);
}

void testZeroMomentumThresholdPreservesMovingAverageCrossover(int& failures) {
    const std::optional<abm::Order> order =
        generateMomentumOrder({100.0, 100.0, 100.0, 100.1}, 0.0, 100000.0, 0.0);

    abm::test::expect(order.has_value(),
                      "zero momentum threshold should preserve the previous MA-crossover signal",
                      failures);
    if (order.has_value()) {
        abm::test::expect(order->type == abm::OrderType::BUY,
                          "zero-threshold positive MA crossover should generate a buy order",
                          failures);
    }
}

void testMomentumValuationOrderRespectsTransactionCostHurdle(int& failures) {
    const std::vector<double> weakMomentumPrices{100.0, 100.0, 100.0, 100.1};
    const std::optional<abm::Order> noCostOrder =
        generateMomentumValuationOrder(weakMomentumPrices, 0.0, false);
    const std::optional<abm::Order> costAwareOrder =
        generateMomentumValuationOrder(weakMomentumPrices, 0.10, true);

    abm::test::expect(noCostOrder.has_value(),
                      "weak positive momentum should trade before applying cost hurdle", failures);
    abm::test::expect(!costAwareOrder.has_value(),
                      "transaction-cost hurdle should suppress weak chartist valuation gaps",
                      failures);
}

void testBreakoutBuySignalRequiresPriceAbovePreviousHigh(int& failures) {
    const std::optional<abm::Order> order =
        generateBreakoutOrder({100.0, 101.0, 102.0, 105.0}, 100000.0, 0.0);

    abm::test::expect(
        order.has_value(),
        "breakout should submit an order when price exceeds the previous channel high", failures);
    if (order.has_value()) {
        abm::test::expect(order->type == abm::OrderType::BUY,
                          "upside breakout should generate a buy order", failures);
        abm::test::expect(order->quantity > 0.0,
                          "upside breakout order should have positive quantity", failures);
    }
}

void testBreakoutSellSignalRequiresPriceBelowPreviousLow(int& failures) {
    const std::optional<abm::Order> order =
        generateBreakoutOrder({100.0, 99.0, 98.0, 96.0}, 10000.0, 10.0);

    abm::test::expect(
        order.has_value(),
        "breakout should submit an order when price falls below the previous channel low",
        failures);
    if (order.has_value()) {
        abm::test::expect(order->type == abm::OrderType::SELL,
                          "downside breakout should generate a sell order", failures);
        abm::test::expect(order->quantity > 0.0,
                          "downside breakout order should have positive quantity", failures);
    }
}

void testBreakoutHoldsInsidePreviousChannel(int& failures) {
    const std::optional<abm::Order> order =
        generateBreakoutOrder({100.0, 105.0, 95.0, 100.0}, 100000.0, 0.0);

    abm::test::expect(!order.has_value(),
                      "breakout should hold when price remains inside the previous channel",
                      failures);
}

std::optional<abm::Order> generateMomentumOrderWithAllocationFloor(double minRiskyWeight) {
    abm::Market market;
    storePrices(market, {100.0, 100.0, 100.0, 90.0});

    abm::Agent agent(1U, abm::AgentEndowment{10000.0, {0.0}}, abm::ProspectTheory{}, false);
    abm::MomentumChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters();
    parameters.commonParameters.allocationLine = abm::AssetAllocationLine(3.0, minRiskyWeight, 1.0);
    parameters.shortWindow = 2;
    parameters.longWindow = 4;
    parameters.momentumSignalThreshold = 0.0;
    abm::MomentumChartistStrategy strategy(std::move(parameters));
    return strategy.generateOrder(agent, market, 1);
}

void testChartistHonoursConfiguredAllocationFloor(int& failures) {
    /*
     * With no holdings, any sell order is a short sale. A zero allocation
     * floor must therefore suppress the sell that a negative-floor
     * configuration permits, proving the configured minimum risky weight is
     * applied rather than silently overwritten by the short-weight cap.
     */
    const std::optional<abm::Order> flooredOrder = generateMomentumOrderWithAllocationFloor(0.0);
    const std::optional<abm::Order> shortCapableOrder =
        generateMomentumOrderWithAllocationFloor(-0.30);

    abm::test::expect(!flooredOrder.has_value(),
                      "zero allocation floor should suppress short-selling chartist orders",
                      failures);
    abm::test::expect(shortCapableOrder.has_value() &&
                          shortCapableOrder->type == abm::OrderType::SELL &&
                          shortCapableOrder->quantity > 0.0,
                      "negative allocation floor should permit chartist short exposure", failures);
}

void testBreakoutHoldsOnChannelBoundaryEquality(int& failures) {
    const std::optional<abm::Order> highBoundaryOrder =
        generateBreakoutOrder({100.0, 105.0, 95.0, 105.0}, 100000.0, 0.0);
    const std::optional<abm::Order> lowBoundaryOrder =
        generateBreakoutOrder({100.0, 105.0, 95.0, 95.0}, 10000.0, 10.0);

    abm::test::expect(!highBoundaryOrder.has_value(),
                      "breakout should hold when price equals the previous channel high", failures);
    abm::test::expect(!lowBoundaryOrder.has_value(),
                      "breakout should hold when price equals the previous channel low", failures);
}

/**
 * Orders a cash-only mean-reversion chartist submits through the production
 * generateOrders path. Nineteen prices at 101 followed by 100 put the 20-step
 * average at 100.95, so the forecast is log(100.95 / 100); the covariance
 * fixes volatility at 2% so the Markowitz weight has a closed form.
 */
std::vector<abm::Order> meanReversionOrdersAtHorizon(double forecastHorizon) {
    std::vector<double> history(19, 101.0);
    history.push_back(100.0);
    abm::Market market;
    storePrices(market, history);

    abm::Agent agent(1U, abm::AgentEndowment{10000.0, {0.0}}, abm::ProspectTheory{}, false);
    abm::MeanReversionChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters();
    parameters.commonParameters.forecastHorizon = forecastHorizon;
    parameters.longWindow = 20;
    abm::MeanReversionChartistStrategy strategy(std::move(parameters));

    abm::AssetUniverse assets;
    assets.declare({abm::test::makeAssetDefinition(kAssetName, 100.0, 0.0, 0.01, 0.01, 0.0, 1e-6)});
    const std::vector<double> latestPrices{100.0};
    abm::SymmetricMatrix covariance(1);
    covariance.at(0, 0) = 0.02 * 0.02;
    const abm::MarketStepView marketView{latestPrices, covariance, assets};

    abm::TradingOrderContext context;
    context.useValuationLimitPrice = true;
    context.priceTickSize = 0.01;
    context.transactionCostAffectsDecisions = false;
    return strategy.generateOrders(agent, market, 1, context, marketView);
}

/*
 * The forecast horizon spreads the technical forecast over the steps it is
 * expected to take, so sizing sees a per-step return: doubling the horizon
 * halves an interior position. The valuation quote is the price expected at
 * the horizon and so does not depend on the horizon's length.
 */
void testForecastHorizonScalesChartistSizeButNotQuote(int& failures) {
    const std::vector<abm::Order> twentySteps = meanReversionOrdersAtHorizon(20.0);
    const std::vector<abm::Order> fortySteps = meanReversionOrdersAtHorizon(40.0);
    abm::test::expect(twentySteps.size() == 1 && fortySteps.size() == 1,
                      "the mean-reversion chartist should submit one buy at each horizon",
                      failures);
    if (twentySteps.size() != 1 || fortySteps.size() != 1) {
        return;
    }

    const double forecast = std::log(100.95 / 100.0);
    const double interiorWeight = (forecast / 20.0) / (3.0 * 0.02 * 0.02);
    abm::test::expect(
        abm::test::nearlyEqual(twentySteps.front().quantity, 10000.0 * interiorWeight / 100.0,
                               1e-9),
        "a 20-step horizon should give the interior Markowitz position for forecast / 20",
        failures);
    abm::test::expect(abm::test::nearlyEqual(fortySteps.front().quantity,
                                             twentySteps.front().quantity / 2.0, 1e-9),
                      "doubling the forecast horizon should halve an interior chartist position",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(fortySteps.front().price, twentySteps.front().price),
                      "the chartist valuation quote should not depend on the forecast horizon",
                      failures);
}

} // namespace

namespace abm::test {

void runChartistStrategyTests(int& failures) {
    testMomentumBuySignalRequiresGapAboveThreshold(failures);
    testMomentumSellSignalRequiresNegativeGapBelowThreshold(failures);
    testMomentumHoldsInsideThresholdDeadband(failures);
    testZeroMomentumThresholdPreservesMovingAverageCrossover(failures);
    testMomentumValuationOrderRespectsTransactionCostHurdle(failures);
    testBreakoutBuySignalRequiresPriceAbovePreviousHigh(failures);
    testBreakoutSellSignalRequiresPriceBelowPreviousLow(failures);
    testBreakoutHoldsInsidePreviousChannel(failures);
    testChartistHonoursConfiguredAllocationFloor(failures);
    testBreakoutHoldsOnChannelBoundaryEquality(failures);
    testForecastHorizonScalesChartistSizeButNotQuote(failures);
}

} // namespace abm::test
