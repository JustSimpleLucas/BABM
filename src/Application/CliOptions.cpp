// CliOptions.cpp

#include "Application/CliOptions.h"

#include "ControlParameters/SimulationConfigIO.h"
#include "ControlParameters/SimulationConfigValidation.h"

#include <iostream>
#include <string>
#include <vector>

namespace abm {
namespace {

/** Marks the parse as a usage failure that should print help and exit non-zero. */
void failWithUsage(CliParseResult& result, const std::string& programName,
                   const std::string& reason) {
    std::cerr << "Command-line error: " << reason << '\n';
    printSimulationApplicationUsage(programName);
    result.shouldExit = true;
    result.exitCode = 1;
}

} // namespace

void printSimulationApplicationUsage(const std::string& programName) {
    std::cout
        << "Usage: " << programName << " [options] [config_file]\n"
        << "   or: " << programName << " --config <config_file> [options]\n"
        << '\n'
        << "Options:\n"
        << "  --config <file>     Configuration file to run. May also be given positionally.\n"
        << "  --validate, --check Check the configuration, print the resolved settings,\n"
        << "                      and exit without running or writing anything.\n"
        << "  --config-reference  Print the configuration key reference as markdown.\n"
        << "  --quiet-progress    Suppress the live progress bar.\n"
        << "  --help, -h          Show this message.\n"
        << '\n'
        << "Experiment parameters are changed in the configuration file, never on the\n"
        << "command line, so every run traces back to an archived file.\n";
}

CliParseResult parseSimulationCommandLine(int argc, char** argv) {
    CliParseResult result;
    const std::vector<std::string> arguments(argv, argv + argc);
    const std::string programName = arguments.empty() ? "simulate" : arguments.front();

    std::string configPath;
    bool configPathGiven = false;

    for (std::size_t index = 1; index < arguments.size(); ++index) {
        const std::string& argument = arguments[index];

        if (argument == "--help" || argument == "-h") {
            printSimulationApplicationUsage(programName);
            result.shouldExit = true;
            result.exitCode = 0;
            return result;
        }
        if (argument == "--validate" || argument == "--check") {
            result.mode = SimulationRunMode::Validate;
            continue;
        }
        if (argument == "--config-reference") {
            result.mode = SimulationRunMode::ConfigReference;
            continue;
        }
        if (argument == "--quiet-progress") {
            result.quietProgress = true;
            continue;
        }
        if (argument == "--config") {
            if (index + 1 >= arguments.size()) {
                failWithUsage(result, programName, "--config needs a file path.");
                return result;
            }
            if (configPathGiven) {
                failWithUsage(result, programName, "more than one configuration file was given.");
                return result;
            }
            configPath = arguments[++index];
            configPathGiven = true;
            continue;
        }
        if (argument.rfind("--", 0) == 0) {
            failWithUsage(result, programName, "unknown option '" + argument + "'.");
            return result;
        }
        if (configPathGiven) {
            failWithUsage(result, programName, "more than one configuration file was given.");
            return result;
        }
        configPath = argument;
        configPathGiven = true;
    }

    /*
     * The key reference is derived from the compiled-in registry, so it is
     * produced without reading a configuration file at all.
     */
    if (result.mode == SimulationRunMode::ConfigReference) {
        return result;
    }

    if (!configPathGiven) {
        configPath = findDefaultRuntimeConfigPath(programName);
    }

    result.runtimeConfig = readRuntimeConfig(configPath, result.diagnostics);

    /*
     * Validation runs even when parsing reported problems. A key that failed to
     * apply keeps its built-in default, and defaults satisfy every constraint,
     * so the extra pass cannot invent spurious findings; it only adds the
     * constraint failures a reader would otherwise discover one run later.
     */
    collectSimulationConfigDiagnostics(result.runtimeConfig.simulation,
                                       result.runtimeConfig.provenance, result.diagnostics);

    return result;
}

} // namespace abm
