// CliOptions.h

#ifndef ABM_APPLICATION_CLI_OPTIONS_H
#define ABM_APPLICATION_CLI_OPTIONS_H

#include "ControlParameters/ConfigDiagnostics.h"
#include "ControlParameters/SimulationConfig.h"

#include <string>
#include <vector>

namespace abm {

/** What the executable was asked to do with the configuration it was given. */
enum class SimulationRunMode {
    /** Run the simulation and write its artefacts. */
    Simulate,
    /** Check the configuration, report the resolved settings, and exit. */
    Validate,
    /** Print the configuration key reference as markdown and exit. */
    ConfigReference,
};

/**
 * Result of parsing the executable command line.
 *
 * Help and usage errors are represented as early exits so the application
 * coordinator can keep configuration loading separate from simulation
 * execution. Configuration problems are returned as diagnostics rather than
 * thrown, so every problem in a file can be reported in one pass.
 */
struct CliParseResult {
    bool shouldExit{false};
    int exitCode{0};
    SimulationRunMode mode{SimulationRunMode::Simulate};

    /** Suppresses the live progress bar; presentation only, never a model input. */
    bool quietProgress{false};

    RuntimeConfig runtimeConfig{};
    std::vector<ConfigDiagnostic> diagnostics{};
};

/** Prints the supported command-line forms for the simulation executable. */
void printSimulationApplicationUsage(const std::string& programName);

/**
 * Parses command-line arguments and loads the requested runtime configuration.
 *
 * The parser accepts only full configuration files plus flags that change how a
 * run is reported, never individual experiment parameters. Experiment
 * parameters are changed in config files so runs remain reproducible and
 * auditable.
 *
 * @throws std::exception when the configuration file cannot be opened at all.
 */
[[nodiscard]] CliParseResult parseSimulationCommandLine(int argc, char** argv);

} // namespace abm

#endif // ABM_APPLICATION_CLI_OPTIONS_H
