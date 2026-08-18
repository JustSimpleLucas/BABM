// ConsoleReporter.cpp

#include "Application/ConsoleReporter.h"

#include "Config/SimulationConfigParsing.h"
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
    const std::size_t protagonistCount = config.protagonist.enabled ? 1U : 0U;
    std::ostringstream described;
    described << (config.numFundamentalists + config.numChartists + config.numNoiseTraders +
                  config.numBuyAndHoldAgents + protagonistCount)
              << " (" << config.numFundamentalists << " fundamentalists, " << config.numChartists
              << " chartists, " << config.numNoiseTraders << " noise traders, "
              << config.numBuyAndHoldAgents << " buy-and-hold agents";
    if (config.protagonist.enabled) {
        described << ", plus the protagonist '" << config.protagonist.name << "' running the "
                  << config_parsing::protagonistStrategyKindName(config.protagonist.strategy)
                  << " rule";
    }
    described << ")";
    return described.str();
}

/** End-of-run figures for one traded asset. */
struct AssetOutcome {
    std::string name;
    bool primary{false};
    double finalMarketPrice{0.0};
    double finalFundamentalPrice{0.0};
    double tradedVolume{0.0};
    double transactionCosts{0.0};
};

/**
 * Collects end-of-run figures for every traded asset.
 *
 * The model treats its assets symmetrically -- neither is analytically
 * privileged -- so the summary reports all of them rather than only the asset
 * nominated as primary for the single-asset CSV projection. Volume and costs are
 * accumulated from the per-(step, asset) records, which are the same rows that
 * back asset_timeseries.csv.
 */
[[nodiscard]] std::vector<AssetOutcome> collectAssetOutcomes(const SimulationRunResult& result) {
    const MultiAssetRunData& multiAsset = result.multiAssetData();
    const std::size_t primaryIndex = result.config().assets.primaryIndex();

    std::vector<AssetOutcome> outcomes;
    outcomes.reserve(multiAsset.assetNames.size());
    for (std::size_t assetIndex = 0; assetIndex < multiAsset.assetNames.size(); ++assetIndex) {
        AssetOutcome outcome;
        outcome.name = multiAsset.assetNames[assetIndex];
        outcome.primary = assetIndex == primaryIndex;
        if (assetIndex < multiAsset.marketPriceHistories.size() &&
            !multiAsset.marketPriceHistories[assetIndex].empty()) {
            outcome.finalMarketPrice = multiAsset.marketPriceHistories[assetIndex].back();
        }
        if (assetIndex < multiAsset.fundamentalPriceHistories.size() &&
            !multiAsset.fundamentalPriceHistories[assetIndex].empty()) {
            outcome.finalFundamentalPrice = multiAsset.fundamentalPriceHistories[assetIndex].back();
        }
        outcomes.push_back(std::move(outcome));
    }

    for (const AssetStepDetails& record : multiAsset.assetStepDetails) {
        if (record.assetIndex < outcomes.size()) {
            outcomes[record.assetIndex].tradedVolume += record.tradedVolume;
            outcomes[record.assetIndex].transactionCosts += record.totalTransactionCosts;
        }
    }

    return outcomes;
}

/** Renders the tail of a price history as a single spaced row. */
[[nodiscard]] std::string describePriceTail(const std::vector<double>& history,
                                            std::size_t tailCount) {
    std::ostringstream tail;
    tail << std::fixed << std::setprecision(4);
    const std::size_t shown = std::min(tailCount, history.size());
    for (auto priceIt = std::prev(history.cend(), static_cast<std::ptrdiff_t>(shown));
         priceIt != history.cend(); ++priceIt) {
        tail << ' ' << *priceIt;
    }
    return tail.str();
}

/**
 * Prints the per-asset outcome table with a market-wide total row.
 *
 * The total is the sum of the rows above it rather than SimulationStats, whose
 * totalTradedVolume and totalTransactionCosts accumulate the primary asset's
 * order book alone. Deriving the total here keeps the table internally
 * consistent instead of showing a headline figure that its own rows contradict.
 */
void printAssetOutcomeTable(const std::vector<AssetOutcome>& outcomes) {
    const std::string totalLabel = "all assets";
    std::size_t nameWidth = std::max(std::string("Asset").size(), totalLabel.size());
    for (const AssetOutcome& outcome : outcomes) {
        const std::size_t labelWidth = outcome.name.size() + (outcome.primary ? 10 : 0);
        nameWidth = std::max(nameWidth, labelWidth);
    }

    constexpr int kFigureWidth = 16;
    std::cout << "  " << std::left << std::setw(static_cast<int>(nameWidth)) << "Asset"
              << std::right << std::setw(kFigureWidth) << "final price" << std::setw(kFigureWidth)
              << "fundamental" << std::setw(kFigureWidth) << "volume" << std::setw(kFigureWidth)
              << "costs" << '\n';

    double totalVolume = 0.0;
    double totalCosts = 0.0;
    for (const AssetOutcome& outcome : outcomes) {
        const std::string label = outcome.name + (outcome.primary ? " (primary)" : "");
        std::cout << "  " << std::left << std::setw(static_cast<int>(nameWidth)) << label
                  << std::right << std::setw(kFigureWidth) << outcome.finalMarketPrice
                  << std::setw(kFigureWidth) << outcome.finalFundamentalPrice
                  << std::setw(kFigureWidth) << outcome.tradedVolume << std::setw(kFigureWidth)
                  << outcome.transactionCosts << '\n';
        totalVolume += outcome.tradedVolume;
        totalCosts += outcome.transactionCosts;
    }

    if (outcomes.size() > 1) {
        std::cout << "  " << std::left << std::setw(static_cast<int>(nameWidth)) << totalLabel
                  << std::right << std::setw(kFigureWidth) << "" << std::setw(kFigureWidth) << ""
                  << std::setw(kFigureWidth) << totalVolume << std::setw(kFigureWidth) << totalCosts
                  << '\n';
    }
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

    std::cout << std::fixed << std::setprecision(4);
    std::cout << "Simulation completed.\n";

    printSection("Configuration");
    printRow("Config file", runtimeConfig.sourcePath);
    printRow("Assets", describeEnabledAssets(config));
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
    /*
     * Order imbalance is measured on the primary asset's book alone, so it is
     * labelled with that asset rather than presented as a market-wide figure.
     */
    printRow("Avg abs order imbalance (" + config.assetName() + ")",
             stats.averageAbsoluteOrderImbalance);
    std::cout << '\n';

    const std::vector<AssetOutcome> assetOutcomes = collectAssetOutcomes(result);
    printAssetOutcomeTable(assetOutcomes);

    const MultiAssetRunData& multiAsset = result.multiAssetData();
    constexpr std::size_t kPriceTailCount = 5;
    std::cout << "\n  Last " << kPriceTailCount << " market prices\n";
    for (std::size_t assetIndex = 0; assetIndex < assetOutcomes.size(); ++assetIndex) {
        printRow("  " + assetOutcomes[assetIndex].name,
                 describePriceTail(multiAsset.marketPriceHistories[assetIndex], kPriceTailCount));
    }
    std::cout << "  Last " << kPriceTailCount << " fundamentals\n";
    for (std::size_t assetIndex = 0; assetIndex < assetOutcomes.size(); ++assetIndex) {
        printRow(
            "  " + assetOutcomes[assetIndex].name,
            describePriceTail(multiAsset.fundamentalPriceHistories[assetIndex], kPriceTailCount));
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
