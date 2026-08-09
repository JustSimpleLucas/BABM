#include "tests/TestSupport.h"

#include "Analysis/StylisedFactMetrics.h"
#include "DataManagement/ExperimentDataWorkflow.h"
#include "DataManagement/RunArchiveSchema.h"
#include "Experiment/ExperimentRunManager.h"
#include "Simulation/SimulationEngine.h"

#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::string readTextFile(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::string content;
    std::string line;
    while (std::getline(input, line)) {
        content += line;
        content += '\n';
    }
    return content;
}

void testExperimentRunIdUsesProjectSchema(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.control.prospectTheoryEnabled = true;
    config.control.prospectParameterHeterogeneityEnabled = true;
    config.social.enabled = false;
    config.shortSellingEnabled = true;
    config.numFundamentalists = 100;
    config.numChartists = 1500;
    config.numNoiseTraders = 25;
    config.numBuyAndHoldAgents = 10;
    config.timeSteps = 1000;
    config.seed = 66;

    const std::string runId = abm::ExperimentRunManager::buildRunId(config, "20260427143012");

    abm::test::expect(runId == "20260427143012_1_1_0_1_100_1500_25_10_1000_66",
                      "experiment run ID should follow the documented numeric schema", failures);
}

void testExperimentRunManagerDoesNotCreateUnusedPlotsDirectory(int& failures) {
    namespace fs = std::filesystem;

    const fs::path outputRoot = fs::temp_directory_path() / "abm_run_manager_layout_test";
    std::error_code cleanupError;
    fs::remove_all(outputRoot, cleanupError);

    abm::RuntimeConfig runtimeConfig;
    runtimeConfig.simulation = abm::test::deterministicSmokeConfig();
    runtimeConfig.output.experimentOutputEnabled = true;
    runtimeConfig.output.experimentRootPath = outputRoot.string();
    runtimeConfig.output.experimentName = "layout_test";
    runtimeConfig.output.runLabel = "no_plots_directory";

    std::string error;
    const bool prepared = abm::ExperimentRunManager::prepareOutputLayout(runtimeConfig, error);

    abm::test::expect(prepared,
                      "experiment run manager should prepare the archived output layout: " + error,
                      failures);
    const fs::path runDirectory(runtimeConfig.output.runDirectoryPath);
    abm::test::expect(fs::exists(runDirectory / "logs"),
                      "experiment archive should still create the logs directory", failures);
    abm::test::expect(!fs::exists(runDirectory / "plots"),
                      "experiment archive should not create the unused plots directory", failures);

    fs::remove_all(outputRoot, cleanupError);
}

void testRunArchiveSchemaRejectsMissingRequiredPaths(int& failures) {
    abm::RuntimeConfig runtimeConfig;
    runtimeConfig.output.simulationCsvPath.clear();

    std::string error;
    const bool valid = abm::validatePreparedRunArchive(runtimeConfig, error);

    abm::test::expect(!valid,
                      "run archive schema validation should reject missing core artifact paths",
                      failures);
    abm::test::expect(error.find("step-timeseries CSV path") != std::string::npos,
                      "run archive schema error should name the missing artifact path", failures);

    runtimeConfig.output.simulationCsvPath = "step_timeseries.csv";
    runtimeConfig.output.experimentOutputEnabled = true;
    runtimeConfig.output.runId.clear();
    runtimeConfig.output.runDirectoryPath = "run_directory";
    runtimeConfig.output.experimentManifestCsvPath = "experiment_manifest.csv";
    error.clear();

    const bool archiveIdentityValid = abm::validatePreparedRunArchive(runtimeConfig, error);
    abm::test::expect(!archiveIdentityValid,
                      "archived output validation should require a run identifier", failures);
    abm::test::expect(error.find("run identifier") != std::string::npos,
                      "archived output validation should name the missing run identifier",
                      failures);
}

