// ChartistStrategy.cpp

#include "AgentStrategy/ChartistStrategy.h"
#include "Agent/Agent.h"
#include "AgentStrategy/OrderSizing.h"
#include "AgentStrategy/PortfolioOptimizer.h"
#include "AgentStrategy/StrategyMarketHelpers.h"
#include "AgentStrategy/TradingStrategy.h"
#include "Market/Market.h"
#include "Utility/NumericValidation.h"
#include "Utility/OrderPricing.h"
#include "Utility/SimulationConstants.h"
#include "Utility/TransactionCosts.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace abm {

ChartistStrategy::ChartistStrategy(ChartistStrategyParameters parameters)
    : assetIndex_(parameters.assetIndex), allocationLine_(std::move(parameters.allocationLine)),
      volatilityWindow_(parameters.volatilityWindow), riskFreeRate_(0.0), maxShortWeight_(0.30),
      referencePointMode_(parameters.referencePointMode),
      referenceMovingAverageWindow_(parameters.referenceMovingAverageWindow) {
    setVolatilityWindow(parameters.volatilityWindow);
    setRiskFreeRate(parameters.riskFreeRate);
    setMaxShortWeight(parameters.maxShortWeight);
    requireStrictlyPositive(parameters.maxGrossExposure, "Max gross exposure");
    maxGrossExposure_ = parameters.maxGrossExposure;
}

std::size_t ChartistStrategy::assetIndex() const {
    return assetIndex_;
}

void ChartistStrategy::setRiskFreeRate(double riskFreeRate) {
    requireFinite(riskFreeRate, "Risk-free rate");
    riskFreeRate_ = riskFreeRate;
}

double ChartistStrategy::riskFreeRate() const {
    return riskFreeRate_;
}

void ChartistStrategy::setMaxShortWeight(double maxShortWeight) {
    requireInClosedUnitInterval(maxShortWeight, "Max short weight");
    maxShortWeight_ = maxShortWeight;
}

double ChartistStrategy::maxShortWeight() const {
    return maxShortWeight_;
}

void ChartistStrategy::setVolatilityWindow(std::size_t volatilityWindow) {
    requirePositiveSize(volatilityWindow, "Volatility window");
    volatilityWindow_ = volatilityWindow;
}

std::size_t ChartistStrategy::volatilityWindow() const {
    return volatilityWindow_;
}

std::optional<Order> ChartistStrategy::generateOrder(Agent& agent, const Market& market,
                                                     int timeStep,
                                                     const TradingOrderContext& context) {
    const AgentAction signal = generateSignal(market);
    if (!context.useValuationLimitPrice && signal == AgentAction::Hold) {
        return std::nullopt;
    }

    const double price = strategy_detail::latestPositiveMarketPrice(market, assetIndex_);
    agent.updateWealth(std::vector<double>{price});
    const double excessReturn = forecastExcessReturn(market, assetIndex_);
    const double sigma =
        strategy_detail::boundedLogReturnVolatility(market, assetIndex_, volatilityWindow_);
    const double behaviouralExcessReturn =
        prospectAdjustedExcessReturn(agent, market, assetIndex_, excessReturn, sigma, price);
    const double mu = riskFreeRate_ + behaviouralExcessReturn;
    const double rawRiskyWeight = allocationLine_.optimalRiskyWeight(mu, riskFreeRate_, sigma);
    /*
     * The effective lower bound is the tighter of the configured allocation
     * floor and the short-exposure cap, so both constraints bind independently.
     */
    const double riskyWeight =
        std::clamp(rawRiskyWeight, std::max(allocationLine_.minRiskyWeight(), -maxShortWeight_),
                   std::max(0.0, allocationLine_.maxRiskyWeight()));

    const double wealth = agent.getWealth();
    if (!(wealth > 0.0)) {
        return std::nullopt;
    }

    /*
     * Unlike the fundamentalist implementation, chartist sizing allows
     * negative target holdings when the configured short-weight bound permits
     * short selling.
     */
    const double targetRiskyUnits = strategy_detail::targetRiskyUnits(
        strategy_detail::TargetUnitsRequest{wealth, riskyWeight, price, false, false});
    double quantity = 0.0;
    OrderType orderType = OrderType::BUY;
    double orderPrice = price;

    if (!context.useValuationLimitPrice) {
        if (signal == AgentAction::Buy) {
            orderType = OrderType::BUY;
            quantity = strategy_detail::buyQuantityTowardTarget(targetRiskyUnits, agent.getStock(0),
                                                                agent.getCash(), price,
                                                                context.transactionCostRate);
        } else {
            orderType = OrderType::SELL;
            quantity = strategy_detail::sellQuantityTowardTarget(targetRiskyUnits,
                                                                 agent.getStock(0), false, true);
        }
        orderPrice = quantizeLimitPrice(orderPrice, context.priceTickSize, orderType);
    } else {
        /*
         * Formula note:
         * P_baseline = P_t * exp(expected_excess_return),
         * P_lim_raw = P_baseline * exp(kappa * o_i,t).
         *
         * The chartist forecast and the social-opinion signal are both applied
         * in log-price space, so the submitted valuation remains strictly
         * positive and reacts multiplicatively to optimism or pessimism.
         */
        const double baselinePrice =
            std::max(kMinimumPrice, price * std::exp(behaviouralExcessReturn));
        const double rawOrderPrice =
            std::max(kMinimumPrice, baselinePrice * std::exp(std::max(0.0, context.opinionKappa) *
                                                             context.socialOpinion));

        const std::optional<strategy_detail::ValuationQuote> quote =
            strategy_detail::buildValuationQuote(
                strategy_detail::ValuationQuoteRequest{rawOrderPrice, price, false}, context);
        if (!quote.has_value()) {
            return std::nullopt;
        }
        orderType = quote->type;
        orderPrice = quote->price;

        if (orderType == OrderType::BUY) {
            quantity = strategy_detail::buyQuantityTowardTarget(targetRiskyUnits, agent.getStock(0),
                                                                agent.getCash(), orderPrice,
                                                                context.transactionCostRate);
        } else {
            quantity = strategy_detail::sellQuantityTowardTarget(targetRiskyUnits,
                                                                 agent.getStock(0), false, true);
        }
    }

    if (quantity <= kMinimumOrderQuantity) {
        return std::nullopt;
    }

    Order order = agent.generateOrder(orderType, orderPrice, quantity);
    order.timeStep = timeStep;
    return order;
}

