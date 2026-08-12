// ChartistStrategyFactory.h

#ifndef ABM_AGENT_STRATEGY_CHARTIST_STRATEGY_FACTORY_H
#define ABM_AGENT_STRATEGY_CHARTIST_STRATEGY_FACTORY_H

#include <memory>

#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/TradingStrategy.h"
#include "Config/SimulationConfig.h"

namespace abm {
class RandomEngine;

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
