// ProtagonistTimeseriesCsvWriter.h

#ifndef ABM_OUTPUT_PROTAGONIST_TIMESERIES_CSV_WRITER_H
#define ABM_OUTPUT_PROTAGONIST_TIMESERIES_CSV_WRITER_H

#include <string>

namespace abm {
class SimulationRunResult;

namespace output_detail {

/**
 * Writes the protagonist's per-step position and standing in the wealth
 * cross-section.
 *
 * Produces a header-only file when no protagonist was configured, so a caller
 * that writes the artefact unconditionally still yields a readable file rather
 * than an empty one.
 */
[[nodiscard]] bool exportProtagonistTimeseriesCsv(const std::string& outputPath,
                                                  const SimulationRunResult& result,
                                                  std::string& error);

} // namespace output_detail
} // namespace abm

#endif // ABM_OUTPUT_PROTAGONIST_TIMESERIES_CSV_WRITER_H
