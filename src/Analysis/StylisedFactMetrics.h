// StylisedFactMetrics.h

#ifndef STYLISED_FACT_METRICS_H
#define STYLISED_FACT_METRICS_H

#include <cstddef>
#include <string>
#include <vector>

namespace abm {

class SimulationRunResult;

/**
 * Compact screening metrics for simulated financial-market stylised facts.
 *
 * These metrics are deliberately lightweight. They provide immediate run-level
 * diagnostics for experiment manifests, while the R analysis workflow remains
 * the thesis-level inferential layer for formal Ljung-Box, ARCH, GARCH, and
 * distributional tests.
 */
struct RunMetrics {
    std::size_t observationCount{0};
    double meanLogReturn{0.0};
    double logReturnVariance{0.0};
    double logReturnStdDev{0.0};
    double skewness{0.0};
    double excessKurtosis{0.0};
    double maxDrawdown{0.0};
    double finalWealthGiniCoefficient{0.0};
    double meanAllocativeEfficiency{0.0};
    std::size_t allocativeEfficiencyObservations{0};
    double lag1ReturnAutocorrelation{0.0};
    double lag1AbsoluteReturnAutocorrelation{0.0};
    double lag1SquaredReturnAutocorrelation{0.0};
    double meanTradedVolume{0.0};
    double zeroReturnShare{0.0};
    std::string autocorrelationConclusion;
    std::string fatTailsConclusion;
    std::string volatilityClusteringConclusion;
};

/** Screening metrics for one traded asset, paired with the asset's name. */
struct AssetRunMetrics {
    std::string assetName;
    RunMetrics metrics;
};

/**
 * Calculates stylised-fact screening metrics from completed simulation output.
 *
 * @param result Completed simulation output containing per-step details.
 * @return Summary metrics used by CSV exports and experiment manifests.
 */
[[nodiscard]] RunMetrics calculateRunMetrics(const SimulationRunResult& result);

/**
 * Calculates the same screening metrics separately for every traded asset.
 *
 * Every asset is screened on identical terms, so a two-asset run reports two
 * independent stylised-fact verdicts rather than one verdict for whichever
 * asset happens to be nominated primary. Wealth inequality is a portfolio-level
 * quantity and is therefore repeated unchanged on each asset's row.
 *
 * @param result Completed simulation output containing per-(step, asset) details.
 * @return One metrics record per asset, in the configured asset order. Falls
 *     back to a single record built from the primary-asset step details when
 *     the result carries no per-asset data.
 */
[[nodiscard]] std::vector<AssetRunMetrics>
calculateAssetRunMetrics(const SimulationRunResult& result);

/**
 * Calculates a bounded cross-sectional Gini coefficient from agent wealth values.
 *
 * The metric floors finite negative wealth at zero before sorting. This keeps the
 * reported inequality index in the standard [0, 1] range while still treating
 * negative-equity agents as holding no non-negative wealth for distributional
 * concentration. Non-finite values are ignored; fewer than two usable values or
 * zero aggregate non-negative wealth returns 0.
 *
 * @param wealthValues Mark-to-market wealth values for the population.
 * @return Non-negative wealth Gini coefficient in [0, 1].
 */
[[nodiscard]] double calculateNonNegativeGiniCoefficient(std::vector<double> wealthValues);

} // namespace abm

#endif // STYLISED_FACT_METRICS_H
