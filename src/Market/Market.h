// Market.h

#ifndef ABM_MARKET_MARKET_H
#define ABM_MARKET_MARKET_H

#include <cstddef>
#include <string>
#include <vector>

#include "Utility/SimulationConstants.h"

namespace abm {

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
 *
 * The market is a passive record: it stores what the fundamental process and
 * the order book produced and answers questions about that history. It draws no
 * random numbers of its own, so it is freely copyable and a copy can be taken
 * for diagnostics without duplicating or desynchronising any random stream. The
 * fundamental process that extends `trueValues` lives in
 * FundamentalValueProcess.
 */
class Market {
  public:
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
     * Returns a human-readable label for an asset, for diagnostics only.
     *
     * Public so that collaborators which extend a market's histories — notably
     * FundamentalValueProcess — can name the offending asset in their own error
     * messages rather than reporting a bare index.
     */
    [[nodiscard]] std::string assetLabel(std::size_t assetIndex) const;

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
    [[nodiscard]] double calculateRSI(std::size_t assetIndex,
                                      std::size_t period = kRelativeStrengthIndexPeriod) const;

  private:
    [[nodiscard]] const AssetPriceSeries& seriesAt(std::size_t assetIndex) const;
    [[nodiscard]] AssetPriceSeries& seriesAt(std::size_t assetIndex);

    std::vector<std::string> assetNames_;
    std::vector<AssetPriceSeries> series_;
};

} // namespace abm

#endif // ABM_MARKET_MARKET_H
