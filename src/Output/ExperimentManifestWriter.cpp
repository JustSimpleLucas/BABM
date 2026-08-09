// ExperimentManifestWriter.cpp

#include "Output/ExperimentManifestWriter.h"

#include "Output/OutputSerialization.h"
#include "Results/SimulationRunResult.h"

#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <sstream>
#include <string>
#include <system_error>
#include <vector>

namespace abm {
namespace {

const std::vector<std::string>& experimentManifestColumns() {
    static const std::vector<std::string> columns{
        "run_id",
        "experiment_name",
        "run_label",
        "created_at_local",
        "status",
        "config_hash",
        "seed",
        "time_steps",
        "warmup_steps",
        "fundamental_shock_std_dev",
        "fundamental_drift_per_step",
        "minimum_fundamental_value",
        "num_fundamentalists",
        "num_chartists",
        "num_noise_traders",
        "num_buy_and_hold_agents",
        "buy_hold_target_risky_weight",
        "control_prospect_theory_enabled",
        "control_prospect_theory_agent_fraction",
        "control_prospect_heterogeneity_enabled",
        "social_enabled",
        "short_selling_enabled",
        "loss_aversion",
        "prospect_scenario_count",
        "final_market_price",
        "final_fundamental_price",
        "final_wealth_gini_coefficient",
        "total_traded_volume",
        "average_absolute_order_imbalance",
        "mean_allocative_efficiency",
        "allocative_efficiency_observations",
        "mean_log_return",
        "log_return_std_dev",
        "excess_kurtosis",
        "max_drawdown",
        "lag1_return_autocorrelation",
        "lag1_abs_return_autocorrelation",
        "lag1_squared_return_autocorrelation",
        "stylised_absence_autocorrelation_conclusion",
        "stylised_fat_tails_conclusion",
        "stylised_volatility_clustering_conclusion"};
    return columns;
}

std::string makeCsvRow(const std::vector<std::string>& values) {
    std::ostringstream out;
    bool firstValue = true;
    for (const std::string& value : values) {
        if (!firstValue) {
            out << ',';
        }
        out << output_detail::csvEscape(value);
        firstValue = false;
    }
    return out.str();
}

std::vector<std::string> parseCsvRow(const std::string& line) {
    std::vector<std::string> fields;
    std::string field;
    bool insideQuotes = false;

    for (auto charIt = line.cbegin(); charIt != line.cend(); ++charIt) {
        const char c = *charIt;
        if (insideQuotes) {
            if (c == '"') {
                const auto nextIt = std::next(charIt);
                if (nextIt != line.cend() && *nextIt == '"') {
                    field.push_back('"');
                    charIt = nextIt;
                } else {
                    insideQuotes = false;
                }
            } else {
                field.push_back(c);
            }
        } else if (c == '"') {
            insideQuotes = true;
        } else if (c == ',') {
            fields.push_back(field);
            field.clear();
        } else if (c != '\r') {
            field.push_back(c);
        }
    }

    fields.push_back(field);
    return fields;
}

bool migrateExperimentManifestSchema(const std::string& manifestPath, std::string& error) {
    namespace fs = std::filesystem;

    if (!fs::exists(manifestPath)) {
        return true;
    }

    std::ifstream input(manifestPath);
    if (!input.is_open()) {
        error = "Unable to read experiment manifest: " + manifestPath;
        return false;
    }

    std::vector<std::string> lines;
    std::string line;
    while (std::getline(input, line)) {
        lines.push_back(line);
    }

    const std::vector<std::string>& targetColumns = experimentManifestColumns();
    if (lines.empty()) {
        return true;
    }

    const std::vector<std::string> existingColumns = parseCsvRow(lines.front());
    if (existingColumns == targetColumns) {
        return true;
    }

    std::map<std::string, std::size_t> existingColumnIndex;
    std::size_t existingColumnPosition = 0;
    for (const std::string& existingColumn : existingColumns) {
        existingColumnIndex.emplace(existingColumn, existingColumnPosition);
        ++existingColumnPosition;
    }

    const fs::path temporaryPath = fs::path(manifestPath).concat(".tmp");
    std::ofstream output(temporaryPath);
    if (!output.is_open()) {
        error = "Unable to prepare migrated experiment manifest: " + temporaryPath.string();
        return false;
    }

    output << makeCsvRow(targetColumns) << '\n';
    for (auto lineIt = std::next(lines.cbegin()); lineIt != lines.cend(); ++lineIt) {
        if (lineIt->empty()) {
            continue;
        }

        const std::vector<std::string> oldValues = parseCsvRow(*lineIt);
        std::vector<std::string> migratedValues;
        migratedValues.reserve(targetColumns.size());
        for (const std::string& targetColumn : targetColumns) {
            const auto existing = existingColumnIndex.find(targetColumn);
            if (existing == existingColumnIndex.end() || existing->second >= oldValues.size()) {
                migratedValues.emplace_back();
            } else {
                migratedValues.push_back(oldValues.at(existing->second));
            }
        }
        output << makeCsvRow(migratedValues) << '\n';
    }

    output.flush();
    if (!output.good()) {
        error = "Failed while writing migrated experiment manifest: " + temporaryPath.string();
        return false;
    }

    std::error_code ec;
    fs::rename(temporaryPath, manifestPath, ec);
    if (ec) {
        error = "Unable to replace experiment manifest with migrated schema: " + ec.message();
        return false;
    }

    return true;
}

std::vector<std::string> buildExperimentManifestRow(const RuntimeConfig& runtimeConfig,
                                                    const SimulationRunResult& result,
                                                    const RunMetrics& metrics,
                                                    const std::string& configHash) {
    const SimulationConfig& config = result.config();
    const SimulationStats& stats = result.stats();

    return {
        runtimeConfig.output.runId,
        runtimeConfig.output.experimentName,
        runtimeConfig.output.runLabel,
        runtimeConfig.output.createdAtLocal,
        "completed",
        configHash,
        std::to_string(config.seed),
        std::to_string(config.timeSteps),
        std::to_string(config.warmupSteps),
        output_detail::formatFixedDouble(config.fundamentalShockStdDev()),
        output_detail::formatFixedDouble(config.fundamentalDriftPerStep()),
        output_detail::formatFixedDouble(config.minimumFundamentalValue()),
        std::to_string(config.numFundamentalists),
        std::to_string(config.numChartists),
        std::to_string(config.numNoiseTraders),
        std::to_string(config.numBuyAndHoldAgents),
        output_detail::formatFixedDouble(config.buyAndHold.targetRiskyWeight),
        std::to_string(output_detail::boolToFlag(config.control.prospectTheoryEnabled)),
        output_detail::formatFixedDouble(config.control.prospectTheoryAgentFraction),
        std::to_string(
            output_detail::boolToFlag(config.control.prospectParameterHeterogeneityEnabled)),
        std::to_string(output_detail::boolToFlag(config.social.enabled)),
        std::to_string(output_detail::boolToFlag(config.shortSellingEnabled)),
        output_detail::formatFixedDouble(config.control.lossAversion),
        std::to_string(config.control.prospectScenarioCount),
        output_detail::formatFixedDouble(stats.finalMarketPrice),
        output_detail::formatFixedDouble(stats.finalFundamentalPrice),
        output_detail::formatFixedDouble(metrics.finalWealthGiniCoefficient),
        output_detail::formatFixedDouble(stats.totalTradedVolume),
        output_detail::formatFixedDouble(stats.averageAbsoluteOrderImbalance),
        output_detail::formatFixedDouble(metrics.meanAllocativeEfficiency),
        std::to_string(metrics.allocativeEfficiencyObservations),
        output_detail::formatFixedDouble(metrics.meanLogReturn),
        output_detail::formatFixedDouble(metrics.logReturnStdDev),
        output_detail::formatFixedDouble(metrics.excessKurtosis),
        output_detail::formatFixedDouble(metrics.maxDrawdown),
        output_detail::formatFixedDouble(metrics.lag1ReturnAutocorrelation),
        output_detail::formatFixedDouble(metrics.lag1AbsoluteReturnAutocorrelation),
        output_detail::formatFixedDouble(metrics.lag1SquaredReturnAutocorrelation),
        metrics.autocorrelationConclusion,
        metrics.fatTailsConclusion,
        metrics.volatilityClusteringConclusion};
}

} // namespace

bool appendExperimentManifest(const RuntimeConfig& runtimeConfig,
                              const SimulationRunResult& result,
                              const RunMetrics& metrics,
                              const std::string& configHash,
                              std::string& error) {
    if (!runtimeConfig.output.experimentOutputEnabled) {
        return true;
    }
    if (!output_detail::ensureParentDirectoryExists(
            runtimeConfig.output.experimentManifestCsvPath,
            error)) {
        return false;
    }
    if (!migrateExperimentManifestSchema(runtimeConfig.output.experimentManifestCsvPath, error)) {
        return false;
    }

    const bool shouldWriteHeader =
        !std::filesystem::exists(runtimeConfig.output.experimentManifestCsvPath) ||
        std::filesystem::file_size(runtimeConfig.output.experimentManifestCsvPath) == 0;

    std::ofstream out(runtimeConfig.output.experimentManifestCsvPath, std::ios::app);
    if (!out.is_open()) {
        error = "Unable to open experiment manifest: " +
                runtimeConfig.output.experimentManifestCsvPath;
        return false;
    }

    if (shouldWriteHeader) {
        out << makeCsvRow(experimentManifestColumns()) << '\n';
    }

    out << makeCsvRow(
               buildExperimentManifestRow(runtimeConfig, result, metrics, configHash))
        << '\n';

    out.flush();
    if (!out.good()) {
        error = "Failed while writing experiment manifest: " +
                runtimeConfig.output.experimentManifestCsvPath;
        return false;
    }
    return true;
}

} // namespace abm
