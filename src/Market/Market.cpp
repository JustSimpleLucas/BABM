// Market.cpp
#include "Market/Market.h"
#include "RandomGenerator/RandomGenerator.h"
#include "Utility/NumericValidation.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <iterator>
#include <stdexcept>
#include <utility>
#include <string>

namespace abm {
namespace {
constexpr std::uint64_t kDefaultMarketSeed = 42U;

void validateFundamentalProcess(double driftPerStep,
                                double shockStdDev,
                                double minimumValue) {
    requireFinite(driftPerStep, "Fundamental drift per step");
    requireNonNegative(shockStdDev, "Fundamental shock stddev");
    requireStrictlyPositive(minimumValue, "Minimum fundamental value");
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
[[nodiscard]] std::vector<double> correlateStandardNormals(
    const std::vector<double>& independentDraws,
    double pairwiseCorrelation) {
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
[[nodiscard]] double advanceFundamentalValue(
    double previousValue,
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

Market::Market()
    : randomEngine_(std::make_unique<RandomEngine>(kDefaultMarketSeed)) {}

Market::Market(std::uint64_t seed)
    : randomEngine_(std::make_unique<RandomEngine>(seed)) {}

Market::Market(Market&& other) noexcept = default;

Market& Market::operator=(Market&& other) noexcept = default;

Market::~Market() = default;

void Market::configureAssets(std::vector<std::string> assetNames) {
    if (assetNames.empty()) {
        throw std::invalid_argument("A market requires at least one asset.");
    }
    for (std::size_t assetIndex = 0; assetIndex < assetNames.size(); ++assetIndex) {
        for (std::size_t otherIndex = assetIndex + 1; otherIndex < assetNames.size();
             ++otherIndex) {
            if (assetNames[assetIndex] == assetNames[otherIndex]) {
                throw std::invalid_argument("Duplicate asset name in market configuration: " +
                                            assetNames[assetIndex]);
            }
        }
    }
    assetNames_ = std::move(assetNames);
    series_.assign(assetNames_.size(), AssetPriceSeries{});
}

std::size_t Market::assetCount() const {
    return series_.size();
}

std::string Market::assetLabel(std::size_t assetIndex) const {
    if (assetIndex < assetNames_.size()) {
        return "'" + assetNames_[assetIndex] + "' (index " + std::to_string(assetIndex) + ")";
    }
    return "index " + std::to_string(assetIndex);
}

const AssetPriceSeries& Market::seriesAt(std::size_t assetIndex) const {
    if (assetIndex >= series_.size()) {
        throw std::out_of_range("No configured market series for asset " + assetLabel(assetIndex) +
                                "; the market carries " + std::to_string(series_.size()) +
                                " asset(s).");
    }
    return series_[assetIndex];
}

AssetPriceSeries& Market::seriesAt(std::size_t assetIndex) {
    return const_cast<AssetPriceSeries&>(std::as_const(*this).seriesAt(assetIndex));
}

void Market::storeMarketValue(std::size_t assetIndex, double value) {
    requireFinite(value, "Market value");
    seriesAt(assetIndex).marketValues.push_back(value);
}

void Market::storeTrueValue(std::size_t assetIndex, double value) {
    requireFinite(value, "Fundamental value");
    seriesAt(assetIndex).trueValues.push_back(value);
}

const std::vector<double>& Market::getMarketValues(std::size_t assetIndex) const {
    return seriesAt(assetIndex).marketValues;
}

const std::vector<double>& Market::getTrueValues(std::size_t assetIndex) const {
    return seriesAt(assetIndex).trueValues;
}

double Market::calculateMovingAverage(std::size_t assetIndex, std::size_t window) const {
    requirePositiveSize(window, "Moving average window");

    const auto& values = getMarketValues(assetIndex);
    if (values.size() < window) {
        throw std::invalid_argument(
            "Insufficient market values to calculate moving average for asset " +
            assetLabel(assetIndex) + '.');
    }

    const auto windowBegin = std::prev(values.cend(), static_cast<std::ptrdiff_t>(window));
    double sum = 0.0;
    for (auto valueIt = windowBegin; valueIt != values.cend(); ++valueIt) {
        sum += *valueIt;
    }

    /*
     * Formula note:
     * MA_t(h) = (1 / h) * sum_{k=0}^{h-1} P_{t-k}.
     */
    return sum / static_cast<double>(window);
}

double Market::calculateStandardDeviation(std::size_t assetIndex, std::size_t window) const {
    requirePositiveSize(window, "Standard deviation window");

    const auto& values = getMarketValues(assetIndex);
    if (values.size() < window) {
        throw std::invalid_argument(
            "Insufficient market values to calculate standard deviation for asset " +
            assetLabel(assetIndex) + '.');
    }

    const auto windowBegin = std::prev(values.cend(), static_cast<std::ptrdiff_t>(window));
    const double mean = calculateMovingAverage(assetIndex, window);

    double squaredDiffSum = 0.0;
    for (auto valueIt = windowBegin; valueIt != values.cend(); ++valueIt) {
        const double diff = *valueIt - mean;
        squaredDiffSum += diff * diff;
    }

    /*
     * Formula note:
     * sigma_P(h) = sqrt((1 / h) * sum_{k=0}^{h-1} (P_{t-k} - MA_t(h))^2).
     */
    const double variance = squaredDiffSum / static_cast<double>(window);
    return std::sqrt(variance);
}

double Market::calculateLogReturnStandardDeviation(std::size_t assetIndex,
                                                   std::size_t window) const {
    requirePositiveSize(window, "Log-return standard deviation window");

    const auto& values = getMarketValues(assetIndex);
    if (values.size() <= window) {
        throw std::invalid_argument(
            "Insufficient market values to calculate log-return standard deviation for asset " +
            assetLabel(assetIndex) + '.');
    }

    auto currentIt = std::prev(values.cend(), static_cast<std::ptrdiff_t>(window));
    auto previousIt = std::prev(currentIt);
    std::vector<double> logReturns;
    logReturns.reserve(window);
    double logReturnSum = 0.0;
    for (; currentIt != values.cend(); ++currentIt, ++previousIt) {
        const double previousPrice = *previousIt;
        const double currentPrice = *currentIt;
        if (previousPrice <= 0.0 || currentPrice <= 0.0) {
            throw std::invalid_argument(
                "Log-return standard deviation requires strictly positive market prices.");
        }
        /*
         * Formula note:
         * r_tau = log(P_tau / P_{tau-1}).
         */
        const double logReturn = std::log(currentPrice / previousPrice);
        logReturns.push_back(logReturn);
        logReturnSum += logReturn;
    }

    const double meanLogReturn = logReturnSum / static_cast<double>(window);

    double squaredDiffSum = 0.0;
    for (const double logReturn : logReturns) {
        const double diff = logReturn - meanLogReturn;
        squaredDiffSum += diff * diff;
    }

    /*
     * Formula note:
     * sigma_r(h) = sqrt((1 / h) * sum_tau (r_tau - mean_r)^2).
     *
     * This realised-volatility estimate is used by the portfolio-allocation
     * rules, so it is intentionally computed on log returns rather than prices.
     */
    const double variance = squaredDiffSum / static_cast<double>(window);
    return std::sqrt(variance);
}

double Market::calculateRSI(std::size_t assetIndex, std::size_t period) const {
    requirePositiveSize(period, "RSI period");

    const auto& values = getMarketValues(assetIndex);
    if (values.size() <= period) {
        throw std::invalid_argument("Insufficient market values to calculate RSI for asset " +
                                    assetLabel(assetIndex) + '.');
    }

    auto currentIt = std::prev(values.cend(), static_cast<std::ptrdiff_t>(period));
    auto previousIt = std::prev(currentIt);
    double gains = 0.0;
    double losses = 0.0;

    for (; currentIt != values.cend(); ++currentIt, ++previousIt) {
        const double delta = *currentIt - *previousIt;
        if (delta > 0.0) {
            gains += delta;
        } else {
            losses -= delta;
        }
    }

    const double avgGain = gains / static_cast<double>(period);
    const double avgLoss = losses / static_cast<double>(period);

    if (avgLoss == 0.0) {
        return 100.0;
    }
    if (avgGain == 0.0) {
        return 0.0;
    }

    const double rs = avgGain / avgLoss;
    /*
     * Formula note:
     * RS = average_gain / average_loss,
     * RSI = 100 - 100 / (1 + RS).
     */
    return 100.0 - (100.0 / (1.0 + rs));
}

double Market::generateFundamentalValue(
    std::size_t assetIndex,
    const FundamentalValueProcessParameters& parameters) {
    AssetPriceSeries& series = seriesAt(assetIndex);
    if (series.trueValues.empty()) {
        throw std::out_of_range(
            "Cannot generate fundamental value without an initial true value for asset " +
            assetLabel(assetIndex) + '.');
    }

    validateFundamentalProcess(
        parameters.driftPerStep, parameters.shockStdDev, parameters.minimumValue);

    if (!randomEngine_) {
        randomEngine_ = std::make_unique<RandomEngine>(kDefaultMarketSeed);
    }

    /*
     * The standardised draw is scaled inside advanceFundamentalValue. Drawing
     * Normal(0, 1) and multiplying by sigma is bit-identical to drawing
     * Normal(0, sigma) directly and consumes the same engine state, which is
     * what lets the correlated multi-asset path reproduce this sequence
     * exactly for a single asset (see MarketFundamentalProcessTests).
     */
    const double nextFundamental = advanceFundamentalValue(
        series.trueValues.back(), parameters, randomEngine_->generateNormalDist(0.0, 1.0));
    series.trueValues.push_back(nextFundamental);
    return nextFundamental;
}

std::vector<double> Market::generateCorrelatedFundamentalValues(
    const std::vector<FundamentalValueProcessParameters>& parameters,
    double pairwiseCorrelation) {
    if (parameters.size() != series_.size()) {
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

    for (std::size_t assetIndex = 0; assetIndex < series_.size(); ++assetIndex) {
        if (series_[assetIndex].trueValues.empty()) {
            throw std::out_of_range(
                "Cannot generate fundamental value without an initial true value for asset " +
                assetLabel(assetIndex) + '.');
        }
    }
    for (const FundamentalValueProcessParameters& assetParameters : parameters) {
        validateFundamentalProcess(assetParameters.driftPerStep,
                                   assetParameters.shockStdDev,
                                   assetParameters.minimumValue);
    }

    if (!randomEngine_) {
        randomEngine_ = std::make_unique<RandomEngine>(kDefaultMarketSeed);
    }

    /*
     * Draw independent standard normals first, in asset index order, so the
     * engine consumption pattern is fixed by the asset count alone and does not
     * depend on the correlation value.
     */
    const std::size_t assetCount = parameters.size();
    std::vector<double> independentDraws(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        independentDraws[assetIndex] = randomEngine_->generateNormalDist(0.0, 1.0);
    }

    const std::vector<double> correlatedDraws =
        correlateStandardNormals(independentDraws, pairwiseCorrelation);

    std::vector<double> nextFundamentals(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        std::vector<double>& history = series_[assetIndex].trueValues;
        nextFundamentals[assetIndex] =
            advanceFundamentalValue(history.back(), parameters[assetIndex],
                                    correlatedDraws[assetIndex]);
        history.push_back(nextFundamentals[assetIndex]);
    }
    return nextFundamentals;
}

std::vector<double> Market::generateTrueValues(std::size_t assetIndex,
                                               const TrueValueGenerationParameters& parameters) {
    requireFinite(parameters.initialValue, "Initial fundamental value");
    validateFundamentalProcess(
        parameters.driftPerStep, parameters.shockStdDev, parameters.minimumValue);

    if (!randomEngine_) {
        randomEngine_ = std::make_unique<RandomEngine>(kDefaultMarketSeed);
    }

    std::vector<double> generated;
    generated.reserve(parameters.timeSteps);

    // Use the latest stored fundamental price as p_f(t) when available.
    // Otherwise, initialize p_f(0) with the configured initial latent value.
    double fundamentalPrice = parameters.initialValue;
    std::vector<double>& history = seriesAt(assetIndex).trueValues;
    if (!history.empty()) {
        fundamentalPrice = history.back();
    }

    for (std::size_t i = 0; i < parameters.timeSteps; ++i) {
        const double shock = randomEngine_->generateNormalDist(0.0, parameters.shockStdDev);
        /*
         * Formula note:
         * F_{t+1} = max(F_min, F_t + mu_F + epsilon_t),
         * epsilon_t ~ Normal(0, sigma_F^2).
         */
        fundamentalPrice =
            std::max(parameters.minimumValue, fundamentalPrice + parameters.driftPerStep + shock);
        generated.push_back(fundamentalPrice);
        history.push_back(fundamentalPrice);
    }

    return generated;
}

} // namespace abm
