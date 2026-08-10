// Market/FundamentalValueProcess.cpp

#include "Market/FundamentalValueProcess.h"

#include "Utility/NumericValidation.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>

namespace abm {
namespace {

/**
 * Seed used when no experiment seed is supplied.
 *
 * Only default-constructed processes use it; SimulationEngine always passes the
 * configured run seed.
 */
constexpr std::uint64_t kDefaultFundamentalProcessSeed = 42U;

void validateFundamentalProcess(double driftPerStep, double shockStdDev, double minimumValue) {
    requireFinite(driftPerStep, "Fundamental drift per step");
    requireNonNegative(shockStdDev, "Fundamental shock stddev");
    requireStrictlyPositive(minimumValue, "Minimum fundamental value");
}

/** Returns the latest stored fundamental value, or throws when none exists. */
[[nodiscard]] double latestFundamental(const Market& market, std::size_t assetIndex) {
    const std::vector<double>& history = market.getTrueValues(assetIndex);
    if (history.empty()) {
        throw std::out_of_range(
            "Cannot generate fundamental value without an initial true value for asset " +
            market.assetLabel(assetIndex) + '.');
    }
    return history.back();
}

/**
 * Maps independent standard normals to equicorrelated standard normals.
 *
 * Uses the closed-form one-factor square root of the equicorrelation matrix R
 * (unit diagonal, `pairwiseCorrelation` off-diagonal):
 *
 *   zeta_j = a * z_j + b * sum_k z_k,
 *   a = sqrt(1 - rho),
 *   b = (sqrt(1 + (n - 1) * rho) - a) / n.
 *
 * Writing B for this linear map, B * B^T = R exactly, so zeta has unit
 * variances and pairwise correlation rho. Unlike a Cholesky factorization it
 * remains well defined on the positive-semi-definite boundary, where R is
 * singular and Cholesky fails.
 *
 * @param independentDraws Independent standard normals, one per asset.
 * @param pairwiseCorrelation Correlation applied to every distinct pair.
 * @return Correlated standard normals, parallel to independentDraws.
 *
 * @throws std::invalid_argument when rho is below -1/(n-1), the point at which
 *         the equicorrelation matrix stops being positive semi-definite and no
 *         such joint distribution exists.
 */
[[nodiscard]] std::vector<double>
correlateStandardNormals(const std::vector<double>& independentDraws, double pairwiseCorrelation) {
    const std::size_t assetCount = independentDraws.size();

    /*
     * A single asset has no pair to correlate, and zero correlation is already
     * the identity map. Short-circuiting both keeps the returned draws
     * bit-identical to the independent ones, which is what preserves the
     * frozen single-asset baseline exactly.
     */
    if (assetCount <= 1 || pairwiseCorrelation == 0.0) {
        return independentDraws;
    }

    /*
     * The equicorrelation matrix has eigenvalues 1 + (n-1)*rho (once) and
     * 1 - rho (n-1 times), so it is positive semi-definite exactly on
     * rho in [-1/(n-1), 1]. Below that bound the requested correlation is not
     * attainable by any joint distribution.
     */
    const double lowerBound = -1.0 / static_cast<double>(assetCount - 1);
    if (pairwiseCorrelation < lowerBound) {
        throw std::invalid_argument(
            "Asset fundamental correlation " + std::to_string(pairwiseCorrelation) + " with " +
            std::to_string(assetCount) +
            " assets is not positive semi-definite; the minimum attainable equicorrelation is " +
            std::to_string(lowerBound) + '.');
    }

    const double idiosyncraticLoading = std::sqrt(std::max(0.0, 1.0 - pairwiseCorrelation));
    const double commonFactorEigenvalue =
        1.0 + (static_cast<double>(assetCount - 1) * pairwiseCorrelation);
    const double commonLoading =
        (std::sqrt(std::max(0.0, commonFactorEigenvalue)) - idiosyncraticLoading) /
        static_cast<double>(assetCount);

    double drawSum = 0.0;
    for (const double draw : independentDraws) {
        drawSum += draw;
    }

    std::vector<double> correlatedDraws(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        correlatedDraws[assetIndex] =
            (idiosyncraticLoading * independentDraws[assetIndex]) + (commonLoading * drawSum);
    }
    return correlatedDraws;
}

/**
 * Applies one period of the selected fundamental process.
 *
 * @param previousValue Latent fundamental value at time t.
 * @param parameters Drift, shock scale, floor, and process selector.
 * @param standardNormal Standardised innovation zeta_t ~ Normal(0, 1).
 * @return The latent fundamental value at time t + 1.
 */
[[nodiscard]] double advanceFundamentalValue(double previousValue,
                                             const FundamentalValueProcessParameters& parameters,
                                             double standardNormal) {
    const double innovation = parameters.shockStdDev * standardNormal;

    switch (parameters.processType) {
    case FundamentalProcessType::GeometricBrownianMotion: {
        /*
         * Formula note:
         * F_{t+1} = max(F_min, F_t * exp((mu - sigma^2 / 2) + sigma * zeta_t)).
         *
         * The -sigma^2/2 Ito correction makes mu the expected arithmetic
         * growth rate, so E[F_{t+1} | F_t] = F_t * exp(mu). Multiplicative
         * dynamics keep the value positive on their own; the floor only guards
         * against extreme downward excursions reaching the price grid.
         */
        const double logGrowth =
            (parameters.driftPerStep - (0.5 * parameters.shockStdDev * parameters.shockStdDev)) +
            innovation;
        return std::max(parameters.minimumValue, previousValue * std::exp(logGrowth));
    }
    case FundamentalProcessType::ArithmeticRandomWalk:
    default:
        /*
         * Formula note:
         * F_{t+1} = max(F_min, F_t + mu_F + epsilon_t),
         * epsilon_t = sigma_F * zeta_t ~ Normal(0, sigma_F^2).
         */
        return std::max(parameters.minimumValue,
                        previousValue + parameters.driftPerStep + innovation);
    }
}

} // namespace

FundamentalValueProcess::FundamentalValueProcess()
    : randomEngine_(kDefaultFundamentalProcessSeed) {}

FundamentalValueProcess::FundamentalValueProcess(std::uint64_t seed) : randomEngine_(seed) {}

double FundamentalValueProcess::generateFundamentalValue(
    Market& market, std::size_t assetIndex, const FundamentalValueProcessParameters& parameters) {
    const double previousValue = latestFundamental(market, assetIndex);

    validateFundamentalProcess(parameters.driftPerStep, parameters.shockStdDev,
                               parameters.minimumValue);

    /*
     * The standardised draw is scaled inside advanceFundamentalValue. Drawing
     * Normal(0, 1) and multiplying by sigma is bit-identical to drawing
     * Normal(0, sigma) directly and consumes the same engine state, which is
     * what lets the correlated multi-asset path reproduce this sequence
     * exactly for a single asset (see MarketFundamentalProcessTests).
     */
    const double nextFundamental = advanceFundamentalValue(
        previousValue, parameters, randomEngine_.generateNormalDist(0.0, 1.0));
    market.storeTrueValue(assetIndex, nextFundamental);
    return nextFundamental;
}

std::vector<double> FundamentalValueProcess::generateCorrelatedFundamentalValues(
    Market& market, const std::vector<FundamentalValueProcessParameters>& parameters,
    double pairwiseCorrelation) {
    if (parameters.size() != market.assetCount()) {
        throw std::invalid_argument(
            "Fundamental process parameters must be supplied for every configured asset.");
    }
    if (parameters.empty()) {
        return {};
    }
    requireFinite(pairwiseCorrelation, "Asset fundamental correlation");
    if (pairwiseCorrelation < -1.0 || pairwiseCorrelation > 1.0) {
        throw std::invalid_argument("Asset fundamental correlation must lie in [-1, 1].");
    }

    const std::size_t assetCount = parameters.size();

    /*
     * Read every previous value before drawing so that a market missing an
     * initial fundamental fails without having consumed engine state, which
     * would otherwise desynchronise an otherwise recoverable run.
     */
    std::vector<double> previousValues(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        previousValues[assetIndex] = latestFundamental(market, assetIndex);
    }
    for (const FundamentalValueProcessParameters& assetParameters : parameters) {
        validateFundamentalProcess(assetParameters.driftPerStep, assetParameters.shockStdDev,
                                   assetParameters.minimumValue);
    }

    /*
     * Draw independent standard normals first, in asset index order, so the
     * engine consumption pattern is fixed by the asset count alone and does not
     * depend on the correlation value.
     */
    std::vector<double> independentDraws(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        independentDraws[assetIndex] = randomEngine_.generateNormalDist(0.0, 1.0);
    }

    const std::vector<double> correlatedDraws =
        correlateStandardNormals(independentDraws, pairwiseCorrelation);

    std::vector<double> nextFundamentals(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        nextFundamentals[assetIndex] = advanceFundamentalValue(
            previousValues[assetIndex], parameters[assetIndex], correlatedDraws[assetIndex]);
        market.storeTrueValue(assetIndex, nextFundamentals[assetIndex]);
    }
    return nextFundamentals;
}

std::vector<double>
FundamentalValueProcess::generateTrueValues(Market& market, std::size_t assetIndex,
                                            const TrueValueGenerationParameters& parameters) {
    requireFinite(parameters.initialValue, "Initial fundamental value");
    validateFundamentalProcess(parameters.driftPerStep, parameters.shockStdDev,
                               parameters.minimumValue);

    std::vector<double> generated;
    generated.reserve(parameters.timeSteps);

    // Use the latest stored fundamental price as p_f(t) when available.
    // Otherwise, initialize p_f(0) with the configured initial latent value.
    double fundamentalPrice = parameters.initialValue;
    if (const std::vector<double>& history = market.getTrueValues(assetIndex); !history.empty()) {
        fundamentalPrice = history.back();
    }

    for (std::size_t i = 0; i < parameters.timeSteps; ++i) {
        const double shock = randomEngine_.generateNormalDist(0.0, parameters.shockStdDev);
        /*
         * Formula note:
         * F_{t+1} = max(F_min, F_t + mu_F + epsilon_t),
         * epsilon_t ~ Normal(0, sigma_F^2).
         */
        fundamentalPrice =
            std::max(parameters.minimumValue, fundamentalPrice + parameters.driftPerStep + shock);
        generated.push_back(fundamentalPrice);
        market.storeTrueValue(assetIndex, fundamentalPrice);
    }

    return generated;
}

} // namespace abm
