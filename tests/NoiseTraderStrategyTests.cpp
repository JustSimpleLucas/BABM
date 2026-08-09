// NoiseTraderStrategyTests.cpp

#include "tests/TestSupport.h"

#include "Agent/Agent.h"
#include "AgentStrategy/NoiseTraderStrategy.h"
#include "AgentStrategy/TradingStrategy.h"
#include "BehaviouralFinance/ProspectTheory.h"
#include "ControlParameters/MarketConfig.h"
#include "Market/Market.h"
#include "Utility/CholeskyFactorization.h"

#include <cstdint>
#include <optional>
#include <vector>

namespace {

constexpr char kAssetName[] = "test_asset";
constexpr double kMarketPrice = 100.0;

void initialiseMarket(abm::Market& market) {
    market.configureAssets({kAssetName});
    market.storeMarketValue(0, kMarketPrice);
    market.storeTrueValue(0, kMarketPrice);
}

std::optional<abm::Order> generateNoiseOrder(std::uint64_t seed, double cash, double stock,
                                             double orderSizeFraction, double maxShortWeight,
                                             double transactionCostRate = 0.0) {
    abm::Market market;
    initialiseMarket(market);
    abm::Agent agent(1U, abm::AgentEndowment{cash, {stock}}, abm::ProspectTheory{}, false);
    abm::NoiseTraderStrategy strategy(0, 0.05, orderSizeFraction, maxShortWeight, seed);
    abm::TradingOrderContext context;
    context.priceTickSize = 0.01;
    context.transactionCostRate = transactionCostRate;
    context.transactionCostAffectsDecisions = true;
    return strategy.generateOrder(agent, market, 1, context);
}

std::optional<abm::Order> findNoiseOrder(abm::OrderType side, double cash, double stock,
                                         double orderSizeFraction, double maxShortWeight) {
    for (std::uint64_t seed = 1; seed < 1000; ++seed) {
        std::optional<abm::Order> order =
            generateNoiseOrder(seed, cash, stock, orderSizeFraction, maxShortWeight);
        if (order.has_value() && order->type == side) {
            return order;
        }
    }
    return std::nullopt;
}

void testNoiseTraderFirstOrderIsSeedDeterministic(int& failures) {
    const std::optional<abm::Order> first = generateNoiseOrder(20260510U, 10000.0, 5.0, 0.05, 0.30);
    const std::optional<abm::Order> second =
        generateNoiseOrder(20260510U, 10000.0, 5.0, 0.05, 0.30);

    abm::test::expect(first.has_value() == second.has_value(),
                      "noise trader first order existence should be deterministic", failures);
    if (first.has_value() && second.has_value()) {
        abm::test::expect(first->type == second->type,
                          "noise trader first order side should be deterministic", failures);
        abm::test::expect(abm::test::nearlyEqual(first->price, second->price),
                          "noise trader first order price should be deterministic", failures);
        abm::test::expect(abm::test::nearlyEqual(first->quantity, second->quantity),
                          "noise trader first order quantity should be deterministic", failures);
    }
}

void testNoiseTraderCanGenerateBuyAndSellOrdersFromSeededShocks(int& failures) {
    const std::optional<abm::Order> buyOrder =
        findNoiseOrder(abm::OrderType::BUY, 10000.0, 5.0, 0.05, 0.30);
    const std::optional<abm::Order> sellOrder =
        findNoiseOrder(abm::OrderType::SELL, 10000.0, 5.0, 0.05, 0.30);

    abm::test::expect(buyOrder.has_value(),
                      "seeded noise shocks should be able to generate a buy order", failures);
    abm::test::expect(sellOrder.has_value(),
                      "seeded noise shocks should be able to generate a sell order", failures);
}

void testNoiseTraderTransactionCostHurdleSuppressesSmallBeliefShock(int& failures) {
    const std::optional<abm::Order> noCostOrder =
        generateNoiseOrder(20260510U, 10000.0, 5.0, 0.05, 0.30, 0.0);
    const std::optional<abm::Order> highCostOrder =
        generateNoiseOrder(20260510U, 10000.0, 5.0, 0.05, 0.30, 0.99);

    abm::test::expect(noCostOrder.has_value(),
                      "test setup should produce a noise-trader order without costs", failures);
    abm::test::expect(!highCostOrder.has_value(),
                      "transaction-cost hurdle should suppress small random belief shocks",
                      failures);
}

void testNoiseTraderBuyQuantityRespectsWealthFractionAndCash(int& failures) {
    const double cash = 1000.0;
    const double stock = 0.0;
    const double orderSizeFraction = 0.20;
    const std::optional<abm::Order> order =
        findNoiseOrder(abm::OrderType::BUY, cash, stock, orderSizeFraction, 0.30);

    abm::test::expect(order.has_value(), "test setup should find a seeded noise buy order",
                      failures);
    if (!order.has_value()) {
        return;
    }

    const double wealth = cash + (stock * kMarketPrice);
    abm::test::expect(order->quantity <= (wealth * orderSizeFraction / order->price) + 1e-10,
                      "noise trader buy quantity should respect the wealth-fraction budget",
                      failures);
    abm::test::expect(order->quantity <= (cash / order->price) + 1e-10,
                      "noise trader buy quantity should respect available cash", failures);
}

void testNoiseTraderSellQuantityRespectsInventoryWhenShortCapIsZero(int& failures) {
    const std::optional<abm::Order> order =
        findNoiseOrder(abm::OrderType::SELL, 1000.0, 3.0, 1.0, 0.0);

    abm::test::expect(order.has_value(), "test setup should find a seeded noise sell order",
                      failures);
    if (order.has_value()) {
        abm::test::expect(order->quantity <= 3.0 + 1e-10,
                          "noise trader sell quantity should not exceed inventory when short cap "
                          "is zero",
                          failures);
    }
}

void testNoiseTraderSellQuantityRespectsStrategyShortCap(int& failures) {
    const double cash = 1000.0;
    const double stock = 1.0;
    const double maxShortWeight = 0.10;
    const std::optional<abm::Order> order =
        findNoiseOrder(abm::OrderType::SELL, cash, stock, 1.0, maxShortWeight);

    abm::test::expect(order.has_value(), "test setup should find a seeded noise sell order",
                      failures);
    if (!order.has_value()) {
        return;
    }

    const double wealth = cash + (stock * kMarketPrice);
    const double maximumSellQuantity = stock + (wealth * maxShortWeight / order->price);
    abm::test::expect(order->quantity <= maximumSellQuantity + 1e-10,
                      "noise trader sell quantity should respect the strategy short cap", failures);
}

} // namespace

