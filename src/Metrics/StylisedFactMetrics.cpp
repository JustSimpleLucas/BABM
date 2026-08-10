// StylisedFactMetrics.cpp

#include "Metrics/StylisedFactMetrics.h"

#include "Results/SimulationRunResult.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>
#include <iterator>
#include <limits>
#include <numeric>
#include <utility>
#include <vector>

namespace abm {
namespace {

constexpr double kMinimumGiniDenominator = 1e-12;

double meanOf(const std::vector<double>& values) {
    if (values.empty()) {
        return 0.0;
    }
    return std::accumulate(values.begin(), values.end(), 0.0) / static_cast<double>(values.size());
}

double lagOneAutocorrelation(const std::vector<double>& values) {
    if (values.size() < 2) {
        return 0.0;
    }

    const double mean = meanOf(values);
    double numerator = 0.0;
    double denominator = 0.0;

    /*
     * Formula note:
     * rho_1 = sum_t (x_t - mean_x)(x_{t-1} - mean_x)
     *         / sum_t (x_t - mean_x)^2.
     *
     * The same helper is used for raw returns, absolute returns, and squared
     * returns to evaluate weak return autocorrelation and volatility clustering.
     */
    auto previousValueIt = values.cbegin();
    for (auto valueIt = std::next(previousValueIt); valueIt != values.cend();
         ++valueIt, ++previousValueIt) {
        numerator += (*valueIt - mean) * (*previousValueIt - mean);
    }
    for (const double value : values) {
        const double centred = value - mean;
        denominator += centred * centred;
    }

    if (denominator <= std::numeric_limits<double>::epsilon()) {
        return 0.0;
    }
    return numerator / denominator;
}

std::string interpretReturnAutocorrelation(double autocorrelation) {
    return std::abs(autocorrelation) < 0.10 ? "Consistent with weak linear return autocorrelation"
                                            : "Evidence of return autocorrelation";
}

std::string interpretFatTails(double excessKurtosis) {
    return excessKurtosis > 0.0 ? "Consistent with fat-tailed returns"
                                : "Fat-tail evidence is weak or mixed";
}

std::string interpretVolatilityClustering(double absoluteReturnAutocorrelation,
                                          double squaredReturnAutocorrelation) {
    return (absoluteReturnAutocorrelation > 0.05 || squaredReturnAutocorrelation > 0.05)
               ? "Consistent with volatility clustering"
               : "Volatility-clustering evidence is weak";
}

/**
 * One step of a single traded series, reduced to what the screening needs.
 *
 * Both the primary-asset StepDetails path and the per-asset AssetStepDetails
 * path project onto this shape, so the two are screened by exactly the same
 * arithmetic and their verdicts stay comparable.
 */
struct SeriesObservation {
    double logReturn{0.0};
    double price{0.0};
    double tradedVolume{0.0};
    double allocativeEfficiency{0.0};
    double maximumAllocativeSurplus{0.0};
};

RunMetrics screenSeries(const std::vector<SeriesObservation>& observations, double initialPrice) {
    RunMetrics metrics;

    std::vector<double> returns;
    returns.reserve(observations.size());
    std::vector<double> absoluteReturns;
    absoluteReturns.reserve(observations.size());
    std::vector<double> squaredReturns;
    squaredReturns.reserve(observations.size());

    double totalTradedVolume = 0.0;
    std::size_t zeroReturnCount = 0;
    double totalAllocativeEfficiency = 0.0;
    double peakPrice = initialPrice;
    double maxDrawdown = 0.0;

    for (const SeriesObservation& observation : observations) {
        if (std::isfinite(observation.logReturn)) {
            returns.push_back(observation.logReturn);
            absoluteReturns.push_back(std::abs(observation.logReturn));
            squaredReturns.push_back(observation.logReturn * observation.logReturn);
            if (std::abs(observation.logReturn) <= 1e-12) {
                ++zeroReturnCount;
            }
        }

        totalTradedVolume += observation.tradedVolume;
        if (std::isfinite(observation.allocativeEfficiency) &&
            observation.maximumAllocativeSurplus > kMinimumPrice) {
            totalAllocativeEfficiency += observation.allocativeEfficiency;
            ++metrics.allocativeEfficiencyObservations;
        }

        if (std::isfinite(observation.price) && observation.price > 0.0) {
            peakPrice = std::max(peakPrice, observation.price);
            if (peakPrice > 0.0) {
                /*
                 * Formula note:
                 * drawdown_t = (peak_price_t - P_t) / peak_price_t.
                 */
                maxDrawdown = std::max(maxDrawdown, (peakPrice - observation.price) / peakPrice);
            }
        }
    }

    metrics.observationCount = returns.size();
    metrics.maxDrawdown = maxDrawdown;
    if (metrics.allocativeEfficiencyObservations > 0) {
        metrics.meanAllocativeEfficiency =
            totalAllocativeEfficiency /
            static_cast<double>(metrics.allocativeEfficiencyObservations);
    }
    if (observations.empty()) {
        metrics.meanTradedVolume = 0.0;
    } else {
        metrics.meanTradedVolume = totalTradedVolume / static_cast<double>(observations.size());
    }

    if (returns.empty()) {
        metrics.autocorrelationConclusion = "Insufficient return observations";
        metrics.fatTailsConclusion = "Insufficient return observations";
        metrics.volatilityClusteringConclusion = "Insufficient return observations";
        return metrics;
    }

    metrics.meanLogReturn = meanOf(returns);
    metrics.zeroReturnShare =
        static_cast<double>(zeroReturnCount) / static_cast<double>(returns.size());

    double secondMoment = 0.0;
    double thirdMoment = 0.0;
    double fourthMoment = 0.0;
    /*
     * Formula note:
     * m_k = (1 / n) * sum_t (r_t - mean_r)^k.
     *
     * Variance, skewness, and excess kurtosis are calculated from these
     * central moments to assess fat tails and asymmetry in simulated returns.
     */
    for (const double value : returns) {
        const double centred = value - metrics.meanLogReturn;
        const double squared = centred * centred;
        secondMoment += squared;
        thirdMoment += squared * centred;
        fourthMoment += squared * squared;
    }

    secondMoment /= static_cast<double>(returns.size());
    thirdMoment /= static_cast<double>(returns.size());
    fourthMoment /= static_cast<double>(returns.size());

    metrics.logReturnVariance = secondMoment;
    metrics.logReturnStdDev = std::sqrt(secondMoment);
    if (secondMoment > std::numeric_limits<double>::epsilon()) {
        /*
         * Formula note:
         * skewness = m_3 / sigma^3,
         * excess_kurtosis = m_4 / m_2^2 - 3.
         */
        metrics.skewness = thirdMoment / std::pow(metrics.logReturnStdDev, 3.0);
        metrics.excessKurtosis = (fourthMoment / (secondMoment * secondMoment)) - 3.0;
    }

    metrics.lag1ReturnAutocorrelation = lagOneAutocorrelation(returns);
    metrics.lag1AbsoluteReturnAutocorrelation = lagOneAutocorrelation(absoluteReturns);
    metrics.lag1SquaredReturnAutocorrelation = lagOneAutocorrelation(squaredReturns);
    metrics.autocorrelationConclusion =
        interpretReturnAutocorrelation(metrics.lag1ReturnAutocorrelation);
    metrics.fatTailsConclusion = interpretFatTails(metrics.excessKurtosis);
    metrics.volatilityClusteringConclusion = interpretVolatilityClustering(
        metrics.lag1AbsoluteReturnAutocorrelation, metrics.lag1SquaredReturnAutocorrelation);

    return metrics;
}

double finalWealthGini(const SimulationRunResult& result) {
    std::vector<double> finalWealthValues;
    finalWealthValues.reserve(result.agentSnapshots().size());
    for (const AgentSnapshot& snapshot : result.agentSnapshots()) {
        finalWealthValues.push_back(snapshot.finalWealth);
    }
    return calculateNonNegativeGiniCoefficient(std::move(finalWealthValues));
}

} // namespace

double calculateNonNegativeGiniCoefficient(std::vector<double> wealthValues) {
    std::vector<double> nonNegativeWealth;
    nonNegativeWealth.reserve(wealthValues.size());
    for (const double wealth : wealthValues) {
        if (std::isfinite(wealth)) {
            nonNegativeWealth.push_back(std::max(0.0, wealth));
        }
    }

    if (nonNegativeWealth.size() < 2) {
        return 0.0;
    }

    std::sort(nonNegativeWealth.begin(), nonNegativeWealth.end());
    const double totalWealth =
        std::accumulate(nonNegativeWealth.begin(), nonNegativeWealth.end(), 0.0);
    if (totalWealth <= kMinimumGiniDenominator) {
        return 0.0;
    }

    /*
     * Formula note:
     * G = (2 * sum_i i * W_(i)) / (n * sum_i W_i) - (n + 1) / n,
     * where W_(i) is the sorted non-negative wealth distribution. This compact
     * form is algebraically equivalent to the pairwise absolute-difference Gini
     * but avoids O(n^2) work for large ABM populations.
     */
    double weightedWealthSum = 0.0;
    for (std::size_t index = 0; index < nonNegativeWealth.size(); ++index) {
        weightedWealthSum += static_cast<double>(index + 1U) * nonNegativeWealth[index];
    }

    const double populationSize = static_cast<double>(nonNegativeWealth.size());
    const double gini = ((2.0 * weightedWealthSum) / (populationSize * totalWealth)) -
                        ((populationSize + 1.0) / populationSize);
    return std::clamp(gini, 0.0, 1.0);
}

RunMetrics calculateRunMetrics(const SimulationRunResult& result) {
    std::vector<SeriesObservation> observations;
    observations.reserve(result.stepDetails().size());
    for (const StepDetails& step : result.stepDetails()) {
        observations.push_back(SeriesObservation{
            step.asset.logReturn, step.asset.marketPrice, step.asset.tradedVolume,
            step.asset.allocativeEfficiency, step.asset.maximumAllocativeSurplus});
    }

    RunMetrics metrics = screenSeries(observations, result.config().initialPrice());
    metrics.finalWealthGiniCoefficient = finalWealthGini(result);
    return metrics;
}

std::vector<AssetRunMetrics> calculateAssetRunMetrics(const SimulationRunResult& result) {
    const double wealthGini = finalWealthGini(result);
    const MultiAssetRunData& multiAsset = result.multiAssetData();

    if (multiAsset.assetNames.empty()) {
        /*
         * Legacy result objects carry no per-asset data. Screening the
         * primary-asset series under the configured asset name keeps the
         * per-asset artefact well-formed for those runs.
         */
        RunMetrics metrics = calculateRunMetrics(result);
        return {AssetRunMetrics{result.config().assetName(), std::move(metrics)}};
    }

    const std::size_t assetCount = multiAsset.assetNames.size();
    std::vector<std::vector<SeriesObservation>> observationsByAsset(assetCount);
    for (const AssetStepDetails& step : multiAsset.assetStepDetails) {
        if (step.assetIndex >= assetCount) {
            continue;
        }
        observationsByAsset[step.assetIndex].push_back(
            SeriesObservation{step.logReturn, step.marketPrice, step.tradedVolume,
                              step.allocativeEfficiency, step.maximumAllocativeSurplus});
    }

    std::vector<AssetRunMetrics> assetMetrics;
    assetMetrics.reserve(assetCount);
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        /*
         * Drawdown is measured from each asset's own starting price, so the
         * peak-to-trough figures of a 100-unit and a 40-unit asset are directly
         * comparable rather than being anchored on the primary asset's level.
         */
        const double initialPrice = multiAsset.marketPriceHistories[assetIndex].empty()
                                        ? result.config().initialPrice()
                                        : multiAsset.marketPriceHistories[assetIndex].front();
        RunMetrics metrics = screenSeries(observationsByAsset[assetIndex], initialPrice);
        metrics.finalWealthGiniCoefficient = wealthGini;
        assetMetrics.push_back(
            AssetRunMetrics{multiAsset.assetNames[assetIndex], std::move(metrics)});
    }
    return assetMetrics;
}

} // namespace abm
