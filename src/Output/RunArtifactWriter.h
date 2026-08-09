// RunArtifactWriter.h

#ifndef OUTPUT_RUN_ARTIFACT_WRITER_H
#define OUTPUT_RUN_ARTIFACT_WRITER_H

#include <string>

#include "Analysis/StylisedFactMetrics.h"
#include "ControlParameters/SimulationConfig.h"

namespace abm {

class SimulationRunResult;

/** Metadata returned after writing run artifacts. */
struct RunArtifactWriteResult {
    std::string configHash{};
};

/**
 * Writes all durable artifacts for one completed ABM simulation run.
 *
 * This class centralises the file-format boundary: per-step CSV, final
 * agent-state CSV, optional trade ledger, summary metrics, stylised-fact screening,
 * normalised configuration JSON, run metadata, run log, and experiment
 * manifest updates.
 */
class RunArtifactWriter {
  public:
    /**
     * Writes every configured artifact for a completed run.
     *
     * @param runtimeConfig Runtime configuration with prepared output paths.
     * @param simulationResult Completed immutable simulation output.
     * @param metrics Stylised-fact screening metrics calculated from the run.
     * @param result Populated with derived artifact metadata such as config hash.
     * @param error Human-readable error message on failure.
     * @return true when all artifacts were written successfully.
     */
    [[nodiscard]] static bool writeCompletedRun(const RuntimeConfig& runtimeConfig,
                                                const SimulationRunResult& simulationResult,
                                                const RunMetrics& metrics,
                                                RunArtifactWriteResult& result,
                                                std::string& error);
};

} // namespace abm

#endif // OUTPUT_RUN_ARTIFACT_WRITER_H
