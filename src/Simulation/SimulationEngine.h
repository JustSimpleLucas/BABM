// SimulationEngine.h

#ifndef ABM_SIMULATION_SIMULATION_ENGINE_H
#define ABM_SIMULATION_SIMULATION_ENGINE_H

#include <functional>

#include "ControlParameters/SimulationConfig.h"
#include "Market/FundamentalValueProcess.h"
#include "Market/Market.h"
#include "RandomGenerator/RandomGenerator.h"
#include "Results/SimulationRunResult.h"
#include "Simulation/AgentActivationScheduler.h"
#include "Simulation/DiagnosticsRecorder.h"
#include "Simulation/MarketClearingEngine.h"
#include "Simulation/OrderCollector.h"
#include "Simulation/RiskControlService.h"
#include "Simulation/SimulationClock.h"
#include "Simulation/SocialInfluenceModel.h"

namespace abm {

/**
 * High-level orchestrator for one agent-based market simulation.
 *
 * The engine coordinates the clock, population, social influence, market
 * process, order collection, clearing, risk controls, and diagnostics. Domain
 * assumptions live in those collaborators rather than in this controller.
 */
class SimulationEngine {
  public:
    /** Receives completed and total simulation steps after each simulated period. */
    using ProgressCallback = SimulationClock::ProgressCallback;

    /** Validates configuration and initialises agents, social state, and market history. */
    explicit SimulationEngine(SimulationConfig config = {});

    /**
     * Runs the complete post-warm-up simulation and returns immutable run output.
     *
     * @param progressCallback Optional callback for terminal or UI progress reporting.
     * @param recordTradeLedger Enables detailed counterparty-level audit rows when true.
     */
    [[nodiscard]] SimulationRunResult run(const ProgressCallback& progressCallback = {},
                                          bool recordTradeLedger = false);

    /** Returns the effective simulation configuration after validation/clamping. */
    [[nodiscard]] const SimulationConfig& config() const;

  private:
    /** Returns each asset's latest stored market price in config asset order. */
    [[nodiscard]] std::vector<double> latestMarketPrices() const;

    SimulationConfig config_;
    Market market_;

    /*
     * Two independent streams, both derived from the single configured seed.
     * Keeping the fundamental process on its own stream means a change to the
     * number of agent-side draws cannot perturb the fundamental path, so
     * behavioural experiments remain comparable against a fixed seed.
     */
    FundamentalValueProcess fundamentalProcess_;
    RandomEngine random_;
    SimulationPopulation population_{};
    SocialInfluenceModel socialInfluenceModel_{};
    AgentActivationScheduler activationScheduler_{};
    OrderCollector orderCollector_{};
    MarketClearingEngine marketClearingEngine_{};
    RiskControlService riskControlService_{};
    DiagnosticsRecorder diagnosticsRecorder_{};
};

} // namespace abm

#endif // ABM_SIMULATION_SIMULATION_ENGINE_H
