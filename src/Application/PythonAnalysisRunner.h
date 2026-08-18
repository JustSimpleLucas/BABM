// PythonAnalysisRunner.h

#ifndef ABM_APPLICATION_PYTHON_ANALYSIS_RUNNER_H
#define ABM_APPLICATION_PYTHON_ANALYSIS_RUNNER_H

#include "Config/SimulationConfig.h"

#include <string>

namespace abm {

/**
 * Result of the optional Python post-processing step.
 *
 * The C++ simulation remains the authority for model execution and artefact
 * generation. Python post-processing imports a completed run's staging
 * artefacts into PostgreSQL; reading those results is the job of the analysis
 * package's dashboard, which is started separately and never by the simulator.
 */
struct PythonAnalysisRunResult {
    bool attempted{false};
    bool databaseImportAttempted{false};
    bool databaseImportSucceeded{false};
    std::string databaseImportMessage;
    std::string message;
};

/**
 * Runs the Python database import after a completed simulation.
 *
 * The runner is deliberately separated from the simulation engine because
 * post-processing is an output concern, not part of the market mechanism.
 * Failures are reported as warnings so a missing Python dependency does not
 * invalidate completed C++ simulation outputs.
 */
class PythonAnalysisRunner {
  public:
    [[nodiscard]] static PythonAnalysisRunResult
    runPostRunProcessing(const RuntimeConfig& runtimeConfig);
};

} // namespace abm

#endif // ABM_APPLICATION_PYTHON_ANALYSIS_RUNNER_H
