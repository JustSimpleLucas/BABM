#include "tests/TestSupport.h"

#include "Agent/Agent.h"
#include "AgentStrategy/BuyAndHoldStrategy.h"
#include "AgentStrategy/TradingStrategy.h"
#include "BehaviouralFinance/ProspectTheory.h"
#include "ControlParameters/MarketConfig.h"
#include "Market/Market.h"
#include "Utility/CholeskyFactorization.h"

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

std::optional<abm::Order> generateBuyAndHoldOrder(double cash, double stock,
                                                  double targetRiskyWeight,
                                                  double priceTickSize = 0.01,
                                                  double transactionCostRate = 0.0) {
    abm::Market market;
    initialiseMarket(market);
    abm::Agent agent(1U, abm::AgentEndowment{cash, {stock}}, abm::ProspectTheory{}, false);
    abm::BuyAndHoldStrategy strategy(0, targetRiskyWeight);
    abm::TradingOrderContext context;
    context.socialOpinion = 0.75;
    context.opinionKappa = 2.0;
    context.holdTolerance = 0.5;
    context.priceTickSize = priceTickSize;
    context.transactionCostRate = transactionCostRate;
    return strategy.generateOrder(agent, market, 7, context);
}

void testBuyAndHoldBuysWhenBelowTarget(int& failures) {
    const std::optional<abm::Order> order = generateBuyAndHoldOrder(1000.0, 0.0, 0.60);

    abm::test::expect(order.has_value(),
                      "buy-and-hold should buy when risky exposure is below target", failures);
    if (!order.has_value()) {
        return;
    }

    abm::test::expect(order->type == abm::OrderType::BUY,
                      "buy-and-hold should only submit buy orders", failures);
    abm::test::expect(abm::test::nearlyEqual(order->quantity, 6.0),
                      "buy-and-hold should size the buy from target risky weight", failures);
    abm::test::expect(abm::test::nearlyEqual(order->price, kMarketPrice),
                      "buy-and-hold should quote at the latest market price on-grid", failures);
    abm::test::expect(order->timeStep == 7,
                      "buy-and-hold should preserve the simulation time step on orders", failures);
}

void testBuyAndHoldBuysFullRemainingGap(int& failures) {
    const std::optional<abm::Order> order = generateBuyAndHoldOrder(1000.0, 2.0, 0.60);

    abm::test::expect(order.has_value(),
                      "buy-and-hold should continue buying while below target", failures);
    if (order.has_value()) {
        abm::test::expect(abm::test::nearlyEqual(order->quantity, 5.2),
                          "buy-and-hold should buy the full remaining target gap", failures);
    }
}

void testBuyAndHoldRespectsCashConstraint(int& failures) {
    const std::optional<abm::Order> order = generateBuyAndHoldOrder(1000.0, 0.0, 1.0, 200.0);

    abm::test::expect(order.has_value(),
                      "test setup should produce a cash-constrained buy-and-hold order",
                      failures);
    if (order.has_value()) {
        abm::test::expect(abm::test::nearlyEqual(order->price, 200.0),
                          "coarse tick should quantize the buy quote to the minimum tick",
                          failures);
        abm::test::expect(abm::test::nearlyEqual(order->quantity, 5.0),
                          "buy-and-hold should not buy more than available cash can fund",
                          failures);
    }
}

void testBuyAndHoldAffordabilityIncludesTransactionCost(int& failures) {
    const std::optional<abm::Order> order =
        generateBuyAndHoldOrder(1010.0, 0.0, 1.0, 100.0, 0.01);

    abm::test::expect(order.has_value(),
                      "test setup should produce a transaction-cost constrained buy order",
                      failures);
    if (order.has_value()) {
        abm::test::expect(abm::test::nearlyEqual(order->quantity, 10.0),
                          "buy-and-hold affordability should reserve cash for transaction cost",
                          failures);
    }
}

