// SimulationApplication.cpp

#include "Application/SimulationApplication.h"

#include "Application/CliOptions.h"
#include "Application/ConfigInspection.h"
#include "Application/ConsoleReporter.h"
#include "Application/PythonAnalysisRunner.h"
#include "Config/ConfigDiagnostics.h"
#include "Config/ConfigKeyRegistry.h"
#include "DataManagement/ExperimentDataWorkflow.h"
#include "Metrics/StylisedFactMetrics.h"
#include "Simulation/SimulationEngine.h"
#include "Utility/ConsoleProgressBar.h"
#include "Utility/ProcessMemoryUsage.h"

#include <exception>
#include <iostream>
#include <string>
#include <vector>

namespace abm {
namespace {

void printPythonAnalysisStatus(const PythonAnalysisRunResult& result) {
    if (!result.attempted) {
        return;
    }

    if (result.databaseImportAttempted && result.databaseImportSucceeded) {
        std::cout << "PostgreSQL import: completed\n";
    }
    if (result.databaseImportAttempted && !result.databaseImportSucceeded) {
        std::cerr << "PostgreSQL import warning: " << result.databaseImportMessage << '\n';
    }
}

} // namespace

int runSimulationApplication(int argc, char** argv) {
    RuntimeConfig runtimeConfig;
    const std::vector<std::string> arguments(argv, argv + argc);
    const std::string programName = arguments.empty() ? "simulate" : arguments.front();

    CliParseResult parseResult;
    try {
        parseResult = parseSimulationCommandLine(argc, argv);
        if (parseResult.shouldExit) {
            return parseResult.exitCode;
        }
    } catch (const std::exception& ex) {
        std::cerr << "Configuration error: " << ex.what() << '\n';
        printSimulationApplicationUsage(programName);
        return 1;
    }

    if (parseResult.mode == SimulationRunMode::ConfigReference) {
        printConfigKeyReference(std::cout);
        return 0;
    }

    runtimeConfig = parseResult.runtimeConfig;
    const std::vector<std::string> defaultedKeys = findDefaultedConfigKeys(runtimeConfig);

    /*
     * Configuration problems are reported before anything is created on disk.
     * Validation used to happen inside the simulation engine, which runs after
     * the archive directory has already been prepared, so an invalid config left
     * an empty run folder behind every time it was rejected.
     */
    if (countConfigErrors(parseResult.diagnostics) != 0) {
        std::cerr << renderConfigDiagnostics(parseResult.diagnostics) << '\n'
                  << "No simulation was run and no output directory was created.\n";
        return 1;
    }

    if (parseResult.mode == SimulationRunMode::Validate) {
        printResolvedConfiguration(std::cout, runtimeConfig);
        printDefaultedConfigKeys(std::cout, defaultedKeys);
        std::cout << "\nConfiguration is valid.\n";
        return 0;
    }

    try {
        printRunPlan(runtimeConfig, defaultedKeys);

        std::string error;
        if (!ExperimentDataWorkflow::prepareRunArchive(runtimeConfig, error)) {
            std::cerr << "Output setup failed: " << error << '\n';
            return 1;
        }

        const SimulationConfig& config = runtimeConfig.simulation;
        SimulationEngine simulationEngine(config);
        // The bar goes to the diagnostic stream so redirected stdout holds only
        // the summary and the artefact paths.
        ConsoleProgressBar progressBar(std::cerr, config.timeSteps, "Simulation progress", 40,
                                       !parseResult.quietProgress);
        const SimulationRunResult simulationResult = simulationEngine.run(
            [&progressBar](std::size_t completedSteps, std::size_t /* totalSteps */) {
                progressBar.update(completedSteps);
            },
            runtimeConfig.output.tradeLedgerEnabled);
        progressBar.finish();
        const ProcessMemoryUsage memoryUsage = sampleProcessMemoryUsage();

        const RunMetrics metrics = calculateRunMetrics(simulationResult);
        RunArtifactWriteResult artifactResult;
        if (!ExperimentDataWorkflow::writeCompletedRun(runtimeConfig, simulationResult, metrics,
                                                       artifactResult, error)) {
            std::cerr << error << '\n';
            return 1;
        }

        printCompletedSimulationSummary(runtimeConfig, simulationResult, metrics, memoryUsage);
        std::cout.flush();

        const PythonAnalysisRunResult pythonAnalysisResult =
            PythonAnalysisRunner::runPostRunProcessing(runtimeConfig);
        printPythonAnalysisStatus(pythonAnalysisResult);
    } catch (const std::exception& ex) {
        std::cerr << "Simulation failed: " << ex.what() << '\n';
        return 1;
    }

    return 0;
}

} // namespace abm
