// ExperimentManifestWriter.h

#ifndef OUTPUT_EXPERIMENT_MANIFEST_WRITER_H
#define OUTPUT_EXPERIMENT_MANIFEST_WRITER_H

#include <string>

#include "Analysis/StylisedFactMetrics.h"
#include "ControlParameters/SimulationConfig.h"

namespace abm {

class SimulationRunResult;

/**
 * Appends one completed run to the experiment-level manifest.
 *
 * The manifest stores run identifiers and comparable summary fields, not
 * duplicated output paths, so parameter sweeps remain compact and thesis
 * analysis can join by run_id.
 */
[[nodiscard]] bool appendExperimentManifest(const RuntimeConfig& runtimeConfig,
                                            const SimulationRunResult& result,
                                            const RunMetrics& metrics,
                                            const std::string& configHash,
                                            std::string& error);

} // namespace abm

#endif // OUTPUT_EXPERIMENT_MANIFEST_WRITER_H
