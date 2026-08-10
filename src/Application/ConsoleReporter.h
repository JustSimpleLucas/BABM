// ConsoleReporter.h

#ifndef ABM_APPLICATION_CONSOLE_REPORTER_H
#define ABM_APPLICATION_CONSOLE_REPORTER_H

#include "ControlParameters/SimulationConfig.h"
#include "Utility/ProcessMemoryUsage.h"

namespace abm {

class SimulationRunResult;
struct RunMetrics;

/**
 * Prints a compact terminal summary for a completed simulation run.
 *
 * The reporter is intentionally separate from artifact export. Console output
 * is for interactive inspection, while CSV/JSON files are the reproducible
 * research record.
 */
void printCompletedSimulationSummary(const RuntimeConfig& runtimeConfig,
                                     const SimulationRunResult& result, const RunMetrics& metrics,
                                     const ProcessMemoryUsage& memoryUsage);

} // namespace abm

#endif // ABM_APPLICATION_CONSOLE_REPORTER_H
