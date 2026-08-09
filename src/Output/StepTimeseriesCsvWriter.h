// StepTimeseriesCsvWriter.h

#ifndef OUTPUT_STEP_TIMESERIES_CSV_WRITER_H
#define OUTPUT_STEP_TIMESERIES_CSV_WRITER_H

#include <string>

namespace abm {
class SimulationRunResult;

namespace output_detail {

[[nodiscard]] bool exportSimulationDetailsCsv(const std::string& outputPath,
                                              const SimulationRunResult& result,
                                              std::string& error);

} // namespace output_detail
} // namespace abm

#endif // OUTPUT_STEP_TIMESERIES_CSV_WRITER_H
