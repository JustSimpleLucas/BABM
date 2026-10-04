// NoiseTraderStrategy.cpp

#include "AgentStrategy/NoiseTraderStrategy.h"

#include "Agent/Agent.h"
#include "AgentStrategy/StrategyMarketHelpers.h"
#include "AgentStrategy/TradingStrategy.h"
#include "OrderBook/OrderPricing.h"
#include "Utility/NumericValidation.h"
#include "Utility/SimulationConstants.h"
#include "Utility/TransactionCosts.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <utility>

namespace abm {
namespace {
constexpr double kDefaultBeliefShockStdDev = 0.02;
constexpr double kDefaultOrderSizeFraction = 0.05;
constexpr double kDefaultMaxShortWeight = 0.30;
constexpr std::uint64_t kDefaultNoiseTraderSeed = 3141592653ULL;
constexpr double kMaximumLogQuoteShock = 20.0;
} // namespace

NoiseTraderStrategy::NoiseTraderStrategy()
    : assetIndex_(0), beliefShockStdDev_(kDefaultBeliefShockStdDev),
      orderSizeFraction_(kDefaultOrderSizeFraction), maxShortWeight_(kDefaultMaxShortWeight),
      random_(kDefaultNoiseTraderSeed) {}

NoiseTraderStrategy::NoiseTraderStrategy(std::size_t assetIndex, double beliefShockStdDev,
                                         double orderSizeFraction, double maxShortWeight,
                                         std::uint64_t seed)
    : assetIndex_(assetIndex), beliefShockStdDev_(kDefaultBeliefShockStdDev),
      orderSizeFraction_(kDefaultOrderSizeFraction), maxShortWeight_(kDefaultMaxShortWeight),
      random_(seed) {
    setBeliefShockStdDev(beliefShockStdDev);
    setOrderSizeFraction(orderSizeFraction);
    setMaxShortWeight(maxShortWeight);
}

std::string NoiseTraderStrategy::strategyType() const {
    return "noise_trader";
}

std::size_t NoiseTraderStrategy::assetIndex() const {
    return assetIndex_;
}

double NoiseTraderStrategy::beliefShockStdDev() const {
    return beliefShockStdDev_;
}

double NoiseTraderStrategy::orderSizeFraction() const {
    return orderSizeFraction_;
}

double NoiseTraderStrategy::maxShortWeight() const {
    return maxShortWeight_;
}

std::optional<Order> NoiseTraderStrategy::generateOrder(Agent& agent, const Market& market,
                                                        int timeStep,
                                                        const TradingOrderContext& context) {
    const double marketPrice = strategy_detail::latestPositiveMarketPrice(market, assetIndex_);
    agent.updateWealth(std::vector<double>{marketPrice});
    return generateOrderForAsset(agent, marketPrice, assetIndex_, timeStep, context);
}

std::vector<Order> NoiseTraderStrategy::generateOrders(Agent& agent, const Market& /*market*/,
                                                       int timeStep,
                                                       const TradingOrderContext& context,
                                                       const MarketStepView& marketView) {
    const AssetUniverse& assets = marketView.assets;
    const std::vector<double>& prices = marketView.latestPrices;
    agent.updateWealth(prices);

    /*
     * The traded asset is drawn uniformly from the private engine.
     *
     * The draw is skipped for a one-asset universe. Selecting uniformly from a
     * single candidate is a degenerate choice that cannot change the outcome,
     * but consuming a variate would shift every subsequent belief shock on this
     * agent's private stream and so would silently invalidate every calibrated
     * single-asset baseline. Skipping it keeps one code path for both cases
     * while leaving the single-asset stream bit-identical.
     */
    const std::size_t assetCount = assets.size();
    std::size_t assetIndex = 0;
    if (assetCount > 1) {
        const double uniformDraw = random_.generateUniformDist(0.0, 1.0);
        assetIndex =
            std::min(static_cast<std::size_t>(uniformDraw * static_cast<double>(assetCount)),
                     assetCount - 1);
    }

    TradingOrderContext assetContext = context;
    assetContext.priceTickSize = assets.at(assetIndex).priceTickSize;

    std::vector<Order> orders;
    std::optional<Order> order =
        generateOrderForAsset(agent, prices[assetIndex], assetIndex, timeStep, assetContext);
    if (order.has_value()) {
        orders.push_back(*order);
    }
    return orders;
}

std::optional<Order>
NoiseTraderStrategy::generateOrderForAsset(Agent& agent, double marketPrice, std::size_t assetIndex,
                                           int timeStep, const TradingOrderContext& context) {
    const double wealth = agent.getWealth();
    if (!(wealth > 0.0)) {
        return std::nullopt;
    }

    const double beliefShock = random_.generateNormalDist(0.0, beliefShockStdDev_);
    if (beliefShock == 0.0) {
        return std::nullopt;
    }

    /*
     * Formula note:
     * zeta_i,t ~ Normal(0, sigma_N^2),
     * P_lim_raw = P_t * exp(zeta_i,t).
     *
     * The sign of zeta_i,t determines order side, and the exponential maps the
     * random belief shock into a strictly positive quote.
     */
    const OrderType orderType = beliefShock > 0.0 ? OrderType::BUY : OrderType::SELL;
    const double boundedShock =
        std::clamp(beliefShock, -kMaximumLogQuoteShock, kMaximumLogQuoteShock);
    const double rawOrderPrice = std::max(kMinimumPrice, marketPrice * std::exp(boundedShock));
    const double orderPrice = quantizeLimitPrice(rawOrderPrice, context.priceTickSize, orderType);
    const double logGap = std::log(orderPrice / marketPrice);
    const double holdHurdle =
        std::max(0.0, context.holdTolerance) +
        (context.transactionCostAffectsDecisions
             ? transaction_costs::roundTripLogHurdle(context.transactionCostRate)
             : 0.0);
    if (std::abs(logGap) <= holdHurdle) {
        return std::nullopt;
    }

    /*
     * Formula note:
     * target_notional = W_i,t * phi_N,
     * q_i,t = target_notional / P_lim.
     */
    const double targetNotional = wealth * orderSizeFraction_;
    double quantity = targetNotional / orderPrice;

    if (orderType == OrderType::BUY) {
        const double affordableQuantity = transaction_costs::affordableBuyQuantity(
            agent.getCash(), orderPrice, context.transactionCostRate);
        quantity = std::min(quantity, affordableQuantity);
    } else {
        /*
         * The strategy-level short cap keeps random liquidity demand in an
         * interpretable range. The order book still applies the global
         * cash, inventory, margin, and borrowable-supply constraints.
         *
         * Formula note:
         * max_short_units = W_i,t * max_short_weight / P_lim.
         */
        const double maximumShortUnits = (wealth * maxShortWeight_) / orderPrice;
        const double maximumSellQuantity =
            std::max(0.0, agent.getStock(assetIndex) + maximumShortUnits);
        quantity = std::min(quantity, maximumSellQuantity);
    }

    if (quantity <= kMinimumOrderQuantity) {
        return std::nullopt;
    }

    Order order = agent.generateOrder(orderType, orderPrice, quantity);
    order.assetIndex = static_cast<std::uint32_t>(assetIndex);
    order.timeStep = timeStep;
    return order;
}

void NoiseTraderStrategy::setBeliefShockStdDev(double beliefShockStdDev) {
    requireStrictlyPositive(beliefShockStdDev, "Noise-trader belief shock stddev");
    beliefShockStdDev_ = beliefShockStdDev;
}

void NoiseTraderStrategy::setOrderSizeFraction(double orderSizeFraction) {
    requireInClosedUnitInterval(orderSizeFraction, "Noise-trader order size fraction");
    if (orderSizeFraction <= 0.0) {
        throw std::invalid_argument("Noise-trader order size fraction must be greater than 0.");
    }
    orderSizeFraction_ = orderSizeFraction;
}

void NoiseTraderStrategy::setMaxShortWeight(double maxShortWeight) {
    requireInClosedUnitInterval(maxShortWeight, "Noise-trader max short weight");
    maxShortWeight_ = maxShortWeight;
}

} // namespace abm
