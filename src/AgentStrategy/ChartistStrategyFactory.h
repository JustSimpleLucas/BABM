// ChartistStrategyFactory.h

#ifndef ABM_AGENT_STRATEGY_CHARTIST_STRATEGY_FACTORY_H
#define ABM_AGENT_STRATEGY_CHARTIST_STRATEGY_FACTORY_H

#include <cstddef>
#include <memory>

#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/TradingStrategy.h"
#include "Config/SimulationConfig.h"

namespace abm {
class RandomEngine;

/**
 * Rule-level inputs every concrete chartist strategy is built from.
 *
 * The four technical rules read overlapping subsets of these values, so
 * gathering them once keeps the four construction branches from each carrying
 * their own argument list. The struct also decouples the factory from where the
 * values came from: the anonymous chartist population reads them out of
 * `config.chartist`, while the protagonist reads his own individually
 * configured windows and thresholds.
 */
struct ChartistRuleSettings {
    /** Asset key the strategy quotes on the single-asset path. */
    std::size_t assetIndex{0};

    /** Mean-variance portfolio sizing rule applied to the technical signal. */
    AssetAllocationLine allocationLine;

    /** Short moving-average window used by the momentum rule. */
    std::size_t shortWindow{5};

    /** Long moving-average window used by the momentum and mean-reversion rules. */
    std::size_t longWindow{20};

    /** Deadband applied to weak short-minus-long moving-average gaps. */
    double momentumSignalThreshold{0.0};

    /** Donchian-style lookback whose previous high and low define a breakout. */
    std::size_t breakoutWindow{20};

    /** Recent one-period log returns used to estimate realised volatility. */
    std::size_t volatilityWindow{20};

    /** Maximum absolute short weight available when shorting is enabled. */
    double maxShortWeight{0.30};

    /** Cap on multi-asset gross exposure sum_j |w_j|. */
    double maxGrossExposure{1.0};

    /** Per-step risk-free return used in the allocation rule. */
    double riskFreeRate{0.0};

    /** CPT reference point rule. */
    ProspectReferencePointMode referencePointMode{ProspectReferencePointMode::AveragePurchasePrice};

    /** Reference window used when CPT anchors on moving-average price. */
    std::size_t referenceMovingAverageWindow{20};
};

/**
 * Builds one concrete chartist strategy for an already-decided technical rule.
 *
 * Callers that know which rule they want — the protagonist, and tests pinning a
 * specific rule — use this overload so that no random draw is taken. Passing
 * ChartistStrategyMode::Random falls back to momentum, because a factory that
 * takes no random engine cannot sample.
 */
[[nodiscard]] std::unique_ptr<TradingStrategy>
createChartistStrategy(ChartistStrategyMode mode, const ChartistRuleSettings& settings);

/**
 * Builds concrete chartist strategies from the reproducible simulation config.
 *
 * The factory keeps population construction independent from the concrete
 * chartist class list and makes the random strategy sampling rule explicit in
 * one place.
 */
[[nodiscard]] std::unique_ptr<TradingStrategy>
createChartistStrategy(const SimulationConfig& config, const AssetAllocationLine& allocationLine,
                       RandomEngine& random);

} // namespace abm

#endif // ABM_AGENT_STRATEGY_CHARTIST_STRATEGY_FACTORY_H
