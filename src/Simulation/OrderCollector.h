// OrderCollector.h

#ifndef ABM_SIMULATION_ORDER_COLLECTOR_H
#define ABM_SIMULATION_ORDER_COLLECTOR_H

#include <cstddef>
#include <vector>

#include "ControlParameters/SimulationConfig.h"
#include "Market/Market.h"
#include "OrderBook/Order.h"
#include "RandomGenerator/RandomGenerator.h"
#include "Simulation/SimulationState.h"
#include "Utility/CholeskyFactorization.h"

namespace abm {

/**
 * Converts scheduled active agents into fully annotated order submissions.
 *
 * Strategy classes decide desired side, price, and quantity. The collector adds
 * simulation timing and microstructure style while preserving the no-social
 * baseline as valuation-based limit pricing.
 */
class OrderCollector {
  public:
    /** Resets deterministic order identifiers before a fresh simulation run. */
    void resetForRun();

    /**
     * Collects orders from the scheduled active population indices.
     *
     * @param covariance Shared per-step log-return covariance in asset index
     * order. Required: the engine estimates it every step, and strategies price
     * against it whether the universe holds one asset or several.
     */
    [[nodiscard]] std::vector<Order>
    collectOrders(std::size_t timeStep, const std::vector<std::size_t>& activeAgentIndices,
                  SimulationPopulation& population, const Market& market,
                  const SimulationConfig& config, RandomEngine& random,
                  const SymmetricMatrix& covariance);

  private:
    int nextOrderId_{1};
};

} // namespace abm

#endif // ABM_SIMULATION_ORDER_COLLECTOR_H