namespace abm::test {

/*
 * The noise trader draws a uniform variate to pick which asset to quote. That
 * draw must not happen on a one-asset universe: choosing uniformly among one
 * candidate cannot change the choice, but consuming a variate would shift every
 * later belief shock on the agent's private stream and invalidate the
 * calibrated single-asset baselines.
 *
 * Comparing a *sequence* of orders is what makes this test bite — a single call
 * would still match if the two paths differed by one draw.
 */
void testNoiseTraderSingleAssetPathsAgree(int& failures) {
    constexpr std::uint64_t kSeed = 20260510U;
    constexpr int kSteps = 12;

    abm::Market market;
    initialiseMarket(market);

    abm::TradingOrderContext context;
    context.priceTickSize = 0.01;

    abm::Agent legacyAgent(1U, abm::AgentEndowment{10000.0, {5.0}}, abm::ProspectTheory{}, false);
    abm::NoiseTraderStrategy legacyStrategy(0, 0.05, 0.05, 0.30, kSeed);

    abm::AssetUniverse assets;
    assets.declare({abm::test::makeAssetDefinition(kAssetName, kMarketPrice, 5.0, 0.01, 0.01, 0.0,
                                                   1e-6)});
    const std::vector<double> prices{kMarketPrice};
    const abm::SymmetricMatrix covariance(1);
    const abm::MarketStepView marketView{prices, covariance, assets};

    abm::Agent viewAgent(1U, abm::AgentEndowment{10000.0, {5.0}}, abm::ProspectTheory{}, false);
    abm::NoiseTraderStrategy viewStrategy(0, 0.05, 0.05, 0.30, kSeed);

    bool sequencesAgree = true;
    bool anyOrderGenerated = false;
    for (int timeStep = 1; timeStep <= kSteps; ++timeStep) {
        const std::optional<abm::Order> expected =
            legacyStrategy.generateOrder(legacyAgent, market, timeStep, context);
        const std::vector<abm::Order> actual =
            viewStrategy.generateOrders(viewAgent, market, timeStep, context, marketView);

        if (expected.has_value() != (actual.size() == 1)) {
            sequencesAgree = false;
            break;
        }
        if (!expected.has_value()) {
            continue;
        }
        anyOrderGenerated = true;
        if (actual[0].type != expected->type ||
            !abm::test::nearlyEqual(actual[0].price, expected->price) ||
            !abm::test::nearlyEqual(actual[0].quantity, expected->quantity) ||
            actual[0].assetIndex != 0U) {
            sequencesAgree = false;
            break;
        }
    }

    abm::test::expect(anyOrderGenerated,
                      "noise-trader equivalence fixture should produce at least one order",
                      failures);
    abm::test::expect(sequencesAgree,
                      "noise-trader portfolio path should consume the private random stream "
                      "identically on a one-asset universe",
                      failures);
}

void runNoiseTraderStrategyTests(int& failures) {
    testNoiseTraderSingleAssetPathsAgree(failures);
    testNoiseTraderFirstOrderIsSeedDeterministic(failures);
    testNoiseTraderCanGenerateBuyAndSellOrdersFromSeededShocks(failures);
    testNoiseTraderTransactionCostHurdleSuppressesSmallBeliefShock(failures);
    testNoiseTraderBuyQuantityRespectsWealthFractionAndCash(failures);
    testNoiseTraderSellQuantityRespectsInventoryWhenShortCapIsZero(failures);
    testNoiseTraderSellQuantityRespectsStrategyShortCap(failures);
}

} // namespace abm::test
