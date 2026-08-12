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
 * generation. Python post-processing imports staging artefacts into
 * PostgreSQL when enabled and then creates Plotly HTML reports.
 */
struct PythonAnalysisRunResult {
    bool attempted{false};
    bool databaseImportAttempted{false};
    bool databaseImportSucceeded{false};
    bool runReportAttempted{false};
    bool runReportSucceeded{false};
    bool runReportOpenAttempted{false};
    bool runReportOpenSucceeded{false};
    bool comparisonReportAttempted{false};
    bool comparisonReportSucceeded{false};
    std::string databaseImportMessage;
    std::string runReportPath;
    std::string comparisonReportPath;
    std::string runReportOpenMessage;
    std::string message;
};

/**
 * Runs the Python report generator after a completed simulation.
 *
 * The runner is deliberately separated from the simulation engine because visualisation is
 * an output concern, not part of the market mechanism. Failures are reported as
 * warnings so a missing Python dependency does not invalidate completed C++
 * simulation outputs.
 */
class PythonAnalysisRunner {
  public:
    [[nodiscard]] static PythonAnalysisRunResult
    generatePostRunReports(const RuntimeConfig& runtimeConfig);
};

} // namespace abm

#endif // ABM_APPLICATION_PYTHON_ANALYSIS_RUNNER_H
