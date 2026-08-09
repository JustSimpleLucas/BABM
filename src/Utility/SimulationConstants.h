// SimulationConstants.h

#ifndef SIMULATION_CONSTANTS_H
#define SIMULATION_CONSTANTS_H

#include <cstddef>

namespace abm {

/**
 * Lowest admissible positive price used when guarding against division by zero.
 *
 * This is a numerical safeguard rather than an economic price floor. Keeping
 * it centralised ensures that price formation, affordability checks, and batch
 * auction comparisons use the same tolerance.
 */
inline constexpr double kMinimumPrice = 1e-6;

/**
 * Smallest order quantity treated as economically executable by the simulator.
 *
 * Quantities below this threshold are ignored to prevent floating-point residue
 * from creating artificial trades in the batch auction.
 */
inline constexpr double kMinimumOrderQuantity = 1e-8;

/**
 * Smallest fill size, as a fraction of the requested match quantity, treated as
 * economic progress by the continuous matching loop.
 *
 * Binding cash, inventory, or short-sale constraints can permit fills that are
 * positive yet negligibly small relative to the quantities being matched. One
 * observed case: when aggregate short interest sits at the borrowable-supply
 * cap and a covering buyer meets a shorting seller, each fill releases exactly
 * as much borrow capacity as it consumes, so the permitted fill never changes
 * and a single order can take billions of iterations to complete. Fills below
 * this fraction of the requested quantity are treated as infeasible so the
 * starved side is cancelled instead of ground down in micro-fills.
 */
inline constexpr double kMinimumFillFraction = 1e-6;

/**
 * Hard upper bound on matching-loop iterations for one incoming order.
 *
 * Legitimate matching touches at most a few book levels per order; this cap is
 * far above that and exists only as a terminal safeguard so an unforeseen
 * constraint interaction degrades into a cancelled order rather than a hang.
 */
inline constexpr std::size_t kMaximumMatchIterationsPerOrder = 100000;

/**
 * Smallest realised-volatility estimate used in mean-variance allocation.
 *
 * The floor prevents division by zero in calm warm-up histories while keeping
 * the modelling assumption explicit and shared by all strategy families.
 */
inline constexpr double kMinimumVolatility = 1e-6;

/**
 * Largest per-step log-return standard deviation accepted for a geometric
 * fundamental process.
 *
 * Under geometric Brownian motion the fundamental shock is a per-step log
 * return, not a price increment. A value above this bound implies a per-step
 * volatility of more than 100%, which is not economically meaningful for a
 * fundamental value and almost always indicates that price-unit parameters
 * were copied from an arithmetic random-walk asset. Rejecting it converts a
 * silent misspecification into an explicit configuration error.
 */
inline constexpr double kMaximumGeometricProcessLogStdDev = 1.0;

/**
 * Default lookback period used by Relative Strength Index chartist signals.
 *
 * Fourteen periods is the standard Wilder-style RSI convention. Keeping the
 * period centralised ensures chartist signal generation and warm-up validation
 * require the same amount of pre-simulation price history.
 */
inline constexpr std::size_t kRelativeStrengthIndexPeriod = 14;

} // namespace abm

#endif // SIMULATION_CONSTANTS_H
