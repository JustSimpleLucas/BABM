// RelativeStrengthIndexChartistStrategy.h

#ifndef RELATIVE_STRENGTH_INDEX_CHARTIST_STRATEGY_H
#define RELATIVE_STRENGTH_INDEX_CHARTIST_STRATEGY_H

#include <cstddef>
#include <string>

#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/ChartistStrategy.h"
#include "ControlParameters/SimulationConfig.h"

namespace abm {

/**
 * Chartist oscillator rule based on the Relative Strength Index.
 *
 * RSI chartists buy after oversold readings and sell after overbought readings.
 * The rule keeps the common 30/70 thresholds explicit because they are a
 * modelling assumption about boundedly rational technical trading.
 */
class RelativeStrengthIndexChartistStrategy final : public ChartistStrategy {
  public:
    /**
     * Constructs an RSI chartist with explicit portfolio and CPT controls.
     *
     * @param parameters Shared chartist portfolio, volatility, and CPT controls.
     */
    explicit RelativeStrengthIndexChartistStrategy(
        ChartistStrategyParameters parameters = ChartistStrategyParameters{});

    /** Returns the export label for RSI chartists. */
    [[nodiscard]] std::string strategyType() const override;

  protected:
    [[nodiscard]] AgentAction generateSignal(const Market& market) const override;
    [[nodiscard]] double forecastExcessReturn(const Market& market,
                                               std::size_t forecastAssetIndex) const override;
};

} // namespace abm

#endif // RELATIVE_STRENGTH_INDEX_CHARTIST_STRATEGY_H
