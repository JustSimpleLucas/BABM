// OrderSizing.h

#ifndef ABM_AGENT_STRATEGY_ORDER_SIZING_H
#define ABM_AGENT_STRATEGY_ORDER_SIZING_H

#include <optional>

#include "AgentStrategy/TradingStrategy.h"
#include "OrderBook/Order.h"

namespace abm::strategy_detail {

/**
 * Inputs for converting a risky portfolio weight into target holdings.
 *
 * Long-only strategies floor the target at zero; strategies with short
 * exposure allow negative targets. Forced liquidation always targets a flat
 * position regardless of the computed weight.
 */
struct TargetUnitsRequest {
    double wealth{0.0};
    double riskyWeight{0.0};
    double price{0.0};
    bool longOnly{false};
    bool forceLiquidation{false};
};

/** Returns the target risky holding x* = W * w / P subject to the request flags. */
[[nodiscard]] double targetRiskyUnits(const TargetUnitsRequest& request);

/**
 * Returns the buy quantity that moves holdings toward the target without
 * exceeding cost-inclusive affordability at the quoted price.
 */
[[nodiscard]] double buyQuantityTowardTarget(double targetUnits, double currentStock,
                                             double availableCash, double orderPrice,
                                             double transactionCostRate);

/**
 * Returns the sell quantity that moves holdings toward the target.
 *
 * Long-only strategies cap the sale at current holdings; short-capable
 * strategies may sell beyond holdings, with execution-time risk controls
 * enforcing the hard short-sale constraints.
 */
[[nodiscard]] double sellQuantityTowardTarget(double targetUnits, double currentStock,
                                              bool forceLiquidation, bool allowShort);

/** Inputs for turning a raw valuation quote into a side, price, and hold decision. */
struct ValuationQuoteRequest {
    double rawOrderPrice{0.0};
    double marketPrice{0.0};
    bool forceLiquidation{false};
};

/** Order side and tick-quantised limit price implied by a valuation quote. */
struct ValuationQuote {
    OrderType type{OrderType::SELL};
    double price{0.0};
};

/**
 * Applies the shared valuation-path quoting rule: log-gap side selection, the
 * hold band (tolerance plus optional round-trip cost hurdle), tick
 * quantisation, and the post-quantisation hold re-check. Forced liquidation
 * bypasses the hold band and always sells.
 *
 * @return The side and quantised price, or std::nullopt when the quote falls
 * inside the hold band.
 */
[[nodiscard]] std::optional<ValuationQuote>
buildValuationQuote(const ValuationQuoteRequest& request, const TradingOrderContext& context);

} // namespace abm::strategy_detail

#endif // ABM_AGENT_STRATEGY_ORDER_SIZING_H
