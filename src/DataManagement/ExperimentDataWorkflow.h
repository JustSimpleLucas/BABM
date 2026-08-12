// ExperimentDataWorkflow.h

#ifndef ABM_DATA_MANAGEMENT_EXPERIMENT_DATA_WORKFLOW_H
#define ABM_DATA_MANAGEMENT_EXPERIMENT_DATA_WORKFLOW_H

#include <string>

#include "Config/SimulationConfig.h"
#include "Metrics/StylisedFactMetrics.h"
#include "Output/RunArtifactWriter.h"

namespace abm {

class SimulationRunResult;

/**
 * Coordinates the file-based data workflow for one simulation run.
 *
 * The workflow is intentionally small: it prepares the archive layout, validates
 * the output schema, and delegates durable artifact writing to the existing
 * output layer. It does not own behavioural assumptions, market mechanics, or
 * econometric calculations, which keeps the research model easier to audit.
 */
class ExperimentDataWorkflow {
  public:
    /**
     * Prepares and validates the run archive before the simulation starts.
     *
     * @param runtimeConfig Runtime configuration to update with archive paths.
     * @param error Human-readable error message on failure.
     * @return true when the run has a valid file-based output layout.
     */
    [[nodiscard]] static bool prepareRunArchive(RuntimeConfig& runtimeConfig, std::string& error);

    /**
     * Writes all configured artifacts for a completed simulation run.
     *
     * @param runtimeConfig Runtime configuration with prepared output paths.
     * @param simulationResult Completed immutable simulation output.
     * @param metrics Stylised-fact screening metrics calculated from the run.
     * @param result Populated with derived metadata such as the config hash.
     * @param error Human-readable error message on failure.
     * @return true when the completed run has been durably written.
     */
    [[nodiscard]] static bool writeCompletedRun(const RuntimeConfig& runtimeConfig,
                                                const SimulationRunResult& simulationResult,
                                                const RunMetrics& metrics,
                                                RunArtifactWriteResult& result, std::string& error);
};

} // namespace abm

#endif // ABM_DATA_MANAGEMENT_EXPERIMENT_DATA_WORKFLOW_H
