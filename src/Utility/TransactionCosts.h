// TransactionCosts.h

#ifndef UTILITY_TRANSACTION_COSTS_H
#define UTILITY_TRANSACTION_COSTS_H

#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>

namespace abm::transaction_costs {

/** Returns the validated proportional one-way cost rate used in calculations. */
[[nodiscard]] inline double costRate(double configuredRate) {
    return std::clamp(configuredRate, 0.0, 1.0 - kMinimumPrice);
}

/** Returns the cash cost paid by one side of an execution. */
[[nodiscard]] inline double oneSideCost(double price, double quantity, double configuredRate) {
    return costRate(configuredRate) * std::max(price, kMinimumPrice) * std::max(0.0, quantity);
}

/** Returns the trade notional before transaction costs. */
[[nodiscard]] inline double grossNotional(double price, double quantity) {
    return std::max(price, kMinimumPrice) * std::max(0.0, quantity);
}

/** Returns the quantity a buyer can fund when proportional costs are paid at execution. */
[[nodiscard]] inline double affordableBuyQuantity(double cash, double price,
                                                  double configuredRate) {
    const double unitCashCost = std::max(price, kMinimumPrice) * (1.0 + costRate(configuredRate));
    return std::max(0.0, cash) / unitCashCost;
}

/**
 * Returns the log-return hurdle for a round trip with symmetric proportional costs.
 *
 * Formula note:
 * h_log = log((1 + tau) / (1 - tau)).
 */
[[nodiscard]] inline double roundTripLogHurdle(double configuredRate) {
    const double tau = costRate(configuredRate);
    if (tau <= 0.0) {
        return 0.0;
    }
    return std::log((1.0 + tau) / (1.0 - tau));
}

/**
 * Returns the simple-return hurdle for a round trip with symmetric proportional costs.
 *
 * Formula note:
 * h_return = 2 tau / (1 - tau).
 */
[[nodiscard]] inline double roundTripReturnHurdle(double configuredRate) {
    const double tau = costRate(configuredRate);
    if (tau <= 0.0) {
        return 0.0;
    }
    return (2.0 * tau) / (1.0 - tau);
}

} // namespace abm::transaction_costs

#endif // UTILITY_TRANSACTION_COSTS_H
