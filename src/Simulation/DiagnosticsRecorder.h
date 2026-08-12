// DiagnosticsRecorder.h

#ifndef ABM_SIMULATION_DIAGNOSTICS_RECORDER_H
#define ABM_SIMULATION_DIAGNOSTICS_RECORDER_H

#include <cstddef>
#include <vector>

#include "Config/SimulationConfig.h"
#include "Market/Market.h"
#include "Results/SimulationRunResult.h"
#include "Simulation/SimulationState.h"

namespace abm {

/** Inputs required to record one completed simulation step. */
struct StepRecordingRequest {
    std::size_t step{0};
    const SimulationConfig* config{nullptr};
    std::size_t populationSize{0};
    double referencePrice{0.0};
    double newFundamental{0.0};
    std::size_t submittedOrders{0};
    const MicrostructureStepResult* microstructureResult{nullptr};
    const PriceFormationResult* priceResult{nullptr};
    const SimulationPopulation* population{nullptr};

    /** Per-asset step outputs in config asset order; null on single-asset legacy paths. */
    const std::vector<MicrostructureStepResult>* perAssetResults{nullptr};
    const std::vector<PriceFormationResult>* perAssetPriceResults{nullptr};
    const std::vector<double>* referencePrices{nullptr};
    const std::vector<double>* newFundamentals{nullptr};
};

/**
 * Builds output-facing diagnostics from simulation events.
 *
 * Diagnostics are kept outside the engine so empirical stylised-fact outputs
 * can evolve without changing behavioural or market-clearing mechanics.
 */
class DiagnosticsRecorder {
  public:
    /** Clears run-local diagnostics and initialises aggregate statistics. */
    void resetForRun(const SimulationConfig& config, std::size_t populationSize,
                     const Market& market, bool recordTradeLedger);

    /** Returns the mutable trade ledger used by clearing and risk controls when enabled. */
    [[nodiscard]] std::vector<ExternalTradeLedgerRecord>& externalTradeLedger();

    /** Returns the mutable run-local trade ID counter. */
    [[nodiscard]] std::size_t* nextTradeIdCounter();

    /** Records one post-clearing simulation step and updates aggregate statistics. */
    void recordStep(const StepRecordingRequest& request);

    /** Finalises averages and captures final agent-level state. */
    void completeRun(const SimulationPopulation& population);

    /** Builds the immutable completed-run result consumed outside the engine. */
    [[nodiscard]] SimulationRunResult buildResult(const SimulationConfig& config,
                                                  const Market& market);

    /** Returns aggregate statistics under construction. */
    [[nodiscard]] const SimulationStats& stats() const;

    /** Returns per-step diagnostics under construction. */
    [[nodiscard]] const std::vector<StepDetails>& stepDetails() const;

  private:
    void refreshAgentSnapshots(const SimulationPopulation& population);
    [[nodiscard]] static double
    calculateWealthGiniCoefficient(const SimulationPopulation& population);

    void recordAssetSteps(const StepRecordingRequest& request);

    SimulationStats stats_{};
    std::vector<StepDetails> stepDetails_;
    std::vector<AssetStepDetails> assetStepDetails_;
    std::vector<AgentSnapshot> agentSnapshots_;
    std::vector<ExternalTradeLedgerRecord> externalTradeLedger_;
    std::size_t nextTradeId_{1};
};

} // namespace abm

#endif // ABM_SIMULATION_DIAGNOSTICS_RECORDER_H