void testBuyAndHoldUsesTickQuantizedBuyPrice(int& failures) {
    const std::optional<abm::Order> order = generateBuyAndHoldOrder(1000.0, 0.0, 0.60, 0.30);

    abm::test::expect(order.has_value(), "test setup should produce a tick-quantized order",
                      failures);
    if (order.has_value()) {
        abm::test::expect(abm::test::nearlyEqual(order->price, 99.90),
                          "buy-and-hold should use conservative buy-side tick quantization",
                          failures);
    }
}

void testBuyAndHoldDoesNotTradeAtOrAboveTarget(int& failures) {
    const std::optional<abm::Order> atTarget = generateBuyAndHoldOrder(1000.0, 15.0, 0.60);
    const std::optional<abm::Order> aboveTarget = generateBuyAndHoldOrder(1000.0, 30.0, 0.60);

    abm::test::expect(!atTarget.has_value(),
                      "buy-and-hold should submit no order once target exposure is reached",
                      failures);
    abm::test::expect(!aboveTarget.has_value(),
                      "buy-and-hold should never sell after overshooting the target", failures);
}

} // namespace

namespace abm::test {

/*
 * A one-asset universe must be the degenerate case of the portfolio rule, not a
 * separate routine. Before this was unified, generateOrders delegated to the
 * single-asset generateOrder whenever the universe held one asset, so a
 * one-asset run and a two-asset run executed different code. This pins the two
 * against each other so the split cannot silently return.
 */
void testBuyAndHoldSingleAssetPathsAgree(int& failures) {
    abm::Market market;
    initialiseMarket(market);

    abm::TradingOrderContext context;
    context.priceTickSize = 0.01;

    abm::Agent legacyAgent(1U, abm::AgentEndowment{1000.0, {0.0}}, abm::ProspectTheory{}, false);
    abm::BuyAndHoldStrategy legacyStrategy(0, 0.60);
    const std::optional<abm::Order> expected =
        legacyStrategy.generateOrder(legacyAgent, market, 7, context);

    abm::AssetUniverse assets;
    assets.declare({abm::test::makeAssetDefinition(kAssetName, kMarketPrice, 0.0, 0.01, 0.01, 0.0,
                                                   1e-6)});
    const std::vector<double> prices{kMarketPrice};
    const abm::SymmetricMatrix covariance(1);
    const abm::MarketStepView marketView{prices, covariance, assets};

    abm::Agent viewAgent(1U, abm::AgentEndowment{1000.0, {0.0}}, abm::ProspectTheory{}, false);
    abm::BuyAndHoldStrategy viewStrategy(0, 0.60);
    const std::vector<abm::Order> actual =
        viewStrategy.generateOrders(viewAgent, market, 7, context, marketView);

    abm::test::expect(expected.has_value() == (actual.size() == 1),
                      "buy-and-hold should trade or hold identically on a one-asset universe",
                      failures);
    if (!expected.has_value() || actual.size() != 1) {
        return;
    }

    abm::test::expect(actual[0].type == expected->type &&
                          abm::test::nearlyEqual(actual[0].price, expected->price) &&
                          abm::test::nearlyEqual(actual[0].quantity, expected->quantity) &&
                          actual[0].assetIndex == 0U && actual[0].timeStep == expected->timeStep,
                      "buy-and-hold portfolio path should reproduce the single-asset order exactly",
                      failures);
}

void runBuyAndHoldStrategyTests(int& failures) {
    testBuyAndHoldSingleAssetPathsAgree(failures);
    testBuyAndHoldBuysWhenBelowTarget(failures);
    testBuyAndHoldBuysFullRemainingGap(failures);
    testBuyAndHoldRespectsCashConstraint(failures);
    testBuyAndHoldAffordabilityIncludesTransactionCost(failures);
    testBuyAndHoldUsesTickQuantizedBuyPrice(failures);
    testBuyAndHoldDoesNotTradeAtOrAboveTarget(failures);
}

} // namespace abm::test
