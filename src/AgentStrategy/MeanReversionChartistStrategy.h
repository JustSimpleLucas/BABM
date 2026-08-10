// MeanReversionChartistStrategy.h

#ifndef ABM_AGENT_STRATEGY_MEAN_REVERSION_CHARTIST_STRATEGY_H
#define ABM_AGENT_STRATEGY_MEAN_REVERSION_CHARTIST_STRATEGY_H

#include <cstddef>
#include <string>

#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/ChartistStrategy.h"
#include "ControlParameters/SimulationConfig.h"

namespace abm {

/**
 * Complete construction parameters for a mean-reversion chartist strategy.
 *
 * The named parameter object makes the reversal horizon distinct from shared
 * chartist controls such as volatility estimation and short-exposure limits.
 */
struct MeanReversionChartistStrategyParameters {
    /** Shared chartist portfolio sizing, volatility, and CPT controls. */
    ChartistStrategyParameters commonParameters{};

    /** Long moving-average window used as the perceived reversal anchor. */
    std::size_t longWindow{20};
};

/**
 * Chartist contrarian rule based on deviation from a long moving average.
 *
 * Mean-reversion chartists buy after the price falls below its long-horizon
 * average and sell after it rises above that benchmark. This captures a
 * bounded-rational belief that technical overreaction may reverse.
 */
class MeanReversionChartistStrategy final : public ChartistStrategy {
  public:
    /**
     * Constructs a mean-reversion chartist with explicit reversal controls.
     *
     * @param parameters Named reversal, portfolio, and CPT controls.
     */
    explicit MeanReversionChartistStrategy(MeanReversionChartistStrategyParameters parameters =
                                               MeanReversionChartistStrategyParameters{});

    /** Returns the export label for mean-reversion chartists. */
    [[nodiscard]] std::string strategyType() const override;

    /** Updates the long moving-average window used as the reversal anchor. */
    void setLongWindow(std::size_t longWindow);

  protected:
    [[nodiscard]] AgentAction generateSignal(const Market& market) const override;
    [[nodiscard]] double forecastExcessReturn(const Market& market,
                                              std::size_t forecastAssetIndex) const override;

  private:
    std::size_t longWindow_;
};

} // namespace abm

#endif // ABM_AGENT_STRATEGY_MEAN_REVERSION_CHARTIST_STRATEGY_H
