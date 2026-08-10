// ExperimentRunManager.cpp

#include "Experiment/ExperimentRunManager.h"

#include "Output/OutputSerialization.h"

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <iomanip>
#include <sstream>
#include <system_error>
#include <thread>

namespace abm {
namespace {

std::string sanitizePathComponent(const std::string& value) {
    std::string sanitized;
    sanitized.reserve(value.size());
    for (const unsigned char c : value) {
        if (std::isalnum(c) != 0) {
            sanitized.push_back(static_cast<char>(std::tolower(c)));
        } else if (c == '-' || c == '_') {
            sanitized.push_back(static_cast<char>(c));
        } else if (std::isspace(c) != 0) {
            sanitized.push_back('_');
        }
    }

    sanitized.erase(std::unique(sanitized.begin(), sanitized.end(),
                                [](char lhs, char rhs) { return lhs == '_' && rhs == '_'; }),
                    sanitized.end());
    while (!sanitized.empty() && sanitized.front() == '_') {
        sanitized.erase(sanitized.begin());
    }
    while (!sanitized.empty() && sanitized.back() == '_') {
        sanitized.pop_back();
    }

    return sanitized.empty() ? "run" : sanitized;
}

std::tm localTimeFromNow() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t nowTime = std::chrono::system_clock::to_time_t(now);
    std::tm localTime{};
#if defined(_WIN32)
    localtime_s(&localTime, &nowTime);
#else
    localtime_r(&nowTime, &localTime);
#endif
    return localTime;
}

std::string currentTimestampForPath() {
    const std::tm localTime = localTimeFromNow();
    std::ostringstream out;
    out << std::put_time(&localTime, "%Y%m%d%H%M%S");
    return out.str();
}

std::string currentLocalTimestampForMetadata() {
    const std::tm localTime = localTimeFromNow();
    std::ostringstream out;
    out << std::put_time(&localTime, "%Y-%m-%dT%H:%M:%S");
    return out.str();
}

} // namespace

std::string ExperimentRunManager::buildRunId(const SimulationConfig& config,
                                             const std::string& timestamp) {
    std::ostringstream runFolderName;

    /*
     * Numeric-only run identifiers keep large experiment batches easy to sort
     * while preserving the parameter order required by the project convention.
     */
    runFolderName << timestamp << '_'
                  << output_detail::boolToFlag(config.control.prospectTheoryEnabled) << '_'
                  << output_detail::boolToFlag(config.control.prospectParameterHeterogeneityEnabled)
                  << '_' << output_detail::boolToFlag(config.social.enabled) << '_'
                  << output_detail::boolToFlag(config.shortSellingEnabled) << '_'
                  << config.numFundamentalists << '_' << config.numChartists << '_'
                  << config.numNoiseTraders << '_' << config.numBuyAndHoldAgents << '_'
                  << config.timeSteps << '_' << config.seed;

    return runFolderName.str();
}

bool ExperimentRunManager::prepareOutputLayout(RuntimeConfig& runtimeConfig, std::string& error) {
    if (!runtimeConfig.output.experimentOutputEnabled) {
        if (runtimeConfig.output.createdAtLocal.empty()) {
            runtimeConfig.output.createdAtLocal = currentLocalTimestampForMetadata();
        }
        return true;
    }

    namespace fs = std::filesystem;

    const std::string experimentName = sanitizePathComponent(runtimeConfig.output.experimentName);
    const std::string runLabel = sanitizePathComponent(runtimeConfig.output.runLabel);

    const fs::path experimentDirectory =
        fs::path(runtimeConfig.output.experimentRootPath) / experimentName;

    std::error_code ec;
    fs::path runDirectory;
    std::string runId;

    /*
     * The run-id schema has second-level precision. If a smoke experiment is
     * launched twice in the same second, wait for the next timestamp instead of
     * overwriting a previous archive.
     */
    for (int attempt = 0; attempt < 10; ++attempt) {
        runId = buildRunId(runtimeConfig.simulation, currentTimestampForPath());
        runDirectory = experimentDirectory / runId;
        if (!fs::exists(runDirectory)) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    if (fs::exists(runDirectory)) {
        error = "Unable to allocate a unique experiment run directory after repeated attempts: " +
                runDirectory.string();
        return false;
    }

    fs::create_directories(runDirectory, ec);
    if (ec) {
        error = "Unable to create experiment run directory: " + runDirectory.string() + " (" +
                ec.message() + ")";
        return false;
    }

    fs::create_directories(runDirectory / "logs", ec);
    if (ec) {
        error = "Unable to create experiment log directory: " + ec.message();
        return false;
    }
    runtimeConfig.output.experimentName = experimentName;
    runtimeConfig.output.runLabel = runLabel;
    runtimeConfig.output.createdAtLocal = currentLocalTimestampForMetadata();
    runtimeConfig.output.runId = runId;
    runtimeConfig.output.runDirectoryPath = runDirectory.string();
    runtimeConfig.output.experimentManifestCsvPath =
        (experimentDirectory / "experiment_manifest.csv").string();
    runtimeConfig.output.simulationCsvPath = (runDirectory / "step_timeseries.csv").string();
    runtimeConfig.output.assetTimeseriesCsvPath = (runDirectory / "asset_timeseries.csv").string();
    runtimeConfig.output.agentCsvPath = (runDirectory / "agents_final.csv").string();
    runtimeConfig.output.tradeLedgerCsvPath = (runDirectory / "trade_ledger.csv").string();
    runtimeConfig.output.summaryMetricsCsvPath = (runDirectory / "summary_metrics.csv").string();
    runtimeConfig.output.stylisedFactsCsvPath = (runDirectory / "stylised_facts.csv").string();
    runtimeConfig.output.configJsonPath = (runDirectory / "config.json").string();
    runtimeConfig.output.metadataJsonPath = (runDirectory / "metadata.json").string();
    runtimeConfig.output.runLogPath = (runDirectory / "logs" / "run.log").string();

    if (!runtimeConfig.sourcePath.empty()) {
        fs::copy_file(runtimeConfig.sourcePath, runDirectory / "config_used.cfg",
                      fs::copy_options::overwrite_existing, ec);
        if (ec) {
            error = "Unable to copy config into run directory: " + ec.message();
            return false;
        }
    }

    return true;
}

} // namespace abm
