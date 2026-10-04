// OrderPricing.h

#ifndef ABM_ORDER_BOOK_ORDER_PRICING_H
#define ABM_ORDER_BOOK_ORDER_PRICING_H

#include "OrderBook/Order.h"

namespace abm {

/**
 * Quantises a limit order price to the configured market tick size.
 *
 * Buy orders are rounded down and sell orders are rounded up. This conservative
 * convention prevents tick rounding from making an agent more aggressive than
 * its behavioural signal intended, while still keeping submitted prices on the
 * market price grid.
 *
 * @param rawPrice Continuous price implied by the agent strategy.
 * @param tickSize Minimum admissible price increment. Non-positive or tiny tick
 *        sizes leave rawPrice unchanged.
 * @param side Order side used to choose conservative rounding direction.
 * @return Tick-aligned limit price, bounded below by one tick when quantisation
 *         is active.
 */
[[nodiscard]] double quantizeLimitPrice(double rawPrice, double tickSize, OrderType side);

} // namespace abm

#endif // ABM_ORDER_BOOK_ORDER_PRICING_H
