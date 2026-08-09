// RunMetadataWriters.cpp

#include "Output/RunMetadataWriters.h"

#include "Output/OutputSerialization.h"
#include "Results/SimulationRunResult.h"

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <system_error>

#ifndef ABM_MODEL_VERSION
#define ABM_MODEL_VERSION "unknown"
#endif

#ifndef ABM_GIT_COMMIT
#define ABM_GIT_COMMIT "unknown"
#endif

#ifndef ABM_GIT_DIRTY
#define ABM_GIT_DIRTY 0
#endif

#ifndef ABM_COMPILER_ID
#define ABM_COMPILER_ID "unknown"
#endif

#ifndef ABM_COMPILER_VERSION
#define ABM_COMPILER_VERSION "unknown"
#endif

namespace abm::output_detail {
namespace {

std::filesystem::path metadataReferenceDirectory(const std::string& outputPath,
                                                 const RuntimeConfig& runtimeConfig) {
    if (runtimeConfig.output.experimentOutputEnabled &&
        !runtimeConfig.output.runDirectoryPath.empty()) {
        return {runtimeConfig.output.runDirectoryPath};
    }

    const std::filesystem::path metadataPath(outputPath);
    const std::filesystem::path parentPath = metadataPath.parent_path();
    return parentPath.empty() ? std::filesystem::path(".") : parentPath;
}

std::string portableMetadataPath(const std::string& pathValue,
                                 const std::filesystem::path& referenceDirectory) {
    if (pathValue.empty()) {
        return {};
    }

    const std::filesystem::path path = std::filesystem::path(pathValue).lexically_normal();
    const std::filesystem::path reference = referenceDirectory.lexically_normal();
    const std::filesystem::path relativePath = path.lexically_relative(reference);

    /*
     * Metadata should remain useful when a run archive is moved to another
     * machine. Paths inside the run folder are written relative to that folder;
     * project files are written relative to the current project directory; and
     * other absolute paths fall back to their filename so local Mac user
     * directories are not baked into the research artefact.
     */
    if (!relativePath.empty() && *relativePath.begin() != "..") {
        return relativePath.generic_string();
    }
    if (path.is_absolute()) {
        std::error_code ec;
        const std::filesystem::path currentDirectory =
            std::filesystem::current_path(ec).lexically_normal();
        if (!ec) {
            const std::filesystem::path projectRelativePath =
                path.lexically_relative(currentDirectory);
            if (!projectRelativePath.empty() && *projectRelativePath.begin() != "..") {
                return projectRelativePath.generic_string();
            }
        }
        return path.filename().generic_string();
    }
    return path.generic_string();
}

} // namespace

bool exportConfigJson(const ConfigJsonExportRequest& request, std::string& error) {
    if (!ensureParentDirectoryExists(request.outputPath, error)) {
        return false;
    }

    std::ofstream out(request.outputPath);
    if (!out.is_open()) {
        error = "Unable to open config JSON file: " + request.outputPath;
        return false;
    }

    out << request.normalizedConfigJson;
    out.flush();
    if (!out.good()) {
        error = "Failed while writing config JSON file: " + request.outputPath;
        return false;
    }
    return true;
}

bool exportMetadataJson(const std::string& outputPath, const RuntimeConfig& runtimeConfig,
                        const SimulationRunResult& result, const RunMetrics& metrics,
                        const std::string& configHash, std::string& error) {
    if (!ensureParentDirectoryExists(outputPath, error)) {
        return false;
    }

    std::ofstream out(outputPath);
    if (!out.is_open()) {
        error = "Unable to open metadata file: " + outputPath;
        return false;
    }

    const SimulationConfig& config = result.config();
    const SimulationStats& stats = result.stats();
    const std::filesystem::path referenceDirectory =
        metadataReferenceDirectory(outputPath, runtimeConfig);
    const std::string archivedConfigPath =
        runtimeConfig.output.experimentOutputEnabled ? "config_used.cfg" : runtimeConfig.sourcePath;
    const std::string sourceConfigPathForMetadata =
        portableMetadataPath(runtimeConfig.sourcePath, referenceDirectory);
    const std::string archivedConfigPathForMetadata =
        portableMetadataPath(archivedConfigPath, referenceDirectory);

    out << std::fixed << std::setprecision(10);
    out << "{\n";
    out << R"(  "run_id": ")" << jsonEscape(runtimeConfig.output.runId) << R"(",)" << '\n';
    out << R"(  "experiment_name": ")" << jsonEscape(runtimeConfig.output.experimentName) << R"(",)"
        << '\n';
    out << R"(  "run_label": ")" << jsonEscape(runtimeConfig.output.runLabel) << R"(",)" << '\n';
    out << R"(  "created_at_local": ")" << jsonEscape(runtimeConfig.output.createdAtLocal)
        << R"(",)" << '\n';
    out << R"(  "status": "completed",)" << '\n';
    out << R"(  "config_hash": ")" << jsonEscape(configHash) << R"(",)" << '\n';
    out << R"(  "model_version": ")" << jsonEscape(ABM_MODEL_VERSION) << R"(",)" << '\n';
    out << R"(  "git_commit": ")" << jsonEscape(ABM_GIT_COMMIT) << R"(",)" << '\n';
    out << R"(  "git_dirty": )" << jsonBool(ABM_GIT_DIRTY != 0) << ",\n";
    out << R"(  "compiler": {)" << '\n';
    out << R"(    "id": ")" << jsonEscape(ABM_COMPILER_ID) << R"(",)" << '\n';
    out << R"(    "version": ")" << jsonEscape(ABM_COMPILER_VERSION) << R"(",)" << '\n';
    out << R"(    "cplusplus": )" << __cplusplus << '\n';
    out << "  },\n";
    out << R"(  "source_config_path": ")" << jsonEscape(sourceConfigPathForMetadata) << R"(",)"
        << '\n';
    out << R"(  "archived_config_path": ")" << jsonEscape(archivedConfigPathForMetadata) << R"(",)"
        << '\n';
    out << R"(  "outputs": {)" << '\n';
    out << R"(    "step_timeseries_csv": ")"
        << jsonEscape(
               portableMetadataPath(runtimeConfig.output.simulationCsvPath, referenceDirectory))
        << R"(",)" << '\n';
    out << R"(    "agents_final_csv": ")"
        << jsonEscape(portableMetadataPath(runtimeConfig.output.agentCsvPath, referenceDirectory))
        << R"(",)" << '\n';
    out << R"(    "asset_timeseries_enabled": )"
        << jsonBool(runtimeConfig.output.assetTimeseriesEnabled) << ",\n";
    out << R"(    "asset_timeseries_csv": )";
    if (runtimeConfig.output.assetTimeseriesEnabled) {
        out << '"'
            << jsonEscape(portableMetadataPath(runtimeConfig.output.assetTimeseriesCsvPath,
                                               referenceDirectory))
            << '"';
    } else {
        out << "null";
    }
    out << ",\n";
    out << R"(    "trade_ledger_enabled": )" << jsonBool(runtimeConfig.output.tradeLedgerEnabled)
        << ",\n";
    out << R"(    "trade_ledger_csv": )";
    if (runtimeConfig.output.tradeLedgerEnabled) {
        out << '"'
            << jsonEscape(portableMetadataPath(runtimeConfig.output.tradeLedgerCsvPath,
                                               referenceDirectory))
            << '"';
    } else {
        out << "null";
    }
    out << ",\n";
    out << R"(    "summary_metrics_csv": ")"
        << jsonEscape(
               portableMetadataPath(runtimeConfig.output.summaryMetricsCsvPath, referenceDirectory))
        << R"(",)" << '\n';
    out << R"(    "stylised_facts_csv": ")"
        << jsonEscape(
               portableMetadataPath(runtimeConfig.output.stylisedFactsCsvPath, referenceDirectory))
        << R"(",)" << '\n';
    out << R"(    "config_json": ")"
        << jsonEscape(portableMetadataPath(runtimeConfig.output.configJsonPath, referenceDirectory))
        << R"(",)" << '\n';
    out << R"(    "run_log": ")"
        << jsonEscape(portableMetadataPath(runtimeConfig.output.runLogPath, referenceDirectory))
        << '"' << '\n';
    out << "  },\n";
    out << R"(  "parameters": {)" << '\n';
    out << R"(    "asset_name": ")" << jsonEscape(config.assetName()) << R"(",)" << '\n';
    out << R"(    "seed": )" << config.seed << ",\n";
    out << R"(    "time_steps": )" << config.timeSteps << ",\n";
    out << R"(    "warmup_steps": )" << config.warmupSteps << ",\n";
    out << R"(    "num_fundamentalists": )" << config.numFundamentalists << ",\n";
    out << R"(    "num_chartists": )" << config.numChartists << ",\n";
    out << R"(    "num_noise_traders": )" << config.numNoiseTraders << ",\n";
    out << R"(    "num_buy_and_hold_agents": )" << config.numBuyAndHoldAgents << ",\n";
    out << R"(    "buy_hold_target_risky_weight": )"
        << config.buyAndHold.targetRiskyWeight << ",\n";
    out << R"(    "fundamental_shock_std_dev": )" << config.fundamentalShockStdDev() << ",\n";
    out << R"(    "fundamental_drift_per_step": )" << config.fundamentalDriftPerStep() << ",\n";
    out << R"(    "minimum_fundamental_value": )" << config.minimumFundamentalValue() << ",\n";
    out << R"(    "transaction_cost_rate": )" << config.transactionCosts.rate << ",\n";
    out << R"(    "transaction_cost_affects_decisions": )"
        << jsonBool(config.transactionCosts.affectsDecisions) << ",\n";
    out << R"(    "transaction_cost_apply_to_forced_buy_ins": )"
        << jsonBool(config.transactionCosts.applyToForcedBuyIns) << ",\n";
    out << R"(    "chartist_strategy_mode": ")"
        << jsonEscape(chartistStrategyModeLabel(config.chartist.strategyMode)) << R"(",)" << '\n';
    out << R"(    "chartist_momentum_signal_threshold": )"
        << config.chartist.momentumSignalThreshold << ",\n";
    out << R"(    "chartist_breakout_window": )" << config.chartist.breakoutWindow << ",\n";
    out << R"(    "prospect_theory_enabled": )" << jsonBool(config.control.prospectTheoryEnabled)
        << ",\n";
    out << R"(    "prospect_theory_agent_fraction": )" << config.control.prospectTheoryAgentFraction
        << ",\n";
    out << R"(    "prospect_heterogeneity_enabled": )"
        << jsonBool(config.control.prospectParameterHeterogeneityEnabled) << ",\n";
    out << R"(    "social_enabled": )" << jsonBool(config.social.enabled) << ",\n";
    out << R"(    "short_selling_enabled": )" << jsonBool(config.shortSellingEnabled) << '\n';
    out << "  },\n";
    out << R"(  "summary_metrics": {)" << '\n';
    out << R"(    "completed_steps": )" << stats.completedSteps << ",\n";
    out << R"(    "final_market_price": )" << stats.finalMarketPrice << ",\n";
    out << R"(    "final_fundamental_price": )" << stats.finalFundamentalPrice << ",\n";
    out << R"(    "total_traded_volume": )" << stats.totalTradedVolume << ",\n";
    out << R"(    "total_transaction_costs": )" << stats.totalTransactionCosts << ",\n";
    out << R"(    "mean_log_return": )" << metrics.meanLogReturn << ",\n";
    out << R"(    "log_return_std_dev": )" << metrics.logReturnStdDev << ",\n";
    out << R"(    "excess_kurtosis": )" << metrics.excessKurtosis << ",\n";
    out << R"(    "max_drawdown": )" << metrics.maxDrawdown << ",\n";
    out << R"(    "mean_allocative_efficiency": )" << metrics.meanAllocativeEfficiency << ",\n";
    out << R"(    "allocative_efficiency_observations": )"
        << metrics.allocativeEfficiencyObservations << ",\n";
    out << R"(    "final_wealth_gini_coefficient": )"
        << metrics.finalWealthGiniCoefficient << '\n';
    out << "  }\n";
    out << "}\n";

    out.flush();
    if (!out.good()) {
        error = "Failed while writing metadata file: " + outputPath;
        return false;
    }
    return true;
}

