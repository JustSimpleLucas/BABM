// RunMetadataWriters.h

#ifndef ABM_OUTPUT_RUN_METADATA_WRITERS_H
#define ABM_OUTPUT_RUN_METADATA_WRITERS_H

#include <string>

#include "Config/SimulationConfig.h"
#include "Metrics/StylisedFactMetrics.h"

namespace abm {

class SimulationRunResult;

namespace output_detail {

/**
 * Identifies the resolved configuration JSON artefact to write.
 *
 * The output path and JSON payload are both strings, so grouping them prevents
 * accidental argument swaps at call sites.
 */
struct ConfigJsonExportRequest {
    std::string outputPath;
    std::string normalizedConfigJson;
};

[[nodiscard]] bool exportConfigJson(const ConfigJsonExportRequest& request, std::string& error);

[[nodiscard]] bool exportMetadataJson(const std::string& outputPath,
                                      const RuntimeConfig& runtimeConfig,
                                      const SimulationRunResult& result, const RunMetrics& metrics,
                                      const std::string& configHash, std::string& error);

[[nodiscard]] bool exportRunLog(const std::string& outputPath, const RuntimeConfig& runtimeConfig,
                                const SimulationRunResult& result, const RunMetrics& metrics,
                                const std::string& configHash, std::string& error);

} // namespace output_detail
} // namespace abm

#endif // ABM_OUTPUT_RUN_METADATA_WRITERS_H
