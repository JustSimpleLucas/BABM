// FundamentalistStrategy.cpp

#include "AgentStrategy/FundamentalistStrategy.h"
#include "Agent/Agent.h"
#include "Agent/AgentAction.h"
#include "AgentStrategy/OrderSizing.h"
#include "AgentStrategy/PortfolioOptimizer.h"
#include "AgentStrategy/StrategyMarketHelpers.h"
#include "AgentStrategy/TradingStrategy.h"
#include "BehaviouralFinance/ProspectTheory.h"
#include "Market/Market.h"
#include "OrderBook/Order.h"
#include "OrderBook/OrderPricing.h"
#include "Utility/NumericValidation.h"
#include "Utility/SimulationConstants.h"
#include "Utility/TransactionCosts.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <optional>
#include <stdexcept>

namespace abm {
namespace {
constexpr double kDefaultMispricingThreshold = 0.02;
constexpr double kDefaultStopLossThreshold = 0.05;
constexpr double kDefaultTakeProfitThreshold = 0.10;
constexpr std::size_t kDefaultVolatilityWindow = 20;
constexpr double kDefaultRiskFreeRate = 0.0;

constexpr double kMinPosition = 1e-8;
} // namespace

FundamentalistStrategy::FundamentalistStrategy()
    : FundamentalistStrategy(FundamentalistStrategyParameters{}) {}

FundamentalistStrategy::FundamentalistStrategy(const FundamentalistStrategyParameters& parameters)
    : assetIndex_(parameters.assetIndex), allocationLine_(parameters.allocationLine),
      mispricingThreshold_(kDefaultMispricingThreshold),
      stopLossThreshold_(kDefaultStopLossThreshold),
      takeProfitThreshold_(kDefaultTakeProfitThreshold),
      volatilityWindow_(kDefaultVolatilityWindow), riskFreeRate_(kDefaultRiskFreeRate),
      referencePointMode_(parameters.referencePointMode),
      referenceMovingAverageWindow_(parameters.referenceMovingAverageWindow) {

    setMispricingThreshold(parameters.mispricingThreshold);
    setRiskThresholds(parameters.riskThresholds);
    setVolatilityWindow(parameters.volatilityWindow);
    setRiskFreeRate(parameters.riskFreeRate);
    requireStrictlyPositive(parameters.maxGrossExposure, "Max gross exposure");
    maxGrossExposure_ = parameters.maxGrossExposure;
    requireAtLeast(parameters.forecastHorizon, 1.0, "Forecast horizon");
    forecastHorizon_ = parameters.forecastHorizon;
}

std::string FundamentalistStrategy::strategyType() const {
    return "fundamentalist";
}

std::size_t FundamentalistStrategy::assetIndex() const {
    return assetIndex_;
}

void FundamentalistStrategy::setRiskFreeRate(double riskFreeRate) {
    requireFinite(riskFreeRate, "Risk-free rate");
    riskFreeRate_ = riskFreeRate;
}

double FundamentalistStrategy::riskFreeRate() const {
    return riskFreeRate_;
}

void FundamentalistStrategy::setMispricingThreshold(double threshold) {
    requireInHalfOpenUnitInterval(threshold, "Mispricing threshold");
    mispricingThreshold_ = threshold;
}

double FundamentalistStrategy::mispricingThreshold() const {
    return mispricingThreshold_;
}

void FundamentalistStrategy::setRiskThresholds(FundamentalistRiskThresholds thresholds) {
    requireInHalfOpenUnitInterval(thresholds.stopLossThreshold, "Stop-loss threshold");
    requireInHalfOpenUnitInterval(thresholds.takeProfitThreshold, "Take-profit threshold");
    stopLossThreshold_ = thresholds.stopLossThreshold;
    takeProfitThreshold_ = thresholds.takeProfitThreshold;
}

double FundamentalistStrategy::stopLossThreshold() const {
    return stopLossThreshold_;
}

double FundamentalistStrategy::takeProfitThreshold() const {
    return takeProfitThreshold_;
}

void FundamentalistStrategy::setVolatilityWindow(std::size_t window) {
    requirePositiveSize(window, "Volatility window");
    volatilityWindow_ = window;
}

std::size_t FundamentalistStrategy::volatilityWindow() const {
    return volatilityWindow_;
}

std::optional<Order> FundamentalistStrategy::generateOrder(Agent& agent, const Market& market,
                                                           int timeStep,
                                                           const TradingOrderContext& context) {
    const PriceInputs prices{strategy_detail::latestPositiveMarketPrice(market, assetIndex_),
                             strategy_detail::latestFiniteFundamentalPrice(market, assetIndex_)};
    agent.updateWealth(std::vector<double>{prices.marketPrice});

    const double transactionCostReturnHurdle =
        context.transactionCostAffectsDecisions
            ? transaction_costs::roundTripReturnHurdle(context.transactionCostRate)
            : 0.0;
    const SignalDecision decision = generateSignal(agent, prices, transactionCostReturnHurdle);
    if (!context.useValuationLimitPrice && decision.action == AgentAction::Hold) {
        return std::nullopt;
    }

    const double mispricingValue = mispricing(prices);
    const double sigma =
        strategy_detail::boundedLogReturnVolatility(market, assetIndex_, volatilityWindow_);
    const ProspectAdjustmentInputs prospectInputs{forecastExcessReturn(mispricingValue), sigma,
                                                  prices.marketPrice};
    const double horizonExcessReturn =
        prospectAdjustedHorizonReturn(agent, market, 0, prospectInputs);
    const double mu = riskFreeRate_ + (horizonExcessReturn / forecastHorizon_);
    const double riskyWeight = allocationLine_.optimalRiskyWeight(mu, riskFreeRate_, sigma);

    const double wealth = agent.getWealth();
    if (!(wealth > 0.0)) {
        return std::nullopt;
    }

    const OrderSizingInputs sizingInputs{
        prices, targetRiskyUnits(PortfolioSizingInputs{wealth, riskyWeight, prices.marketPrice,
                                                       decision.forceLiquidation})};
    const std::optional<OrderIntent> intent =
        context.useValuationLimitPrice
            ? buildValuationOrderIntent(agent, decision, sizingInputs, context)
            : buildSignalOrderIntent(agent, decision, sizingInputs, context);

    if (!intent.has_value() || intent->quantity <= kMinimumOrderQuantity) {
        return std::nullopt;
    }

    Order order = agent.generateOrder(intent->type, intent->price, intent->quantity);
    order.timeStep = timeStep;
    return order;
}

FundamentalistStrategy::SignalDecision
FundamentalistStrategy::generateSignal(const Agent& agent, const PriceInputs& prices,
                                       double transactionCostReturnHurdle) const {
    return generateSignalForPosition(prices, agent.getStock(0), agent.getAverageEntryPrice(0),
                                     transactionCostReturnHurdle);
}

FundamentalistStrategy::SignalDecision
FundamentalistStrategy::generateSignalForPosition(const PriceInputs& prices, double stock,
                                                  double averageEntryPrice,
                                                  double transactionCostReturnHurdle) const {
    if (stock > kMinPosition && std::isfinite(averageEntryPrice) &&
        averageEntryPrice > kMinimumPrice) {
        /*
         * Formula note:
         * pnl_ratio = (P_t - P_entry) / P_entry.
         *
         * The same realised gain/loss ratio triggers both stop-loss and
         * take-profit liquidation, making the risk-control assumption explicit.
         */
        const double pnlRatio = (prices.marketPrice - averageEntryPrice) / averageEntryPrice;
        if (pnlRatio <= -stopLossThreshold_) {
            return {AgentAction::Sell, true};
        }
        if (pnlRatio >= takeProfitThreshold_) {
            return {AgentAction::Sell, true};
        }
    }

    const double mispricingValue = mispricing(prices);
    const double effectiveMispricingThreshold =
        mispricingThreshold_ + std::max(0.0, transactionCostReturnHurdle);
    if (mispricingValue >= effectiveMispricingThreshold) {
        return {AgentAction::Buy, false};
    }
    if (mispricingValue <= -effectiveMispricingThreshold) {
        return {AgentAction::Sell, false};
    }
    return {AgentAction::Hold, false};
}

double FundamentalistStrategy::mispricing(const PriceInputs& prices) {
    if (!(prices.marketPrice >= kMinimumPrice)) {
        throw std::invalid_argument("Market price must be finite and at least the minimum price.");
    }
    requireFinite(prices.fundamentalPrice, "Fundamental price");

    /*
     * Formula note:
     * m_t = log(F_t / P_t).
     *
     * Positive m_t means the latent fundamental value is above the market
     * price, so the asset is treated as undervalued by fundamentalists. The
     * log form keeps the forecast commensurate with the log-return volatility
     * used by the mean-variance sizing rule.
     */
    return std::log(std::max(prices.fundamentalPrice, kMinimumPrice) / prices.marketPrice);
}

double FundamentalistStrategy::forecastExcessReturn(double mispricingValue) {
    /*
     * Formula note:
     * expected_excess_return = clamp(m_t, -1, 1).
     *
     * The clipping is numerical protection against extreme portfolio weights
     * when the simulated fundamental and market prices temporarily diverge.
     */
    return std::clamp(mispricingValue, -1.0, 1.0);
}

double FundamentalistStrategy::targetRiskyUnits(const PortfolioSizingInputs& inputs) {
    /*
     * Fundamentalist sizing remains long-only here; short exposure is handled
     * by chartist and noise-trader rules plus the global risk-control layer.
     */
    return strategy_detail::targetRiskyUnits(strategy_detail::TargetUnitsRequest{
        inputs.wealth, inputs.riskyWeight, inputs.marketPrice, true, inputs.forceLiquidation});
}

double FundamentalistStrategy::buyQuantity(const Agent& agent, const OrderSizingInputs& inputs,
                                           double orderPrice, double transactionCostRate) {
    return strategy_detail::buyQuantityTowardTarget(inputs.targetRiskyUnits, agent.getStock(0),
                                                    agent.getCash(), orderPrice,
                                                    transactionCostRate);
}

double FundamentalistStrategy::sellQuantity(const Agent& agent, const SignalDecision& decision,
                                            const OrderSizingInputs& inputs) {
    return strategy_detail::sellQuantityTowardTarget(inputs.targetRiskyUnits, agent.getStock(0),
                                                     decision.forceLiquidation, false);
}

std::optional<FundamentalistStrategy::OrderIntent>
FundamentalistStrategy::buildSignalOrderIntent(const Agent& agent, const SignalDecision& decision,
                                               const OrderSizingInputs& inputs,
                                               const TradingOrderContext& context) {
    const OrderType orderType =
        decision.action == AgentAction::Buy ? OrderType::BUY : OrderType::SELL;
    const double orderPrice =
        quantizeLimitPrice(inputs.prices.marketPrice, context.priceTickSize, orderType);
    const double quantity = orderType == OrderType::BUY ? buyQuantity(agent, inputs, orderPrice,
                                                                      context.transactionCostRate)
                                                        : sellQuantity(agent, decision, inputs);
    return {{orderType, orderPrice, quantity}};
}

std::optional<FundamentalistStrategy::OrderIntent>
FundamentalistStrategy::buildValuationOrderIntent(const Agent& agent,
                                                  const SignalDecision& decision,
                                                  const OrderSizingInputs& inputs,
                                                  const TradingOrderContext& context) {
    const double rawOrderPrice = std::max(
        kMinimumPrice, inputs.prices.fundamentalPrice *
                           std::exp(std::max(0.0, context.opinionKappa) * context.socialOpinion));

    /*
     * Formula note:
     * P_lim_raw = max(P_min, F_t * exp(kappa * o_i,t)).
     *
     * Social opinion shifts the valuation quote in log-price space, preserving
     * positive prices while allowing optimism and pessimism to move quotes
     * multiplicatively around the latent fundamental value.
     */
    const std::optional<strategy_detail::ValuationQuote> quote =
        strategy_detail::buildValuationQuote(
            strategy_detail::ValuationQuoteRequest{rawOrderPrice, inputs.prices.marketPrice,
                                                   decision.forceLiquidation},
            context);
    if (!quote.has_value()) {
        return std::nullopt;
    }

    const double quantity = quote->type == OrderType::BUY ? buyQuantity(agent, inputs, quote->price,
                                                                        context.transactionCostRate)
                                                          : sellQuantity(agent, decision, inputs);
    return {{quote->type, quote->price, quantity}};
}

double FundamentalistStrategy::prospectAdjustedHorizonReturn(
    Agent& agent, const Market& market, std::size_t assetIndex,
    const ProspectAdjustmentInputs& inputs) const {
    if (!agent.usesProspectTheory()) {
        return inputs.expectedExcessReturn;
    }

    const double referenceLogReturn = strategy_detail::resolveProspectReferenceReturn(
        agent, market, assetIndex, referencePointMode_, referenceMovingAverageWindow_,
        inputs.marketPrice);

    /*
     * The mispricing is the log return expected over the forecast horizon, so
     * CPT values the gamble over that same horizon, the agent's evaluation
     * period in the sense of Benartzi and Thaler (1995). Volatility grows with
     * the square root of the horizon (independent per-step returns), and cash,
     * the alternative the asset is valued against, earns the risk-free log
     * return for every step of it.
     */
    const ProspectReturnForecast forecast{
        inputs.expectedExcessReturn, inputs.volatility * std::sqrt(forecastHorizon_),
        referenceLogReturn, forecastHorizon_ * std::log1p(riskFreeRate_)};
    return std::clamp(agent.prospectTheory().prospectAdjustedReturn(forecast), -1.0, 1.0);
}

std::vector<Order> FundamentalistStrategy::generateOrders(Agent& agent, const Market& market,
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

    const double transactionCostReturnHurdle =
        context.transactionCostAffectsDecisions
            ? transaction_costs::roundTripReturnHurdle(context.transactionCostRate)
            : 0.0;

    /*
     * Per-asset CPT-adjusted mispricing forecasts feed one joint Markowitz
     * solve; the risk-management liquidation rule is evaluated per asset
     * against that asset's own average entry price.
     */
    std::vector<SignalDecision> decisions(assetCount);
    std::vector<PriceInputs> priceInputs(assetCount);
    std::vector<double> excessReturns(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        priceInputs[assetIndex] = PriceInputs{
            prices[assetIndex], strategy_detail::latestFiniteFundamentalPrice(market, assetIndex)};
        decisions[assetIndex] = generateSignalForPosition(
            priceInputs[assetIndex], agent.getStock(assetIndex),
            agent.getAverageEntryPrice(assetIndex), transactionCostReturnHurdle);

        const double sigma = std::sqrt(std::max(covariance.at(assetIndex, assetIndex),
                                                kMinimumVolatility * kMinimumVolatility));
        const ProspectAdjustmentInputs prospectInputs{
            forecastExcessReturn(mispricing(priceInputs[assetIndex])), sigma, prices[assetIndex]};
        /*
         * The Markowitz rule needs a per-step expected return, commensurate
         * with the per-step covariance (Merton, 1969). The mispricing is
         * expected to close over the forecast horizon, so it is spread over
         * that horizon (Chiarella, Iori and Perello, 2009); treating the whole
         * gap as a one-step return would push nearly every weight to its bound.
         */
        excessReturns[assetIndex] =
            prospectAdjustedHorizonReturn(agent, market, assetIndex, prospectInputs) /
            forecastHorizon_;
    }

    const std::vector<AssetWeightBounds> bounds(
        assetCount, AssetWeightBounds{std::max(0.0, allocationLine_.minRiskyWeight()),
                                      std::max(0.0, allocationLine_.maxRiskyWeight())});
    const std::vector<double> weights = optimalRiskyWeights(PortfolioInputs{
        &excessReturns, &covariance, allocationLine_.riskAversion(), &bounds, maxGrossExposure_});

    std::vector<Order> orders;
    orders.reserve(assetCount);
    double remainingCash = agent.getCash();
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        const SignalDecision& decision = decisions[assetIndex];
        const double targetUnits =
            strategy_detail::targetRiskyUnits(strategy_detail::TargetUnitsRequest{
                wealth, weights[assetIndex], prices[assetIndex], true, decision.forceLiquidation});

        TradingOrderContext assetContext = context;
        assetContext.priceTickSize = assets[assetIndex].priceTickSize;

        const double rawOrderPrice =
            std::max(kMinimumPrice,
                     priceInputs[assetIndex].fundamentalPrice *
                         std::exp(std::max(0.0, context.opinionKappa) * context.socialOpinion));
        const std::optional<strategy_detail::ValuationQuote> quote =
            strategy_detail::buildValuationQuote(
                strategy_detail::ValuationQuoteRequest{rawOrderPrice, prices[assetIndex],
                                                       decision.forceLiquidation},
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
                targetUnits, agent.getStock(assetIndex), decision.forceLiquidation, false);
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