double ChartistStrategy::prospectAdjustedExcessReturn(Agent& agent, const Market& market,
                                                      std::size_t forecastAssetIndex,
                                                      double expectedExcessReturn,
                                                      double volatility, double marketPrice) const {
    if (!agent.usesProspectTheory()) {
        return expectedExcessReturn;
    }

    const double referenceLogReturn = strategy_detail::resolveProspectReferenceReturn(
        agent, market, forecastAssetIndex, referencePointMode_, referenceMovingAverageWindow_,
        marketPrice);
    const ProspectReturnForecast forecast{expectedExcessReturn, volatility, referenceLogReturn};
    return std::clamp(agent.prospectTheory().prospectAdjustedReturn(forecast), -1.0, 1.0);
}

std::vector<Order> ChartistStrategy::generateOrders(Agent& agent, const Market& market,
                                                    int timeStep,
                                                    const TradingOrderContext& context,
                                                    const MarketStepView& marketView) {
    const AssetUniverse& assets = marketView.assets;
    const std::vector<double>& prices = marketView.latestPrices;
    const SymmetricMatrix& covariance = marketView.covariance;
    const std::size_t assetCount = assets.size();

    agent.updateWealth(prices);
    const double wealth = agent.getWealth();
    if (!(wealth > 0.0)) {
        return {};
    }

    /*
     * The concrete technical rule is evaluated per asset; the CPT-adjusted
     * forecasts feed one joint Markowitz solve with the shared covariance.
     */
    std::vector<double> excessReturns(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        const double excessReturn = forecastExcessReturn(market, assetIndex);
        const double sigma = std::sqrt(std::max(covariance.at(assetIndex, assetIndex),
                                                kMinimumVolatility * kMinimumVolatility));
        excessReturns[assetIndex] = prospectAdjustedExcessReturn(
            agent, market, assetIndex, excessReturn, sigma, prices[assetIndex]);
    }

    const double lowerBound = std::max(allocationLine_.minRiskyWeight(), -maxShortWeight_);
    const std::vector<AssetWeightBounds> bounds(
        assetCount, AssetWeightBounds{lowerBound, std::max(0.0, allocationLine_.maxRiskyWeight())});
    const std::vector<double> weights = optimalRiskyWeights(PortfolioInputs{
        &excessReturns, &covariance, allocationLine_.riskAversion(), &bounds, maxGrossExposure_});

    std::vector<Order> orders;
    orders.reserve(assetCount);
    double remainingCash = agent.getCash();
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        const double targetUnits =
            strategy_detail::targetRiskyUnits(strategy_detail::TargetUnitsRequest{
                wealth, weights[assetIndex], prices[assetIndex], false, false});

        TradingOrderContext assetContext = context;
        assetContext.priceTickSize = assets[assetIndex].priceTickSize;

        const double baselinePrice =
            std::max(kMinimumPrice, prices[assetIndex] * std::exp(excessReturns[assetIndex]));
        const double rawOrderPrice =
            std::max(kMinimumPrice, baselinePrice * std::exp(std::max(0.0, context.opinionKappa) *
                                                             context.socialOpinion));
        const std::optional<strategy_detail::ValuationQuote> quote =
            strategy_detail::buildValuationQuote(
                strategy_detail::ValuationQuoteRequest{rawOrderPrice, prices[assetIndex], false},
                assetContext);
        if (!quote.has_value()) {
            continue;
        }

        double quantity = 0.0;
        if (quote->type == OrderType::BUY) {
            /*
             * Local cash budgeting keeps simultaneous buys across assets from
             * jointly overcommitting; the clearing engine still enforces the
             * hard affordability constraint at execution time.
             */
            quantity = strategy_detail::buyQuantityTowardTarget(
                targetUnits, agent.getStock(assetIndex), remainingCash, quote->price,
                context.transactionCostRate);
        } else {
            quantity = strategy_detail::sellQuantityTowardTarget(
                targetUnits, agent.getStock(assetIndex), false, true);
        }
        if (quantity <= kMinimumOrderQuantity) {
            continue;
        }

        Order order = agent.generateOrder(quote->type, quote->price, quantity);
        order.assetIndex = static_cast<std::uint32_t>(assetIndex);
        order.timeStep = timeStep;
        if (quote->type == OrderType::BUY) {
            remainingCash =
                std::max(0.0, remainingCash - (quote->price * quantity *
                                               (1.0 + std::max(0.0, context.transactionCostRate))));
        }
        orders.push_back(order);
    }
    return orders;
}

} // namespace abm