void testExperimentDataWorkflowWritesArchivedRunsAndManifest(int& failures) {
    namespace fs = std::filesystem;

    const fs::path outputRoot = fs::temp_directory_path() / "abm_data_workflow_archive_test";
    std::error_code cleanupError;
    fs::remove_all(outputRoot, cleanupError);

    std::vector<std::string> runIds;
    fs::path manifestPath;

    for (const unsigned int seed : std::vector<unsigned int>{20260421U, 20260422U}) {
        abm::RuntimeConfig runtimeConfig;
        runtimeConfig.simulation = abm::test::deterministicSmokeConfig();
        runtimeConfig.simulation.seed = seed;
        runtimeConfig.output.experimentOutputEnabled = true;
        runtimeConfig.output.experimentRootPath = outputRoot.string();
        runtimeConfig.output.experimentName = "Data Workflow Test";
        runtimeConfig.output.runLabel = "archive smoke";
        runtimeConfig.output.tradeLedgerEnabled = false;
        runtimeConfig.output.pythonAnalysisEnabled = false;
        runtimeConfig.output.pythonAnalysisComparisonEnabled = false;

        std::string error;
        const bool prepared = abm::ExperimentDataWorkflow::prepareRunArchive(runtimeConfig, error);
        abm::test::expect(
            prepared, "data workflow should prepare and validate an archived run layout: " + error,
            failures);

        const fs::path runDirectory(runtimeConfig.output.runDirectoryPath);
        abm::test::expect(fs::exists(runDirectory / "logs"),
                          "data workflow should preserve the run log directory", failures);
        abm::test::expect(!runtimeConfig.output.runId.empty(),
                          "data workflow should assign a reproducible run identifier", failures);

        abm::SimulationEngine simulation(runtimeConfig.simulation);
        const abm::SimulationRunResult simulationResult =
            simulation.run({}, runtimeConfig.output.tradeLedgerEnabled);
        const abm::RunMetrics metrics = abm::calculateRunMetrics(simulationResult);

        abm::RunArtifactWriteResult writeResult;
        error.clear();
        const bool wrote = abm::ExperimentDataWorkflow::writeCompletedRun(
            runtimeConfig, simulationResult, metrics, writeResult, error);
        abm::test::expect(wrote,
                          "data workflow should write completed archived run artifacts: " + error,
                          failures);

        for (const abm::RunArchivePathRequirement& requirement :
             abm::requiredRunArtifactPaths(runtimeConfig.output)) {
            abm::test::expect(fs::exists(requirement.path) && fs::is_regular_file(requirement.path),
                              "data workflow should create " + requirement.label, failures);
        }
        abm::test::expect(!fs::exists(runtimeConfig.output.tradeLedgerCsvPath),
                          "data workflow should keep disabled trade ledger optional", failures);

        manifestPath = runtimeConfig.output.experimentManifestCsvPath;
        runIds.push_back(runtimeConfig.output.runId);
    }

    abm::test::expect(runIds.size() == 2 && runIds[0] != runIds[1],
                      "data workflow should assign distinct run IDs across replicated seeds",
                      failures);

    const std::string manifestContent = readTextFile(manifestPath);
    std::istringstream manifestStream(manifestContent);
    std::string manifestLine;
    int nonEmptyLineCount = 0;
    while (std::getline(manifestStream, manifestLine)) {
        if (!manifestLine.empty()) {
            ++nonEmptyLineCount;
        }
    }
    abm::test::expect(nonEmptyLineCount == 3,
                      "experiment manifest should contain one header and two completed runs",
                      failures);
    abm::test::expect(manifestContent.find("final_wealth_gini_coefficient") != std::string::npos,
                      "experiment manifest should export the final wealth Gini coefficient",
                      failures);
    for (const std::string& runId : runIds) {
        abm::test::expect(manifestContent.find(runId) != std::string::npos,
                          "experiment manifest should index archived run " + runId, failures);
    }

    fs::remove_all(outputRoot, cleanupError);
}

} // namespace

namespace abm::test {

void runArchiveWorkflowTests(int& failures) {
    testExperimentRunIdUsesProjectSchema(failures);
    testExperimentRunManagerDoesNotCreateUnusedPlotsDirectory(failures);
    testRunArchiveSchemaRejectsMissingRequiredPaths(failures);
    testExperimentDataWorkflowWritesArchivedRunsAndManifest(failures);
}

} // namespace abm::test
