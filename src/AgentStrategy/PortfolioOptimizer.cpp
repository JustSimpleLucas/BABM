// PortfolioOptimizer.cpp

#include "AgentStrategy/PortfolioOptimizer.h"

#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace abm {
namespace {

constexpr double kInitialDiagonalLoading = 1e-6;
constexpr int kMaximumRegularizationRetries = 3;

[[nodiscard]] std::vector<double> clampToBounds(std::vector<double> weights,
                                                const std::vector<AssetWeightBounds>& bounds) {
    for (std::size_t assetIndex = 0; assetIndex < weights.size(); ++assetIndex) {
        const AssetWeightBounds& interval = bounds[assetIndex];
        weights[assetIndex] = std::clamp(weights[assetIndex], interval.minWeight,
                                         interval.maxWeight);
    }
    return weights;
}

} // namespace

std::vector<double> optimalRiskyWeights(const PortfolioInputs& inputs) {
    if (inputs.expectedExcessReturns == nullptr || inputs.covariance == nullptr ||
        inputs.bounds == nullptr) {
        throw std::invalid_argument("Portfolio inputs must supply returns, covariance, bounds.");
    }
    const std::vector<double>& expectedExcessReturns = *inputs.expectedExcessReturns;
    const std::size_t assetCount = expectedExcessReturns.size();
    if (inputs.covariance->size != assetCount || inputs.bounds->size() != assetCount) {
        throw std::invalid_argument("Portfolio input dimensions must agree.");
    }
    if (!(inputs.riskAversion > 0.0)) {
        throw std::invalid_argument("Risk aversion must be strictly positive.");
    }
    if (assetCount == 0) {
        return {};
    }

    const double varianceFloor = kMinimumVolatility * kMinimumVolatility;

    std::vector<double> rhs(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        rhs[assetIndex] = expectedExcessReturns[assetIndex] / inputs.riskAversion;
    }

    std::vector<double> weights;
    bool solved = false;
    double diagonalLoading = 0.0;
    for (int attempt = 0; attempt <= kMaximumRegularizationRetries; ++attempt) {
        SymmetricMatrix factor = *inputs.covariance;
        regularizeCovariance(factor, varianceFloor, diagonalLoading);
        if (choleskyFactorize(factor)) {
            weights = choleskySolve(factor, rhs);
            solved = std::all_of(weights.begin(), weights.end(),
                                 [](double weight) { return std::isfinite(weight); });
            if (solved) {
                break;
            }
        }
        diagonalLoading =
            diagonalLoading == 0.0 ? kInitialDiagonalLoading : diagonalLoading * 10.0;
    }

    if (!solved) {
        /*
         * Diagonal fallback: ignore covariances and apply the historical
         * scalar rule per asset, w_j = mu_j / (rho * sigma_j^2).
         */
        weights.assign(assetCount, 0.0);
        for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
            const double variance =
                std::max(inputs.covariance->at(assetIndex, assetIndex), varianceFloor);
            weights[assetIndex] = expectedExcessReturns[assetIndex] /
                                  (inputs.riskAversion * variance);
        }
    }

    weights = clampToBounds(std::move(weights), *inputs.bounds);

    if (inputs.maxGrossExposure > 0.0) {
        double grossExposure = 0.0;
        for (const double weight : weights) {
            grossExposure += std::abs(weight);
        }
        if (grossExposure > inputs.maxGrossExposure) {
            const double scale = inputs.maxGrossExposure / grossExposure;
            for (double& weight : weights) {
                weight *= scale;
            }
            weights = clampToBounds(std::move(weights), *inputs.bounds);
        }
    }
    return weights;
}

} // namespace abm
