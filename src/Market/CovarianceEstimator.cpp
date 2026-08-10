// CovarianceEstimator.cpp

#include "Market/CovarianceEstimator.h"

#include "Market/Market.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>

namespace abm {

SymmetricMatrix estimateLogReturnCovariance(const Market& market, std::size_t window) {
    const std::size_t assetCount = market.assetCount();
    SymmetricMatrix covariance(assetCount);
    if (assetCount == 0 || window < 2) {
        return covariance;
    }

    // Common trailing sample length across assets keeps the matrix consistent.
    std::size_t sampleLength = window;
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        const std::vector<double>& prices = market.getMarketValues(assetIndex);
        const std::size_t availableReturns = prices.size() > 1 ? prices.size() - 1 : 0;
        sampleLength = std::min(sampleLength, availableReturns);
    }
    if (sampleLength < 2) {
        return covariance;
    }

    std::vector<std::vector<double>> logReturns(assetCount, std::vector<double>(sampleLength, 0.0));
    std::vector<double> means(assetCount, 0.0);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        const std::vector<double>& prices = market.getMarketValues(assetIndex);
        const std::size_t priceCount = prices.size();
        for (std::size_t sampleIndex = 0; sampleIndex < sampleLength; ++sampleIndex) {
            const std::size_t laterIndex = priceCount - sampleLength + sampleIndex;
            const double later = std::max(prices[laterIndex], kMinimumPrice);
            const double earlier = std::max(prices[laterIndex - 1], kMinimumPrice);
            const double logReturn = std::log(later / earlier);
            logReturns[assetIndex][sampleIndex] = logReturn;
            means[assetIndex] += logReturn;
        }
        means[assetIndex] /= static_cast<double>(sampleLength);
    }

    /*
     * Formula note:
     * Sigma_jk = sum_t (r_j,t - mean_j)(r_k,t - mean_k) / (T - 1).
     */
    const double divisor = static_cast<double>(sampleLength - 1);
    for (std::size_t rowAsset = 0; rowAsset < assetCount; ++rowAsset) {
        for (std::size_t columnAsset = rowAsset; columnAsset < assetCount; ++columnAsset) {
            double sum = 0.0;
            for (std::size_t sampleIndex = 0; sampleIndex < sampleLength; ++sampleIndex) {
                sum += (logReturns[rowAsset][sampleIndex] - means[rowAsset]) *
                       (logReturns[columnAsset][sampleIndex] - means[columnAsset]);
            }
            const double value = sum / divisor;
            covariance.at(rowAsset, columnAsset) = value;
            covariance.at(columnAsset, rowAsset) = value;
        }
    }
    return covariance;
}

} // namespace abm
