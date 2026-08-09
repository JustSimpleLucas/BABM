// CovarianceEstimator.h

#ifndef MARKET_COVARIANCE_ESTIMATOR_H
#define MARKET_COVARIANCE_ESTIMATOR_H

#include <cstddef>

#include "Utility/CholeskyFactorization.h"

namespace abm {
class Market;

/**
 * Estimates the rolling sample covariance of per-asset one-period log returns.
 *
 * Returns are computed from the trailing stored market prices (warm-up history
 * included, so estimates exist from the first trading step). All assets use a
 * common trailing sample length: the smaller of `window` and the shortest
 * available return history, so the matrix stays internally consistent. With
 * fewer than two common observations the matrix is all zeros; callers must
 * regularize before factorization either way.
 */
[[nodiscard]] SymmetricMatrix estimateLogReturnCovariance(const Market& market,
                                                          std::size_t window);

} // namespace abm

#endif // MARKET_COVARIANCE_ESTIMATOR_H
