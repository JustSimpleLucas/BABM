// MomentumChartistStrategy.h

#ifndef ABM_AGENT_STRATEGY_MOMENTUM_CHARTIST_STRATEGY_H
#define ABM_AGENT_STRATEGY_MOMENTUM_CHARTIST_STRATEGY_H

#include "AgentStrategy/ChartistStrategy.h"
#include <cstddef>
#include <string>

namespace abm {

/**
 * Complete construction parameters for a momentum chartist strategy.
 *
 * Keeping the moving-average windows and portfolio controls in a named object
 * avoids ambiguous constructor calls where adjacent numeric values could be
 * accidentally swapped.
 */
struct MomentumChartistStrategyParameters {
    /** Shared chartist portfolio sizing, volatility, and CPT controls. */
    ChartistStrategyParameters commonParameters{};

    /** Short moving-average window used to detect recent trend direction. */
    std::size_t shortWindow{5};

    /** Long moving-average window used as the slower trend benchmark. */
    std::size_t longWindow{20};

    /** Deadband for weak moving-average gaps. */
    double momentumSignalThreshold{0.0};
};

/**
 * Chartist trend-following rule based on short-minus-long moving averages.
 *
 * The signal represents a standard moving-average crossover heuristic: agents
 * buy when the short-horizon trend is sufficiently above the long-horizon
 * trend and sell when it is sufficiently below. The threshold is a research
 * control for ignoring economically weak trend evidence.
 */
class MomentumChartistStrategy final : public ChartistStrategy {
  public:
    /**
     * Constructs a momentum chartist with explicit trend and portfolio controls.
     *
     * @param parameters Named momentum, portfolio, and CPT controls.
     */
    explicit MomentumChartistStrategy(
        MomentumChartistStrategyParameters parameters = MomentumChartistStrategyParameters{});

    /** Returns the export label for momentum chartists. */
    [[nodiscard]] std::string strategyType() const override;

    /** Updates the short and long moving-average windows. */
    void setWindows(std::size_t shortWindow, std::size_t longWindow);

    /** Updates the momentum deadband around a zero moving-average gap. */
    void setMomentumSignalThreshold(double momentumSignalThreshold);

    /** Returns the minimum absolute moving-average gap required for a signal. */
    [[nodiscard]] double momentumSignalThreshold() const;

  protected:
    [[nodiscard]] AgentAction generateSignal(const Market& market) const override;
    [[nodiscard]] double forecastExcessReturn(const Market& market,
                                              std::size_t forecastAssetIndex) const override;

  private:
    [[nodiscard]] double movingAverageGap(const Market& market,
                                          std::size_t forecastAssetIndex) const;

    std::size_t shortWindow_;
    std::size_t longWindow_;
    double momentumSignalThreshold_;
};

} // namespace abm

#endif // ABM_AGENT_STRATEGY_MOMENTUM_CHARTIST_STRATEGY_H
