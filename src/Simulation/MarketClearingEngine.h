// MarketClearingEngine.h

#ifndef SIMULATION_MARKET_CLEARING_ENGINE_H
#define SIMULATION_MARKET_CLEARING_ENGINE_H

#include <cstddef>
#include <vector>

#include "ControlParameters/SimulationConfig.h"
#include "OrderBook/LimitOrderBook.h"
#include "OrderBook/Order.h"
#include "RandomGenerator/RandomGenerator.h"
#include "Simulation/RiskControlService.h"
#include "Results/SimulationRunResult.h"
#include "Simulation/SimulationState.h"

namespace abm {

/**
 * Inputs for applying resting-order lifecycle rules before new order flow.
 *
 * Reference prices are supplied per asset in SimulationConfig::assets index
 * order; missing entries fall back to zero, which disables the mispricing
 * component of stale cancellation for that book.
 */
struct RestingOrderProcessingRequest {
    std::size_t timeStep{0};
    const std::vector<double>* referencePrices{nullptr};
    const MicrostructureConfig* config{nullptr};
};

/**
 * Inputs for one continuous-double-auction clearing pass.
 *
 * Grouping these references keeps the execution boundary explicit: the engine
 * supplies orders, institutional controls, agent lookup, and optional ledger
 * storage, while this component owns only matching and accounting mechanics.
 * Reference prices and lifecycle counts are per asset in
 * SimulationConfig::assets index order.
 */
struct OrderExecutionRequest {
    const std::vector<Order>* orders{nullptr};
    const std::vector<double>* referencePrices{nullptr};
    std::vector<RestingOrderLifecycleCounts> lifecycleCounts{};
    const SimulationConfig* config{nullptr};
    const std::vector<Agent*>* agentsById{nullptr};
    RiskControlService* riskControls{nullptr};
    std::vector<ExternalTradeLedgerRecord>* externalTradeLedger{nullptr};
    std::size_t* nextTradeId{nullptr};
    bool recordTradeLedger{false};
};

/**
 * Executes orders through one persistent continuous limit-order book per asset.
 *
 * This component owns market-clearing mechanics only. It delegates balance
 * sheet and borrow-supply updates to the risk-control service, making the
 * institutional constraint assumptions independently testable. Orders are
 * routed to the book selected by Order::assetIndex; books never cross assets.
 */
class MarketClearingEngine {
  public:
    /** Clears all resting orders and sizes one book per asset before a run. */
    void resetForRun(std::size_t assetCount);

    /** Clears all resting orders, preserving the current book count. */
    void clear();

    /** Applies order expiry and stale-order cancellation to every book. */
    [[nodiscard]] std::vector<RestingOrderLifecycleCounts>
    processRestingOrders(const RestingOrderProcessingRequest& request, RandomEngine& random);

    /** Matches submitted orders per asset and returns one result per book. */
    [[nodiscard]] std::vector<MicrostructureStepResult>
    executeOrders(const OrderExecutionRequest& request);

  private:
    std::vector<LimitOrderBook> orderBooks_ = std::vector<LimitOrderBook>(1);
};

} // namespace abm

#endif // SIMULATION_MARKET_CLEARING_ENGINE_H
