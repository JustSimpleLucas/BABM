// OrderSizing.cpp

#include "AgentStrategy/OrderSizing.h"

#include "OrderBook/OrderPricing.h"
#include "Utility/TransactionCosts.h"

#include <algorithm>
#include <cmath>

namespace abm::strategy_detail {
namespace {

[[nodiscard]] double holdLogHurdle(const TradingOrderContext& context) {
    return std::max(0.0, context.holdTolerance) +
           (context.transactionCostAffectsDecisions
                ? transaction_costs::roundTripLogHurdle(context.transactionCostRate)
                : 0.0);
}

} // namespace

double targetRiskyUnits(const TargetUnitsRequest& request) {
    if (request.forceLiquidation) {
        return 0.0;
    }

    /*
     * Formula note:
     * x*_i,t = W_i,t * w_i,t / P_t.
     *
     * Long-only strategies floor the target at zero; short-capable strategies
     * keep negative targets so the sell side can build short exposure.
     */
    const double target = (request.wealth * request.riskyWeight) / request.price;
    return request.longOnly ? std::max(0.0, target) : target;
}

double buyQuantityTowardTarget(double targetUnits, double currentStock, double availableCash,
                               double orderPrice, double transactionCostRate) {
    const double desiredBuyUnits = std::max(0.0, targetUnits - currentStock);
    const double affordableUnits =
        transaction_costs::affordableBuyQuantity(availableCash, orderPrice, transactionCostRate);
    return std::min(desiredBuyUnits, affordableUnits);
}

double sellQuantityTowardTarget(double targetUnits, double currentStock, bool forceLiquidation,
                                bool allowShort) {
    const double desiredSellUnits =
        forceLiquidation ? currentStock : std::max(0.0, currentStock - targetUnits);
    return allowShort ? desiredSellUnits : std::min(desiredSellUnits, currentStock);
}

std::optional<ValuationQuote> buildValuationQuote(const ValuationQuoteRequest& request,
                                                  const TradingOrderContext& context) {
    const double hurdle = holdLogHurdle(context);

    OrderType orderType = OrderType::SELL;
    if (!request.forceLiquidation) {
        const double logGap = std::log(request.rawOrderPrice / request.marketPrice);
        if (std::abs(logGap) <= hurdle) {
            return std::nullopt;
        }
        orderType = logGap > 0.0 ? OrderType::BUY : OrderType::SELL;
    }

    const double orderPrice =
        quantizeLimitPrice(request.rawOrderPrice, context.priceTickSize, orderType);
    if (!request.forceLiquidation) {
        const double quantizedLogGap = std::log(orderPrice / request.marketPrice);
        if (std::abs(quantizedLogGap) <= hurdle) {
            return std::nullopt;
        }
    }
    return ValuationQuote{orderType, orderPrice};
}

} // namespace abm::strategy_detail
