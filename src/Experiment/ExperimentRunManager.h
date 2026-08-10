// ExperimentRunManager.h

#ifndef ABM_EXPERIMENT_EXPERIMENT_RUN_MANAGER_H
#define ABM_EXPERIMENT_EXPERIMENT_RUN_MANAGER_H

#include <string>

#include "ControlParameters/SimulationConfig.h"

namespace abm {

/**
 * Creates the reproducible folder layout for one simulation run.
 *
 * The manager centralises experiment archival policy so the executable does not
 * need to know how run identifiers, manifests, logs, and parameter
 * snapshots are arranged on disk. This keeps the output convention stable when
 * larger parameter sweeps are added later.
 */
class ExperimentRunManager {
  public:
    /**
     * Builds the required numeric run identifier for one ABM configuration.
     *
     * @param config Fully resolved simulation configuration.
     * @param timestamp Local timestamp in YYYYMMDDHHMMSS format.
     * @return Run identifier following the thesis project convention.
     */
    [[nodiscard]] static std::string buildRunId(const SimulationConfig& config,
                                                const std::string& timestamp);

    /**
     * Prepares output directories and assigns all run-specific artifact paths.
     *
     * When experiment archiving is disabled, this only records the local
     * creation timestamp and leaves the explicit latest-output paths unchanged.
     *
     * @param runtimeConfig Runtime configuration to update in place.
     * @param error Human-readable error message on failure.
     * @return true when the layout is ready for writing simulation artifacts.
     */
    [[nodiscard]] static bool prepareOutputLayout(RuntimeConfig& runtimeConfig, std::string& error);
};

} // namespace abm

#endif // ABM_EXPERIMENT_EXPERIMENT_RUN_MANAGER_H
