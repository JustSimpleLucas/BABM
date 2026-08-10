// SimulationConfigIO.h

#ifndef ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_IO_H
#define ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_IO_H

#include <string>

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
 * Parses a key=value simulation configuration file.
 *
 * @param configPath Path to the configuration file.
 * @return RuntimeConfig containing simulation parameters, output paths, and provenance.
 * @throws std::runtime_error if the file cannot be opened.
 * @throws std::invalid_argument if a key or value is malformed.
 */
[[nodiscard]] RuntimeConfig loadRuntimeConfig(const std::string& configPath);

} // namespace abm

#endif // ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_IO_H
