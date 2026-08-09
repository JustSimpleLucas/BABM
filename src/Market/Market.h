// Market.h

#ifndef MARKET_H
#define MARKET_H

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "ControlParameters/MarketConfig.h"
#include "Utility/SimulationConstants.h"

namespace abm {

class RandomEngine;

/**
 * Parameters for pre-generating a latent fundamental-value path.
 *
 * Grouping these values avoids swappable adjacent numeric arguments and keeps
 * the experimental interpretation explicit at call sites.
 */
struct TrueValueGenerationParameters {
    /** Number of future fundamental values to draw and append. */
    std::size_t timeSteps{0};

    /**
     * Initial latent value used only when the asset has no stored fundamental
     * history.
     */
    double initialValue{0.0};

    /** Deterministic drift added to the latent fundamental value each period. */
    double driftPerStep{0.0};

    /** Standard deviation of the additive Gaussian fundamental-value shock. */
    double shockStdDev{0.01};

    /** Lower bound applied after drift and stochastic innovation are combined. */
    double minimumValue{kMinimumPrice};
};

/**
 * Parameters controlling one-period latent fundamental-value evolution.
 *
 * The functional form is selected by `processType`:
 *   ArithmeticRandomWalk    F_{t+1} = max(F_min, F_t + mu + sigma * zeta)
 *   GeometricBrownianMotion F_{t+1} = max(F_min, F_t * exp((mu - sigma^2/2) + sigma * zeta))
 *
 * where zeta is a standard normal innovation. The units of `driftPerStep` and
 * `shockStdDev` follow the chosen process; see FundamentalProcessType.
 */
struct FundamentalValueProcessParameters {
    /** Stochastic process used to evolve the latent fundamental value. */
    FundamentalProcessType processType{FundamentalProcessType::ArithmeticRandomWalk};

    /** Deterministic drift applied to the latent fundamental value each period. */
    double driftPerStep{0.0};

    /** Scale of the Gaussian fundamental-value innovation. */
    double shockStdDev{0.01};

    /** Lower bound applied after drift and stochastic innovation are combined. */
    double minimumValue{kMinimumPrice};
};

/** One asset's realised-price and latent-fundamental histories. */
struct AssetPriceSeries {
    std::vector<double> marketValues;
    std::vector<double> trueValues;
};

/**
 * Stores price histories and market-level statistics for one or more assets.
 *
 * The market keeps the observed market price and the latent fundamental value
 * separate. This distinction is important for behavioural-finance experiments:
 * fundamentalists trade on perceived mispricing, while chartists trade on
 * patterns in realised market prices.
 *
 * Assets are addressed by their index in AssetUniverse order — the same
 * addressing used by Order::assetIndex, the covariance matrix, the agent
 * balance sheet, and every per-asset output column. Histories were previously
 * keyed by asset name, which made the market the only component in the model
 * with its own addressing scheme and put a string comparison in the per-agent,
 * per-step valuation path. Names are retained only to label diagnostics.
 */
class Market {
public:
    /** Constructs a reproducible market with a documented default seed. */
    Market();

    /** Constructs a reproducible market with an experiment-supplied seed. */
    explicit Market(std::uint64_t seed);

    /**
     * Copying a market would duplicate the random engine state and make later
     * stochastic draws ambiguous for reproducibility audits.
     */
    Market(const Market&) = delete;
    Market& operator=(const Market&) = delete;

    /** Transfers price histories and random-engine state as one experiment state. */
    Market(Market&& other) noexcept;
    Market& operator=(Market&& other) noexcept;

    ~Market();

    /**
     * Sizes the per-asset histories and records names for diagnostics.
     *
     * Must be called before any asset is addressed. Names are stored purely so
     * that out-of-range and insufficient-history errors can say which asset
     * they mean; nothing is ever looked up by name.
     *
     * @throws std::invalid_argument when the list is empty or names repeat.
     */
    void configureAssets(std::vector<std::string> assetNames);

    /** Returns the number of assets this market carries histories for. */
    [[nodiscard]] std::size_t assetCount() const;

    /**
     * Appends a realised market price for an asset.
     *
     * The value must be finite. Positive prices are expected by the trading
     * strategies and are validated before order generation.
     */
    void storeMarketValue(std::size_t assetIndex, double value);

    /**
     * Appends a latent fundamental value for an asset.
     *
     * This series represents the model's research assumption about intrinsic
     * value rather than an observed transaction price.
     */
    void storeTrueValue(std::size_t assetIndex, double value);