bool exportRunLog(const std::string& outputPath, const RuntimeConfig& runtimeConfig,
                  const SimulationRunResult& result, const RunMetrics& metrics,
                  const std::string& configHash, std::string& error) {
    if (!ensureParentDirectoryExists(outputPath, error)) {
        return false;
    }

    std::ofstream out(outputPath);
    if (!out.is_open()) {
        error = "Unable to open run log: " + outputPath;
        return false;
    }

    const SimulationConfig& config = result.config();
    const SimulationStats& stats = result.stats();

    out << std::fixed << std::setprecision(10);
    out << "ABM experiment run log\n";
    out << "Created at local time: " << runtimeConfig.output.createdAtLocal << '\n';
    out << "Run ID: " << runtimeConfig.output.runId << '\n';
    out << "Experiment: " << runtimeConfig.output.experimentName << '\n';
    out << "Run label: " << runtimeConfig.output.runLabel << '\n';
    out << "Config hash: " << configHash << '\n';
    out << "Source config: " << runtimeConfig.sourcePath << '\n';
    out << "Git commit: " << ABM_GIT_COMMIT << '\n';
    out << "Git dirty: " << jsonBool(ABM_GIT_DIRTY != 0) << '\n';
    out << "Compiler: " << ABM_COMPILER_ID << ' ' << ABM_COMPILER_VERSION << '\n';
    out << "\nKey parameters\n";
    out << "Seed: " << config.seed << '\n';
    out << "Time steps: " << config.timeSteps << '\n';
    out << "Warm-up steps: " << config.warmupSteps << '\n';
    out << "Fundamentalists: " << config.numFundamentalists << '\n';
    out << "Chartists: " << config.numChartists << '\n';
    out << "Noise traders: " << config.numNoiseTraders << '\n';
    out << "Buy-and-hold agents: " << config.numBuyAndHoldAgents << '\n';
    out << "Buy-and-hold target risky weight: " << config.buyAndHold.targetRiskyWeight << '\n';
    out << "Fundamental shock stddev: " << config.fundamentalShockStdDev() << '\n';
    out << "Fundamental drift per step: " << config.fundamentalDriftPerStep() << '\n';
    out << "Minimum fundamental value: " << config.minimumFundamentalValue() << '\n';
    out << "Transaction cost rate: " << config.transactionCosts.rate << '\n';
    out << "Transaction costs affect decisions: "
        << boolToFlag(config.transactionCosts.affectsDecisions) << '\n';
    out << "Transaction costs apply to forced buy-ins: "
        << boolToFlag(config.transactionCosts.applyToForcedBuyIns) << '\n';
    out << "Prospect Theory enabled: " << boolToFlag(config.control.prospectTheoryEnabled) << '\n';
    out << "Prospect Theory agent fraction: " << config.control.prospectTheoryAgentFraction << '\n';
    out << "Prospect heterogeneity enabled: "
        << boolToFlag(config.control.prospectParameterHeterogeneityEnabled) << '\n';
    out << "Social influence enabled: " << boolToFlag(config.social.enabled) << '\n';
    out << "Short selling enabled: " << boolToFlag(config.shortSellingEnabled) << '\n';
    out << "Trade ledger enabled: " << boolToFlag(runtimeConfig.output.tradeLedgerEnabled) << '\n';
    out << "\nRun summary\n";
    out << "Completed steps: " << stats.completedSteps << '\n';
    out << "Final market price: " << stats.finalMarketPrice << '\n';
    out << "Final fundamental price: " << stats.finalFundamentalPrice << '\n';
    out << "Total traded volume: " << stats.totalTradedVolume << '\n';
    out << "Total transaction costs: " << stats.totalTransactionCosts << '\n';
    out << "Average absolute order imbalance: " << stats.averageAbsoluteOrderImbalance << '\n';
    out << "Mean log return: " << metrics.meanLogReturn << '\n';
    out << "Log-return standard deviation: " << metrics.logReturnStdDev << '\n';
    out << "Excess kurtosis: " << metrics.excessKurtosis << '\n';
    out << "Maximum drawdown: " << metrics.maxDrawdown << '\n';
    out << "Mean allocative efficiency: " << metrics.meanAllocativeEfficiency << '\n';
    out << "Allocative-efficiency observations: " << metrics.allocativeEfficiencyObservations
        << '\n';
    out << "Final wealth Gini coefficient: " << metrics.finalWealthGiniCoefficient << '\n';
    out << "Lag-1 raw-return autocorrelation: " << metrics.lag1ReturnAutocorrelation << '\n';
    out << "Lag-1 absolute-return autocorrelation: " << metrics.lag1AbsoluteReturnAutocorrelation
        << '\n';
    out << "Lag-1 squared-return autocorrelation: " << metrics.lag1SquaredReturnAutocorrelation
        << '\n';
    out << "\nStylised-fact screening conclusions\n";
    out << "Autocorrelation: " << metrics.autocorrelationConclusion << '\n';
    out << "Fat tails: " << metrics.fatTailsConclusion << '\n';
    out << "Volatility clustering: " << metrics.volatilityClusteringConclusion << '\n';

    out.flush();
    if (!out.good()) {
        error = "Failed while writing run log: " + outputPath;
        return false;
    }
    return true;
}

} // namespace abm::output_detail
