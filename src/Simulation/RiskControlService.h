// RiskControlService.h

#ifndef ABM_SIMULATION_RISK_CONTROL_SERVICE_H
#define ABM_SIMULATION_RISK_CONTROL_SERVICE_H

#include <cstddef>
#include <vector>

#include "Agent/Agent.h"
#include "ControlParameters/SimulationConfig.h"
#include "Results/SimulationRunResult.h"
#include "Simulation/SimulationState.h"

namespace abm {

/** Aggregate effect of broker-enforced forced buy-ins in one simulation step. */
struct ForcedBuyInResult {
    double volume{0.0};
    double transactionCosts{0.0};

    /** Per-asset breakdown in SimulationConfig::assets index order. */
    std::vector<double> volumeByAsset{};
    std::vector<double> transactionCostsByAsset{};
};

/**
 * Applies market-level and broker-style short-sale constraints.
 *
 * The service owns cached short interest so borrow-supply and margin rules can
 * be tested independently from order collection or social influence.
 */
class RiskControlService {
  public:
    /** Recomputes per-asset initial share supply and aggregate short interest for a run. */
    void reset(const SimulationPopulation& population, const SimulationConfig& config);

    /** Returns asset-zero initial share supply used for borrow-supply constraints. */
    [[nodiscard]] double initialShareSupply() const;

    /** Returns the given asset's fixed initial share supply. */
    [[nodiscard]] double initialShareSupply(std::size_t assetIndex) const;

    /** Returns current asset-zero aggregate short interest in shares. */
    [[nodiscard]] double aggregateShortInterest() const;

    /** Returns the given asset's current aggregate short interest in shares. */
    [[nodiscard]] double aggregateShortInterest(std::size_t assetIndex) const;

    /** Updates an agent's asset-zero inventory while maintaining short interest. */
    void updateAgentStockWithShortInterest(Agent& agent, double newStock);

    /** Updates an agent's inventory in one asset while maintaining short interest. */
    void updateAgentStockWithShortInterest(Agent& agent, std::size_t assetIndex, double newStock);

    /** Enforces maintenance margin for a single-asset market (asset index zero). */
    [[nodiscard]] ForcedBuyInResult
    enforceMaintenanceMargin(double marketPrice, std::size_t timeStep,
                             const SimulationConfig& config, const std::vector<Agent*>& agentsById,
                             std::vector<ExternalTradeLedgerRecord>& externalTradeLedger,
                             std::size_t& nextTradeId, bool recordTradeLedger);

    /**
     * Enforces maintenance margin per asset through external forced buy-ins.
     *
     * Margin is checked asset by asset against the agent's shared cash with no
     * cross-asset netting; sequential enforcement in asset-index order may
     * therefore over-cover relative to a portfolio-margin rule. This is a
     * documented modelling simplification.
     */
    [[nodiscard]] ForcedBuyInResult
    enforceMaintenanceMargin(const std::vector<double>& marketPrices, std::size_t timeStep,
                             const SimulationConfig& config, const std::vector<Agent*>& agentsById,
                             std::vector<ExternalTradeLedgerRecord>& externalTradeLedger,
                             std::size_t& nextTradeId, bool recordTradeLedger);

  private:
    std::vector<double> cachedInitialShareSupplyByAsset_{0.0};
    std::vector<double> cachedAggregateShortInterestByAsset_{0.0};
};

} // namespace abm

#endif // ABM_SIMULATION_RISK_CONTROL_SERVICE_H
