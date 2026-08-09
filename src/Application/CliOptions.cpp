// CliOptions.cpp

#include "Application/CliOptions.h"

#include "ControlParameters/SimulationConfigIO.h"

#include <iostream>
#include <string>
#include <vector>

namespace abm {

void printSimulationApplicationUsage(const std::string& programName) {
    std::cout << "Usage: " << programName << " [config_file]\n"
              << "   or: " << programName << " --config <config_file>\n"
              << "   or: " << programName << " --help\n";
}

CliParseResult parseSimulationCommandLine(int argc, char** argv) {
    CliParseResult result;
    const std::vector<std::string> arguments(argv, argv + argc);
    const std::string programName = arguments.empty() ? "simulate" : arguments.front();

    const bool showHelp =
        argc > 1 &&
        (arguments.at(1) == "--help" || arguments.at(1) == "-h");
    if (showHelp) {
        printSimulationApplicationUsage(programName);
        result.shouldExit = true;
        result.exitCode = 0;
        return result;
    }

    const bool useExplicitConfigFlag =
        argc > 1 && arguments.at(1) == "--config";
    if (useExplicitConfigFlag) {
        if (argc != 3) {
            printSimulationApplicationUsage(programName);
            result.shouldExit = true;
            result.exitCode = 1;
            return result;
        }
        result.runtimeConfig = loadRuntimeConfig(arguments.at(2));
        return result;
    }

    if (argc > 1) {
        if (argc > 2) {
            printSimulationApplicationUsage(programName);
            result.shouldExit = true;
            result.exitCode = 1;
            return result;
        }
        result.runtimeConfig = loadRuntimeConfig(arguments.at(1));
        return result;
    }

    result.runtimeConfig = loadRuntimeConfig(findDefaultRuntimeConfigPath(programName));
    return result;
}

} // namespace abm
