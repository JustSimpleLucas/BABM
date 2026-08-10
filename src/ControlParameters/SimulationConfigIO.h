// SimulationConfigIO.h

#ifndef ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_IO_H
#define ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_IO_H

#include <string>
#include <vector>

#include "ControlParameters/ConfigDiagnostics.h"
#include "ControlParameters/SimulationConfig.h"

namespace abm {

/**
 * Locates the default simulation configuration file.
 *
 * The search starts from the current working directory and then checks paths
 * relative to the executable. This supports running the model from a build
 * directory while keeping parameters centralised in config/simulation.cfg.
 *
 * @param executablePath argv[0] from the executable entry point.
 * @return Normalised path to the first config/simulation.cfg found.
 * @throws std::runtime_error if no default configuration file exists.
 */
[[nodiscard]] std::string findDefaultRuntimeConfigPath(const std::string& executablePath);

/**
 * Parses a key=value configuration file, collecting every problem it finds.
 *
 * Reading continues past a bad line so one pass reports every malformed entry
 * rather than only the first, which is what lets a user correct a configuration
 * in a single edit instead of one run per mistake. Settings that parsed
 * successfully are still applied, so the returned config is usable for
 * reporting even when diagnostics are present.
 *
 * @param configPath Path to the configuration file.
 * @param diagnostics Receives one entry per problem; existing entries are kept.
 * @return RuntimeConfig holding every setting that applied cleanly.
 * @throws std::runtime_error if the file cannot be opened.
 */
[[nodiscard]] RuntimeConfig readRuntimeConfig(const std::string& configPath,
                                              std::vector<ConfigDiagnostic>& diagnostics);

/**
 * Parses a key=value simulation configuration file.
 *
 * @param configPath Path to the configuration file.
 * @return RuntimeConfig containing simulation parameters, output paths, and provenance.
 * @throws std::runtime_error if the file cannot be opened.
 * @throws std::invalid_argument reporting every malformed key or value at once.
 */
[[nodiscard]] RuntimeConfig loadRuntimeConfig(const std::string& configPath);

} // namespace abm

#endif // ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_IO_H
