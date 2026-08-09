// RunSummaryCsvWriter.h

#ifndef OUTPUT_RUN_SUMMARY_CSV_WRITER_H
#define OUTPUT_RUN_SUMMARY_CSV_WRITER_H

#include <string>

#include "Analysis/StylisedFactMetrics.h"
#include "ControlParameters/SimulationConfig.h"

namespace abm {
class SimulationRunResult;

namespace output_detail {

[[nodiscard]] bool exportSummaryMetricsCsv(const std::string& outputPath,
                                           const RuntimeConfig& runtimeConfig,
                                           const SimulationRunResult& result,
                                           const RunMetrics& metrics, const std::string& configHash,
                                           std::string& error);

} // namespace output_detail
} // namespace abm

#endif // OUTPUT_RUN_SUMMARY_CSV_WRITER_H
