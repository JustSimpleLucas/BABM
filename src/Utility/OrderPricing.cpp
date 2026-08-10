// OrderPricing.cpp

#include "Utility/OrderPricing.h"

#include <algorithm>
#include <cmath>

namespace abm {
namespace {
constexpr double kMinTickSize = 1e-12;
} // namespace

double quantizeLimitPrice(double rawPrice, double tickSize, OrderType side) {
    if (tickSize <= kMinTickSize) {
        return rawPrice;
    }

    const double scaled = rawPrice / tickSize;
    /*
     * Formula note:
     * buy quote:  P_lim = floor(P_raw / delta) * delta,
     * sell quote: P_lim = ceil(P_raw / delta) * delta.
     *
     * Rounding buys down and sells up avoids submitting a tick-quantised quote
     * that is more aggressive than the strategy's raw valuation.
     */
    const double quantized = side == OrderType::BUY ? std::floor(scaled + kMinTickSize) * tickSize
                                                    : std::ceil(scaled - kMinTickSize) * tickSize;
    return std::max(tickSize, quantized);
}

} // namespace abm