    /** Returns the realised market-price history for an asset. */
    [[nodiscard]] const std::vector<double>& getMarketValues(std::size_t assetIndex) const;

    /** Returns the latent fundamental-value history for an asset. */
    [[nodiscard]] const std::vector<double>& getTrueValues(std::size_t assetIndex) const;

    /** Calculates a simple moving average over the latest window observations. */
    [[nodiscard]] double calculateMovingAverage(std::size_t assetIndex, std::size_t window) const;

    /** Calculates the population standard deviation over the latest price observations. */
    [[nodiscard]] double calculateStandardDeviation(std::size_t assetIndex,
                                                    std::size_t window) const;

    /**
     * Calculates realised volatility from one-period log returns.
     *
     * This is the preferred volatility estimator for strategy allocation and
     * stylised-fact analysis because it measures dispersion in return space
     * rather than in price-level space.
     */
    [[nodiscard]] double calculateLogReturnStandardDeviation(std::size_t assetIndex,
                                                             std::size_t window) const;

    /** Calculates a simple RSI indicator over the latest period observations. */
    [[nodiscard]] double calculateRSI(
        std::size_t assetIndex,
        std::size_t period = kRelativeStrengthIndexPeriod) const;

    /**
     * Advances one asset's latent fundamental value by one period.
     *
     * The innovation is drawn independently of any other asset, so this
     * overload is appropriate only for single-asset evolution or for tests.
     * Multi-asset runs must use generateCorrelatedFundamentalValues so that
     * the cross-asset correlation structure is respected.
     */
    [[nodiscard]] double generateFundamentalValue(
        std::size_t assetIndex,
        const FundamentalValueProcessParameters& parameters);

    /**
     * Advances every supplied asset by one period using correlated innovations.
     *
     * Purpose: fundamental values in a multi-asset market are not independent.
     * A common macroeconomic factor makes fundamentals co-move, and that
     * co-movement is what limits the diversification available to agents.
     *
     * Method: one standard normal z_j is drawn per asset in index order, then
     * mapped to correlated standard normals via the closed-form one-factor
     * square root of the equicorrelation matrix R (unit diagonal,
     * `pairwiseCorrelation` off-diagonal):
     *
     *   zeta_j = a * z_j + b * sum_k z_k,
     *   a = sqrt(1 - rho),
     *   b = (sqrt(1 + (n - 1) * rho) - a) / n.
     *
     * This is preferred over a generic Cholesky factorization because it stays
     * exact on the positive-semi-definite boundary (rho = 1, or the lower limit
     * rho = -1/(n-1)) where Cholesky would fail on a singular matrix. Each
     * asset then applies its own process to its own zeta_j.
     *
     * Reproducibility: with one asset, or with rho = 0, the map is exactly the
     * identity and is short-circuited, so the innovation sigma * z_j is
     * bit-identical to the legacy independent single-asset draw. The historical
     * draw sequence is therefore preserved exactly.
     *
     * @param parameters Per-asset process parameters, one per configured
     *        asset in index order.
     * @param pairwiseCorrelation Correlation applied to every distinct pair.
     * @return The new fundamental value for each asset, in index order.
     *
     * @throws std::invalid_argument when the parameter count does not match the
     *         configured asset count, when the correlation is outside [-1, 1],
     *         or when the implied correlation matrix is not positive
     *         semi-definite.
     */
    [[nodiscard]] std::vector<double> generateCorrelatedFundamentalValues(
        const std::vector<FundamentalValueProcessParameters>& parameters,
        double pairwiseCorrelation);

    /**
     * Generates and stores a sequence of latent fundamental values.
     *
     * This helper is useful for reproducible experiments and tests where the
     * fundamental process should be generated before agent interaction begins.
     */
    [[nodiscard]] std::vector<double> generateTrueValues(
        std::size_t assetIndex,
        const TrueValueGenerationParameters& parameters);

private:
    [[nodiscard]] const AssetPriceSeries& seriesAt(std::size_t assetIndex) const;
    [[nodiscard]] AssetPriceSeries& seriesAt(std::size_t assetIndex);

    /** Returns a human-readable label for an asset, for diagnostics only. */
    [[nodiscard]] std::string assetLabel(std::size_t assetIndex) const;

    std::vector<std::string> assetNames_;
    std::vector<AssetPriceSeries> series_;
    std::unique_ptr<RandomEngine> randomEngine_;
};

} // namespace abm

#endif // MARKET_H
