// CliOptions.h

#ifndef ABM_APPLICATION_CLI_OPTIONS_H
#define ABM_APPLICATION_CLI_OPTIONS_H

#include "ControlParameters/SimulationConfig.h"

#include <string>

namespace abm {

/**
 * Result of parsing the executable command line.
 *
 * Help and usage errors are represented as early exits so the application
 * coordinator can keep configuration loading separate from simulation
 * execution.
 */
struct CliParseResult {
    bool shouldExit{false};
    int exitCode{0};
    RuntimeConfig runtimeConfig{};
};

/** Prints the supported command-line forms for the simulation executable. */
void printSimulationApplicationUsage(const std::string& programName);

/**
 * Parses command-line arguments and loads the requested runtime configuration.
 *
 * The parser accepts only full configuration files. Experiment parameters
 * should be changed in config files so runs remain reproducible and auditable.
 *
 * @throws std::exception when configuration loading fails.
 */
[[nodiscard]] CliParseResult parseSimulationCommandLine(int argc, char** argv);

} // namespace abm

#endif // ABM_APPLICATION_CLI_OPTIONS_H
