// AllocativeEfficiency.h

#ifndef ANALYSIS_ALLOCATIVE_EFFICIENCY_H
#define ANALYSIS_ALLOCATIVE_EFFICIENCY_H

#include <vector>

#include "OrderBook/Order.h"

namespace abm {

/**
 * Order-side reservation value used to evaluate double-auction efficiency.
 *
 * In the current continuous double-auction model, strategy-generated limit
 * prices are treated as the best observable proxy for each agent's willingness
 * to pay or willingness to accept. This follows the Smith-style experimental
 * double-auction convention while keeping transaction costs as a separate
 * institutional friction diagnostic.
 */
struct AllocativeEfficiencyOrder {
    OrderType side{OrderType::BUY};
    double reservationPrice{0.0};
    double quantity{0.0};
};

/** Executed buyer-seller pair used to calculate realised gross surplus. */
struct AllocativeEfficiencyTrade {
    double buyerReservationPrice{0.0};
    double sellerReservationPrice{0.0};
    double quantity{0.0};
};

/** Gross allocative-efficiency diagnostics for one double-auction step. */
struct AllocativeEfficiencyResult {
    double realizedSurplus{0.0};
    double maximumSurplus{0.0};
    double efficiency{0.0};
};

/**
 * Calculates the maximum positive gross surplus available in an order set.
 *
 * Buy orders are sorted from highest to lowest reservation value and sell orders
 * from lowest to highest reservation value. The greedy matching rule is
 * equivalent to pairing the highest marginal buyer with the lowest marginal
 * seller until the next pair no longer has positive surplus.
 */
[[nodiscard]] double
calculateMaximumAllocativeSurplus(std::vector<AllocativeEfficiencyOrder> orders);

/** Calculates realised gross surplus from executed buyer-seller pairs. */
[[nodiscard]] double
calculateRealizedAllocativeSurplus(const std::vector<AllocativeEfficiencyTrade>& trades);

/** Combines realised and maximum surplus into an efficiency ratio. */
[[nodiscard]] AllocativeEfficiencyResult
calculateAllocativeEfficiency(std::vector<AllocativeEfficiencyOrder> orders,
                              const std::vector<AllocativeEfficiencyTrade>& trades);

} // namespace abm

#endif // ANALYSIS_ALLOCATIVE_EFFICIENCY_H
