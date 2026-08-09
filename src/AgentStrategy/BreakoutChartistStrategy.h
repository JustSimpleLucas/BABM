// BreakoutChartistStrategy.h

#ifndef BREAKOUT_CHARTIST_STRATEGY_H
#define BREAKOUT_CHARTIST_STRATEGY_H

#include <cstddef>
#include <string>
#include <utility>

#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/ChartistStrategy.h"
#include "ControlParameters/SimulationConfig.h"

namespace abm {

/**
 * Complete construction parameters for a breakout chartist strategy.
 *
 * The parameter object separates the price-channel horizon from shared
 * volatility and portfolio controls, which prevents accidental swaps between
 * adjacent window lengths.
 */
struct BreakoutChartistStrategyParameters {
    /** Shared chartist portfolio sizing, volatility, and CPT controls. */
    ChartistStrategyParameters commonParameters{};

    /** Number of previous prices used to form the high-low channel. */
    std::size_t breakoutWindow{20};
};

/**
 * Chartist Donchian-style price-channel breakout rule.
 *
 * Breakout chartists treat a price move beyond the previous lookback high or
 * low as trend-continuation evidence. This is a transparent technical-trading
 * assumption often used to represent rule-based trend followers in market
 * models.
 */
class BreakoutChartistStrategy final : public ChartistStrategy {
  public:
    /**
     * Constructs a breakout chartist with explicit channel and portfolio controls.
     *
     * @param parameters Named breakout, portfolio, and CPT controls.
     */
    explicit BreakoutChartistStrategy(
        BreakoutChartistStrategyParameters parameters = BreakoutChartistStrategyParameters{});

    /** Returns the export label for breakout chartists. */
    [[nodiscard]] std::string strategyType() const override;

    /** Updates the previous-price channel length used for breakout detection. */
    void setBreakoutWindow(std::size_t breakoutWindow);

    /** Returns the previous-price channel length used for breakout detection. */
    [[nodiscard]] std::size_t breakoutWindow() const;

  protected:
    [[nodiscard]] AgentAction generateSignal(const Market& market) const override;
    [[nodiscard]] double forecastExcessReturn(const Market& market,
                                               std::size_t forecastAssetIndex) const override;

  private:
    [[nodiscard]] std::pair<double, double>
    previousPriceChannel(const Market& market, std::size_t forecastAssetIndex) const;

    std::size_t breakoutWindow_;
};

} // namespace abm

#endif // BREAKOUT_CHARTIST_STRATEGY_H
