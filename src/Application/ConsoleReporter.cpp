// ConsoleReporter.cpp

#include "Application/ConsoleReporter.h"

#include "Metrics/StylisedFactMetrics.h"
#include "Results/SimulationRunResult.h"

#include <algorithm>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <optional>
#include <sstream>
#include <string>

namespace abm {
namespace {

constexpr int kLabelColumnWidth = 34;

[[nodiscard]] std::string formatMemoryMebibytes(const std::optional<std::size_t>& bytes) {
    if (!bytes.has_value()) {
        return "unavailable";
    }

    constexpr double bytesPerMebibyte = 1024.0 * 1024.0;
    std::ostringstream formatted;
    formatted << std::fixed << std::setprecision(2)
              << static_cast<double>(*bytes) / bytesPerMebibyte << " MiB";
    return formatted.str();
}

[[nodiscard]] std::string onOff(bool enabled) {
    return enabled ? "enabled" : "disabled";
}

/**
 * Prints one aligned label/value row.
 *
 * Aligning the values keeps the summary scannable and makes it usable verbatim
 * as a thesis appendix, which is also why no colour or terminal control codes
 * are emitted.
 */
template <typename Value> void printRow(const std::string& label, const Value& value) {
    std::cout << "  " << std::left << std::setw(kLabelColumnWidth) << (label + ':') << ' ' << value
              << '\n';
}

void printSection(const std::string& title) {
    std::cout << '\n' << title << '\n';
}

/** Comma-separated names of the assets that will actually trade. */
[[nodiscard]] std::string describeEnabledAssets(const SimulationConfig& config) {
    std::string described;
    for (const AssetDefinition& asset : config.assets) {
        if (!asset.enabled) {
            continue;
        }
        if (!described.empty()) {
            described += ", ";
        }
        described += asset.name;
    }
    return described.empty() ? "none" : described;
}

[[nodiscard]] std::string describeAgentMix(const SimulationConfig& config) {
    std::ostringstream described;
    described << (config.numFundamentalists + config.numChartists + config.numNoiseTraders +
                  config.numBuyAndHoldAgents)
              << " (" << config.numFundamentalists << " fundamentalists, " << config.numChartists
              << " chartists, " << config.numNoiseTraders << " noise traders, "
              << config.numBuyAndHoldAgents << " buy-and-hold agents)";
    return described.str();
}

} // namespace

void printRunPlan(const RuntimeConfig& runtimeConfig,
                  const std::vector<std::string>& defaultedKeys) {
    const SimulationConfig& config = runtimeConfig.simulation;

    std::cout << "Run plan\n";
    printRow("Config file", runtimeConfig.sourcePath);
    printRow("Assets", describeEnabledAssets(config));
    printRow("Agents", describeAgentMix(config));
    printRow("Steps", std::to_string(config.timeSteps) + " (" + std::to_string(config.warmupSteps) +
                          " warm-up)");
    printRow("Seed", config.seed);
    printRow("Prospect theory", onOff(config.control.prospectTheoryEnabled));
    printRow("Prospect heterogeneity", onOff(config.control.prospectParameterHeterogeneityEnabled));
    printRow("Social influence", onOff(config.social.enabled));
    printRow("Short selling", onOff(config.shortSellingEnabled));
    if (runtimeConfig.output.experimentOutputEnabled) {
        printRow("Experiment", runtimeConfig.output.experimentName);
    }
    if (!defaultedKeys.empty()) {
        printRow("Defaulted settings",
                 std::to_string(defaultedKeys.size()) + " (listed in the run log)");
    }
    std::cout << '\n';
    std::cout.flush();
}

void printCompletedSimulationSummary(const RuntimeConfig& runtimeConfig,
                                     const SimulationRunResult& result, const RunMetrics& metrics,
                                     const ProcessMemoryUsage& memoryUsage) {
    const SimulationConfig& config = result.config();
    const SimulationStats& stats = result.stats();
    const auto& prices = result.marketPriceHistory();
    const auto& fundamentals = result.fundamentalPriceHistory();

    std::cout << std::fixed << std::setprecision(4);
    std::cout << "Simulation completed.\n";

    printSection("Configuration");
    printRow("Config file", runtimeConfig.sourcePath);
    printRow("Asset", config.assetName());
    printRow("Steps", stats.completedSteps);
    printRow("Agents", describeAgentMix(config));
    printRow("Short selling", onOff(config.shortSellingEnabled));
    if (config.shortSellingEnabled) {
        printRow("Short-sale initial margin", config.shortSale.initialMarginRequirement);
        printRow("Short-sale maintenance margin", config.shortSale.maintenanceMarginRequirement);
        printRow("Borrowable supply ratio", config.shortSale.borrowableSupplyRatio);
    }
    printRow("Transaction cost rate", config.transactionCosts.rate);
    printRow("Costs affect decisions", onOff(config.transactionCosts.affectsDecisions));

    printSection("Market outcome");
    printRow("Final market price", stats.finalMarketPrice);
    printRow("Final fundamental price", stats.finalFundamentalPrice);
    printRow("Total traded volume", stats.totalTradedVolume);
    printRow("Total transaction costs", stats.totalTransactionCosts);
    printRow("Avg abs order imbalance", stats.averageAbsoluteOrderImbalance);

    {
        const std::size_t tailCount = std::min<std::size_t>(5, prices.size());
        std::ostringstream tail;
        for (auto priceIt = std::prev(prices.cend(), static_cast<std::ptrdiff_t>(tailCount));
             priceIt != prices.cend(); ++priceIt) {
            tail << ' ' << *priceIt;
        }
        printRow("Last " + std::to_string(tailCount) + " market prices", tail.str());
    }
    {
        const std::size_t tailCount = std::min<std::size_t>(5, fundamentals.size());
        std::ostringstream tail;
        for (auto fundamentalIt =
                 std::prev(fundamentals.cend(), static_cast<std::ptrdiff_t>(tailCount));
             fundamentalIt != fundamentals.cend(); ++fundamentalIt) {
            tail << ' ' << *fundamentalIt;
        }
        printRow("Last " + std::to_string(tailCount) + " fundamentals", tail.str());
    }

    printSection("Diagnostics");
    {
        std::ostringstream efficiency;
        efficiency << metrics.meanAllocativeEfficiency << " over "
                   << metrics.allocativeEfficiencyObservations << " positive-surplus steps";
        printRow("Mean allocative efficiency", efficiency.str());
    }
    printRow("Resident memory", formatMemoryMebibytes(memoryUsage.residentSetBytes));
    printRow("Peak resident memory", formatMemoryMebibytes(memoryUsage.peakResidentSetBytes));

    printSection("Artefacts");
    /*
     * When archiving is on, every artefact lands in one run directory, so the
     * directory is the useful thing to print. The individual paths are only
     * listed when they can genuinely differ, which keeps the summary short in
     * the common case without hiding anything in the uncommon one.
     */
    if (runtimeConfig.output.experimentOutputEnabled) {
        printRow("Run directory", runtimeConfig.output.runDirectoryPath);
        printRow("Experiment manifest", runtimeConfig.output.experimentManifestCsvPath);
        printRow("Trade ledger", runtimeConfig.output.tradeLedgerEnabled
                                     ? "written"
                                     : "disabled (trade_ledger_enabled = 0)");
    } else {
        printRow("Step timeseries CSV", runtimeConfig.output.simulationCsvPath);
        printRow("Agent CSV", runtimeConfig.output.agentCsvPath);
        printRow("Trade ledger CSV", runtimeConfig.output.tradeLedgerEnabled
                                         ? runtimeConfig.output.tradeLedgerCsvPath
                                         : "disabled (trade_ledger_enabled = 0)");
        printRow("Summary metrics CSV", runtimeConfig.output.summaryMetricsCsvPath);
        printRow("Stylised-facts CSV", runtimeConfig.output.stylisedFactsCsvPath);
        printRow("Config JSON", runtimeConfig.output.configJsonPath);
        printRow("Metadata JSON", runtimeConfig.output.metadataJsonPath);
        printRow("Run log", runtimeConfig.output.runLogPath);
    }
    if (runtimeConfig.output.databaseOutputEnabled) {
        printRow("PostgreSQL import",
                 "enabled via " + runtimeConfig.output.databaseUrlEnvironmentVariable);
        printRow("Prune staging after import",
                 onOff(runtimeConfig.output.databasePruneAfterImport));
    }
}

} // namespace abm
