// SimulationState.h

#ifndef ABM_SIMULATION_SIMULATION_STATE_H
#define ABM_SIMULATION_SIMULATION_STATE_H

#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "Agent/Agent.h"
#include "AgentStrategy/TradingStrategy.h"
#include "OrderBook/LimitOrderBook.h"

namespace abm {

/** Weighted neighbour relation in the synthetic social-influence network. */
struct SocialNeighbor {
    std::uint32_t agentId{0};
    double weight{0.0};
};

/** Persistent participant record with swappable active trading strategy. */
struct AgentRecord {
    Agent agent;
    std::string initialStrategyType;
    std::unique_ptr<TradingStrategy> currentStrategy;
};

/** Unified population storage plus stable ID lookup used by execution layers. */
struct SimulationPopulation {
    std::vector<AgentRecord> records{};
    std::vector<Agent*> agentsById{};

    /**
     * Position of the protagonist in `records`, empty when none is configured.
     *
     * Held as an index rather than a flag on AgentRecord because the diagnostics
     * layer needs to reach him directly every step; scanning the population for
     * a flag would turn a constant-time lookup into a linear one on the hot
     * path.
     */
    std::optional<std::size_t> protagonistRecordIndex{};
};

/** Execution and book-state diagnostics produced by one continuous LOB step. */
struct MicrostructureStepResult {
    double netDemand{0.0};
    double tradedVolume{0.0};
    double lastTradePrice{0.0};
    std::size_t submittedLimitOrders{0};
    std::size_t submittedMarketOrders{0};

    /**
     * Legacy aggregate preserved for the step_timeseries contract: stale
     * cancellations plus resting-side infeasibility removals plus anti-livelock
     * cancellations. The split counters below break the aggregate apart.
     */
    std::size_t cancelledOrders{0};
    std::size_t expiredOrders{0};

    /** Resting orders cancelled by the pre-flow stale-order lifecycle rule. */
    std::size_t staleCancelledOrders{0};

    /** Resting orders removed mid-matching because their owner became infeasible. */
    std::size_t infeasibleRestingCancellations{0};

    /** Incoming orders zeroed mid-matching (owner infeasible or anti-livelock guard). */
    std::size_t infeasibleIncomingCancellations{0};

    /** Own resting quotes removed so an agent cannot trade with itself. */
    std::size_t selfTradePreventions{0};

    /** Market orders rejected because execution would breach the price collar. */
    std::size_t collarRejectedOrders{0};

    std::size_t executedTrades{0};
    double totalTransactionCosts{0.0};
    double realizedAllocativeSurplus{0.0};
    double maximumAllocativeSurplus{0.0};
    double allocativeEfficiency{0.0};
    LimitOrderBookMetrics bookMetrics{};
};

/** Resting order lifecycle counts removed before new orders are collected. */
struct RestingOrderLifecycleCounts {
    std::size_t expiredOrders{0};
    std::size_t cancelledOrders{0};
};

/** Price and return implied by the post-clearing transaction state. */
struct PriceFormationResult {
    double nextPrice{0.0};
    double rawReturn{0.0};
    double logReturn{0.0};
};

} // namespace abm

#endif // ABM_SIMULATION_SIMULATION_STATE_H
