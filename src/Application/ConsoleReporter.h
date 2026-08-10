// ConsoleReporter.h

#ifndef ABM_APPLICATION_CONSOLE_REPORTER_H
#define ABM_APPLICATION_CONSOLE_REPORTER_H

#include "ControlParameters/SimulationConfig.h"
#include "Utility/ProcessMemoryUsage.h"

#include <cstddef>
#include <string>
#include <vector>

namespace abm {

class SimulationRunResult;
struct RunMetrics;

/**
 * Prints what is about to run, before the simulation starts.
 *
 * A long run that turns out to have had a behavioural switch off is wasted
 * time, so the settings that define the experiment are stated up front rather
 * than only in the completion summary.
 *
 * @param runtimeConfig Configuration the run will use.
 * @param defaultedKeys Keys absent from the file, reported as a single count.
 */
void printRunPlan(const RuntimeConfig& runtimeConfig,
                  const std::vector<std::string>& defaultedKeys);

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
