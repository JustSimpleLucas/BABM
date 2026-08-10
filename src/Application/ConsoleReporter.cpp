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

} // namespace

void printCompletedSimulationSummary(const RuntimeConfig& runtimeConfig,
                                     const SimulationRunResult& result, const RunMetrics& metrics,
                                     const ProcessMemoryUsage& memoryUsage) {
    const SimulationConfig& config = result.config();
    const SimulationStats& stats = result.stats();
    const auto& prices = result.marketPriceHistory();
    const auto& fundamentals = result.fundamentalPriceHistory();

    std::cout << std::fixed << std::setprecision(4);
    std::cout << "Simulation completed.\n";
    std::cout << "Config file: " << runtimeConfig.sourcePath << '\n';
    std::cout << "Asset: " << config.assetName() << '\n';
    std::cout << "Steps: " << stats.completedSteps << '\n';
    std::cout << "Agents: "
              << (config.numFundamentalists + config.numChartists + config.numNoiseTraders +
                  config.numBuyAndHoldAgents)
              << " (" << config.numFundamentalists << " fundamentalists, " << config.numChartists
              << " chartists, " << config.numNoiseTraders << " noise traders, "
              << config.numBuyAndHoldAgents << " buy-and-hold agents)\n";
    std::cout << "Short selling: " << (config.shortSellingEnabled ? "enabled" : "disabled") << '\n';
    std::cout << "Transaction cost rate: " << config.transactionCosts.rate << '\n';
    std::cout << "Transaction costs affect decisions: "
              << (config.transactionCosts.affectsDecisions ? "enabled" : "disabled") << '\n';
    if (config.shortSellingEnabled) {
        std::cout << "Short-sale initial margin: " << config.shortSale.initialMarginRequirement
                  << '\n';
        std::cout << "Short-sale maintenance margin: "
                  << config.shortSale.maintenanceMarginRequirement << '\n';
        std::cout << "Borrowable supply ratio: " << config.shortSale.borrowableSupplyRatio << '\n';
    }
    std::cout << "Final market price: " << stats.finalMarketPrice << '\n';
    std::cout << "Final fundamental price: " << stats.finalFundamentalPrice << '\n';
    std::cout << "Total traded volume: " << stats.totalTradedVolume << '\n';
    std::cout << "Total transaction costs: " << stats.totalTransactionCosts << '\n';
    std::cout << "Avg abs order imbalance: " << stats.averageAbsoluteOrderImbalance << '\n';
    std::cout << "Mean allocative efficiency: " << metrics.meanAllocativeEfficiency << " over "
              << metrics.allocativeEfficiencyObservations << " positive-surplus steps\n";
    std::cout << "Resident memory after simulation: "
              << formatMemoryMebibytes(memoryUsage.residentSetBytes) << '\n';
    std::cout << "Peak resident memory during process: "
              << formatMemoryMebibytes(memoryUsage.peakResidentSetBytes) << '\n';

    const std::size_t tailCount = std::min<std::size_t>(5, prices.size());
    std::cout << "Last " << tailCount << " market prices:";
    for (auto priceIt = std::prev(prices.cend(), static_cast<std::ptrdiff_t>(tailCount));
         priceIt != prices.cend(); ++priceIt) {
        std::cout << ' ' << *priceIt;
    }
    std::cout << '\n';

    const std::size_t tailFundCount = std::min<std::size_t>(5, fundamentals.size());
    std::cout << "Last " << tailFundCount << " fundamental prices:";
    for (auto fundamentalIt =
             std::prev(fundamentals.cend(), static_cast<std::ptrdiff_t>(tailFundCount));
         fundamentalIt != fundamentals.cend(); ++fundamentalIt) {
        std::cout << ' ' << *fundamentalIt;
    }
    std::cout << '\n';
    std::cout << "CSV exported to: " << runtimeConfig.output.simulationCsvPath << '\n';
    std::cout << "Agent CSV exported to: " << runtimeConfig.output.agentCsvPath << '\n';
    if (runtimeConfig.output.tradeLedgerEnabled) {
        std::cout << "Trade ledger CSV exported to: " << runtimeConfig.output.tradeLedgerCsvPath
                  << '\n';
    } else {
        std::cout << "Trade ledger CSV: disabled\n";
    }
    std::cout << "Summary metrics CSV exported to: " << runtimeConfig.output.summaryMetricsCsvPath
              << '\n';
    std::cout << "Stylised-facts CSV exported to: " << runtimeConfig.output.stylisedFactsCsvPath
              << '\n';
    std::cout << "Config JSON exported to: " << runtimeConfig.output.configJsonPath << '\n';
    std::cout << "Metadata JSON exported to: " << runtimeConfig.output.metadataJsonPath << '\n';
    std::cout << "Run log exported to: " << runtimeConfig.output.runLogPath << '\n';
    if (runtimeConfig.output.databaseOutputEnabled) {
        std::cout << "PostgreSQL import: enabled via "
                  << runtimeConfig.output.databaseUrlEnvironmentVariable << '\n';
        std::cout << "Prune staging after database import: "
                  << (runtimeConfig.output.databasePruneAfterImport ? "enabled" : "disabled")
                  << '\n';
    }
    if (runtimeConfig.output.experimentOutputEnabled) {
        std::cout << "Experiment run directory: " << runtimeConfig.output.runDirectoryPath << '\n';
        std::cout << "Experiment manifest: " << runtimeConfig.output.experimentManifestCsvPath
                  << '\n';
    }
}

} // namespace abm
