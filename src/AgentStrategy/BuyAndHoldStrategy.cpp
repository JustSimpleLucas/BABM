// BuyAndHoldStrategy.cpp

#include "AgentStrategy/BuyAndHoldStrategy.h"

#include "Agent/Agent.h"
#include "AgentStrategy/StrategyMarketHelpers.h"
#include "Market/Market.h"
#include "Utility/NumericValidation.h"
#include "Utility/OrderPricing.h"
#include "Utility/SimulationConstants.h"
#include "Utility/TransactionCosts.h"

#include <algorithm>
#include <stdexcept>
#include <string>
#include <utility>

namespace abm {
namespace {
constexpr double kDefaultTargetRiskyWeight = 0.60;
} // namespace

BuyAndHoldStrategy::BuyAndHoldStrategy()
    : BuyAndHoldStrategy(0, kDefaultTargetRiskyWeight) {}

BuyAndHoldStrategy::BuyAndHoldStrategy(std::size_t assetIndex, double targetRiskyWeight)
    : assetIndex_(assetIndex), targetRiskyWeight_(kDefaultTargetRiskyWeight) {
    setTargetRiskyWeight(targetRiskyWeight);
}

std::string BuyAndHoldStrategy::strategyType() const {
    return "buy_and_hold";
}

std::size_t BuyAndHoldStrategy::assetIndex() const {
    return assetIndex_;
}

double BuyAndHoldStrategy::targetRiskyWeight() const {
    return targetRiskyWeight_;
}

void BuyAndHoldStrategy::setTargetRiskyWeight(double targetRiskyWeight) {
    requireInClosedUnitInterval(targetRiskyWeight, "Buy-and-hold target risky weight");
    if (targetRiskyWeight <= 0.0) {
        throw std::invalid_argument("Buy-and-hold target risky weight must be greater than 0.");
    }
    targetRiskyWeight_ = targetRiskyWeight;
}

std::optional<Order> BuyAndHoldStrategy::generateOrder(Agent& agent, const Market& market,
                                                       int timeStep,
                                                       const TradingOrderContext& context) {
    const double marketPrice = strategy_detail::latestPositiveMarketPrice(market, assetIndex_);
    agent.updateWealth(std::vector<double>{marketPrice});

    const double wealth = agent.getWealth();
    if (!(wealth > 0.0)) {
        return std::nullopt;
    }

    /*
     * Formula note:
     * x*_i,t = W_i,t * omega_BH / P_t.
     *
     * The rule uses current mark-to-market wealth and the latest traded price
     * to express a passive desired risky-asset weight. It is intentionally
     * long-only and does not rebalance downward after the target is reached.
     */
    const double targetRiskyUnits = (wealth * targetRiskyWeight_) / marketPrice;
    const double desiredBuyUnits = std::max(0.0, targetRiskyUnits - agent.getStock(0));
    if (desiredBuyUnits <= kMinimumOrderQuantity) {
        return std::nullopt;
    }

    const double orderPrice = quantizeLimitPrice(marketPrice, context.priceTickSize,
                                                 OrderType::BUY);
    const double affordableUnits = transaction_costs::affordableBuyQuantity(
        agent.getCash(), orderPrice, context.transactionCostRate);
    const double quantity = std::min(desiredBuyUnits, affordableUnits);
    if (quantity <= kMinimumOrderQuantity) {
        return std::nullopt;
    }

    Order order = agent.generateOrder(OrderType::BUY, orderPrice, quantity);
    order.timeStep = timeStep;
    return order;
}

std::vector<Order> BuyAndHoldStrategy::generateOrders(Agent& agent, const Market& /*market*/,
                                                      int timeStep,
                                                      const TradingOrderContext& context,
                                                      const MarketStepView& marketView) {
    const AssetUniverse& assets = marketView.assets;
    const std::vector<double>& prices = marketView.latestPrices;
    agent.updateWealth(prices);

    const double wealth = agent.getWealth();
    if (!(wealth > 0.0)) {
        return {};
    }

    /*
     * Formula note:
     * x*_i,j,t = W_i,t * (omega_BH / N) / P_j,t.
     *
     * The passive target weight is split equally across assets; the rule stays
     * long-only and never rebalances downward after a target is reached.
     */
    const double perAssetWeight = targetRiskyWeight_ / static_cast<double>(assets.size());
    std::vector<Order> orders;
    double remainingCash = agent.getCash();
    for (std::size_t assetIndex = 0; assetIndex < assets.size(); ++assetIndex) {
        const double targetUnits = (wealth * perAssetWeight) / prices[assetIndex];
        const double desiredBuyUnits =
            std::max(0.0, targetUnits - agent.getStock(assetIndex));
        if (desiredBuyUnits <= kMinimumOrderQuantity) {
            continue;
        }

        const double orderPrice = quantizeLimitPrice(
            prices[assetIndex], assets[assetIndex].priceTickSize, OrderType::BUY);
        const double affordableUnits = transaction_costs::affordableBuyQuantity(
            remainingCash, orderPrice, context.transactionCostRate);
        const double quantity = std::min(desiredBuyUnits, affordableUnits);
        if (quantity <= kMinimumOrderQuantity) {
            continue;
        }

        Order order = agent.generateOrder(OrderType::BUY, orderPrice, quantity);
        order.assetIndex = static_cast<std::uint32_t>(assetIndex);
        order.timeStep = timeStep;
        remainingCash = std::max(
            0.0, remainingCash - (orderPrice * quantity *
                                  (1.0 + std::max(0.0, context.transactionCostRate))));
        orders.push_back(order);
    }
    return orders;
}

} // namespace abm
