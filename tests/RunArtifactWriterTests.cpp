#include "tests/TestSupport.h"

#include "Application/ConsoleReporter.h"
#include "Metrics/StylisedFactMetrics.h"
#include "Output/RunArtifactWriter.h"
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

/** Collapses runs of spaces so column-aligned report rows can be matched. */
[[nodiscard]] std::string collapseWhitespace(const std::string& text) {
    std::string collapsed;
    collapsed.reserve(text.size());
    bool previousWasSpace = false;
    for (const char character : text) {
        const bool isSpace = character == ' ' || character == '\t';
        if (isSpace && previousWasSpace) {
            continue;
        }
        collapsed += isSpace ? ' ' : character;
        previousWasSpace = isSpace;
    }
    return collapsed;
}

void testRunArtifactWriterProducesRequiredFiles(int& failures) {
    namespace fs = std::filesystem;

    const fs::path outputRoot = fs::temp_directory_path() / "abm_run_artifact_writer_smoke";
    std::error_code cleanupError;
    fs::remove_all(outputRoot, cleanupError);
    fs::create_directories(outputRoot, cleanupError);
    if (cleanupError) {
        abm::test::expect(false, "test setup should create a temporary output directory", failures);
        return;
    }

    abm::RuntimeConfig runtimeConfig;
    runtimeConfig.simulation = abm::test::deterministicSmokeConfig();
    runtimeConfig.simulation.control.prospectTheoryAgentFraction = 0.375;
    runtimeConfig.simulation.chartist.momentumSignalThreshold = 0.015;
    runtimeConfig.simulation.chartist.breakoutWindow = 13;
    runtimeConfig.simulation.numNoiseTraders = 2;
    runtimeConfig.simulation.numBuyAndHoldAgents = 3;
    runtimeConfig.simulation.buyAndHold.targetRiskyWeight = 0.65;
    runtimeConfig.simulation.transactionCosts.rate = 0.0025;
    runtimeConfig.simulation.transactionCosts.affectsDecisions = true;
    runtimeConfig.simulation.transactionCosts.applyToForcedBuyIns = true;
    abm::test::soleAsset(runtimeConfig.simulation).fundamentalDriftPerStep = 0.012;
    abm::test::soleAsset(runtimeConfig.simulation).minimumFundamentalValue = 2.50;
    runtimeConfig.sourcePath = (outputRoot / "source.cfg").string();
    runtimeConfig.output.experimentOutputEnabled = false;
    runtimeConfig.output.experimentName = "smoke_experiment";
    runtimeConfig.output.runLabel = "baseline";
    runtimeConfig.output.createdAtLocal = "20260427143012";
    runtimeConfig.output.runId = "smoke_run";
    runtimeConfig.output.simulationCsvPath = (outputRoot / "step_timeseries.csv").string();
    runtimeConfig.output.agentCsvPath = (outputRoot / "agents_final.csv").string();
    runtimeConfig.output.tradeLedgerEnabled = true;
    runtimeConfig.output.tradeLedgerCsvPath = (outputRoot / "trade_ledger.csv").string();
    runtimeConfig.output.summaryMetricsCsvPath = (outputRoot / "summary_metrics.csv").string();
    runtimeConfig.output.stylisedFactsCsvPath = (outputRoot / "stylised_facts.csv").string();
    runtimeConfig.output.configJsonPath = (outputRoot / "config.json").string();
    runtimeConfig.output.metadataJsonPath = (outputRoot / "metadata.json").string();
    runtimeConfig.output.runLogPath = (outputRoot / "logs" / "run.log").string();

    abm::SimulationEngine simulation(runtimeConfig.simulation);
    const abm::SimulationRunResult simulationResult = simulation.run({}, true);

    const abm::RunMetrics metrics = abm::calculateRunMetrics(simulationResult);
    abm::RunArtifactWriteResult result;
    std::string error;
    const bool wroteArtifacts = abm::RunArtifactWriter::writeCompletedRun(
        runtimeConfig, simulationResult, metrics, result, error);

    abm::test::expect(wroteArtifacts,
                      "run artifact writer should produce all configured files: " + error,
                      failures);
    abm::test::expect(!result.configHash.empty(),
                      "run artifact writer should return a stable config hash", failures);

    const std::vector<fs::path> requiredFiles{
        runtimeConfig.output.simulationCsvPath,    runtimeConfig.output.agentCsvPath,
        runtimeConfig.output.tradeLedgerCsvPath,   runtimeConfig.output.summaryMetricsCsvPath,
        runtimeConfig.output.stylisedFactsCsvPath, runtimeConfig.output.configJsonPath,
        runtimeConfig.output.metadataJsonPath,     runtimeConfig.output.runLogPath,
    };

    for (const fs::path& filePath : requiredFiles) {
        abm::test::expect(fs::exists(filePath) && fs::is_regular_file(filePath),
                          "run artifact writer should create " + filePath.filename().string(),
                          failures);
    }

    std::ifstream agentCsvInput(runtimeConfig.output.agentCsvPath);
    std::string agentCsvHeader;
    std::getline(agentCsvInput, agentCsvHeader);
    abm::test::expect(
        agentCsvHeader.find("agent_id,initial_strategy_type,current_strategy_type") == 0,
        "agent CSV should export initial and current strategy fields after identity refactor",
        failures);
    abm::test::expect(agentCsvHeader.find("average_entry_price,recent_peak_wealth,"
                                          "last_prospect_reference_point") != std::string::npos,
                      "agent CSV should export final CPT reference-point diagnostics", failures);
    abm::test::expect(agentCsvHeader.find("cumulative_transaction_costs_paid") != std::string::npos,
                      "agent CSV should export cumulative transaction costs paid", failures);
    abm::test::expect(agentCsvHeader.find("agent_type") == std::string::npos,
                      "agent CSV should not export the removed agent_type field", failures);

    std::ifstream simulationCsvInput(runtimeConfig.output.simulationCsvPath);
    std::string simulationCsvHeader;
    std::getline(simulationCsvInput, simulationCsvHeader);
    abm::test::expect(simulationCsvHeader.find("best_bid,best_ask,bid_ask_spread,mid_quote") !=
                          std::string::npos,
                      "simulation CSV should export limit-order-book quote diagnostics", failures);
    abm::test::expect(simulationCsvHeader.find("submitted_limit_orders,submitted_market_orders") !=
                          std::string::npos,
                      "simulation CSV should export submitted order-style diagnostics", failures);
    abm::test::expect(simulationCsvHeader.find("total_transaction_costs") != std::string::npos,
                      "simulation CSV should export per-step transaction costs", failures);
    abm::test::expect(simulationCsvHeader.find("realized_allocative_surplus,"
                                               "maximum_allocative_surplus,"
                                               "allocative_efficiency") != std::string::npos,
                      "simulation CSV should export double-auction allocative-efficiency "
                      "diagnostics",
                      failures);
    abm::test::expect(simulationCsvHeader.find("wealth_gini_coefficient") != std::string::npos,
                      "simulation CSV should export per-step wealth inequality diagnostics",
                      failures);

    std::ifstream tradeLedgerInput(runtimeConfig.output.tradeLedgerCsvPath);
    std::string tradeLedgerHeader;
    std::getline(tradeLedgerInput, tradeLedgerHeader);
    abm::test::expect(tradeLedgerHeader.find("trade_id,time,agent_id,counterparty_agent_id") == 0,
                      "enabled trade ledger should export the counterparty-level CSV header",
                      failures);
    abm::test::expect(tradeLedgerHeader.find("gross_notional,transaction_cost,net_cash_flow") !=
                          std::string::npos,
                      "trade ledger should export fee and net-cash-flow diagnostics", failures);

    std::ifstream configJsonInput(runtimeConfig.output.configJsonPath);
    std::string configJsonContent;
    std::string configJsonLine;
    while (std::getline(configJsonInput, configJsonLine)) {
        configJsonContent += configJsonLine;
        configJsonContent += '\n';
    }
    abm::test::expect(configJsonContent.find("\"agent_fraction\": 0.3750000000") !=
                          std::string::npos,
                      "config JSON should export the CPT agent fraction", failures);
    abm::test::expect(
        configJsonContent.find("\"reference_point_mode\": \"average_purchase_price\"") !=
            std::string::npos,
        "config JSON should export the selected CPT reference-point mode", failures);
    abm::test::expect(
        configJsonContent.find("\"reference_moving_average_window\": 20") != std::string::npos,
        "config JSON should export the CPT moving-average reference window", failures);
    abm::test::expect(configJsonContent.find("\"mode\": \"continuous_lob\"") != std::string::npos,
                      "config JSON should export the selected market microstructure", failures);
    abm::test::expect(configJsonContent.find("\"book_depth_levels\": 5") != std::string::npos,
                      "config JSON should export the visible book-depth setting", failures);
    abm::test::expect(configJsonContent.find("\"transaction_costs\"") != std::string::npos &&
                          configJsonContent.find("\"rate\": 0.0025000000") != std::string::npos,
                      "config JSON should export transaction-cost controls", failures);
    abm::test::expect(configJsonContent.find("\"fundamental_drift_per_step\": 0.0120000000") !=
                          std::string::npos,
                      "config JSON should export the fundamental drift per step", failures);
    abm::test::expect(configJsonContent.find("\"minimum_fundamental_value\": 2.5000000000") !=
                          std::string::npos,
                      "config JSON should export the minimum fundamental value", failures);
    abm::test::expect(configJsonContent.find("\"warmup_price_process\"") != std::string::npos &&
                          configJsonContent.find("\"scope\": \"pre_trading_warmup_only\"") !=
                              std::string::npos,
                      "config JSON should label warm-up-only price-process parameters", failures);
    abm::test::expect(configJsonContent.find("\"order_imbalance_impact\"") == std::string::npos,
                      "config JSON should not export removed direct price-impact controls",
                      failures);
    abm::test::expect(configJsonContent.find("\"momentum_signal_threshold\": 0.0150000000") !=
                          std::string::npos,
                      "config JSON should export the chartist momentum signal threshold", failures);
    abm::test::expect(configJsonContent.find("\"breakout_window\": 13") != std::string::npos,
                      "config JSON should export the chartist breakout window", failures);
    abm::test::expect(configJsonContent.find("\"num_noise_traders\": 2") != std::string::npos,
                      "config JSON should export the noise-trader population count", failures);
    abm::test::expect(configJsonContent.find("\"num_buy_and_hold_agents\": 3") != std::string::npos,
                      "config JSON should export the buy-and-hold population count", failures);
    abm::test::expect(configJsonContent.find("\"belief_shock_std_dev\": 0.0200000000") !=
                          std::string::npos,
                      "config JSON should export the noise-trader belief-shock scale", failures);
    abm::test::expect(configJsonContent.find("\"target_risky_weight\": 0.6500000000") !=
                          std::string::npos,
                      "config JSON should export the buy-and-hold target risky weight", failures);

    std::ifstream metadataInput(runtimeConfig.output.metadataJsonPath);
    std::string metadataContent;
    std::string metadataLine;
    while (std::getline(metadataInput, metadataLine)) {
        metadataContent += metadataLine;
        metadataContent += '\n';
    }

    abm::test::expect(metadataContent.find(outputRoot.string()) == std::string::npos,
                      "metadata JSON should store portable paths instead of absolute output paths",
                      failures);
    abm::test::expect(
        metadataContent.find("\"step_timeseries_csv\": \"step_timeseries.csv\"") !=
            std::string::npos,
        "metadata JSON should store output CSV paths relative to the metadata directory", failures);
    abm::test::expect(metadataContent.find("\"trade_ledger_enabled\": true") != std::string::npos &&
                          metadataContent.find("\"trade_ledger_csv\": \"trade_ledger.csv\"") !=
                              std::string::npos,
                      "metadata JSON should record enabled trade-ledger output", failures);
    abm::test::expect(
        metadataContent.find("\"run_log\": \"logs/run.log\"") != std::string::npos,
        "metadata JSON should store nested output paths relative to the metadata directory",
        failures);
    abm::test::expect(
        metadataContent.find("\"chartist_momentum_signal_threshold\": 0.0150000000") !=
            std::string::npos,
        "metadata JSON should export the chartist momentum signal threshold", failures);
    abm::test::expect(metadataContent.find("\"chartist_breakout_window\": 13") != std::string::npos,
                      "metadata JSON should export the chartist breakout window", failures);
    abm::test::expect(metadataContent.find("\"prospect_theory_agent_fraction\": 0.3750000000") !=
                          std::string::npos,
                      "metadata JSON should export the CPT agent fraction", failures);
    abm::test::expect(metadataContent.find("\"num_noise_traders\": 2") != std::string::npos,
                      "metadata JSON should export the noise-trader population count", failures);
    abm::test::expect(metadataContent.find("\"num_buy_and_hold_agents\": 3") != std::string::npos,
                      "metadata JSON should export the buy-and-hold population count", failures);
    abm::test::expect(metadataContent.find("\"buy_hold_target_risky_weight\": 0.6500000000") !=
                          std::string::npos,
                      "metadata JSON should export the buy-and-hold target risky weight", failures);
    abm::test::expect(metadataContent.find("\"fundamental_drift_per_step\": 0.0120000000") !=
                          std::string::npos,
                      "metadata JSON should export the fundamental drift per step", failures);
    abm::test::expect(metadataContent.find("\"minimum_fundamental_value\": 2.5000000000") !=
                          std::string::npos,
                      "metadata JSON should export the minimum fundamental value", failures);
    abm::test::expect(metadataContent.find("\"transaction_cost_rate\": 0.0025000000") !=
                          std::string::npos,
                      "metadata JSON should export the transaction-cost rate", failures);
    abm::test::expect(metadataContent.find("\"total_transaction_costs\"") != std::string::npos,
                      "metadata JSON should export total transaction costs", failures);
    abm::test::expect(metadataContent.find("\"final_wealth_gini_coefficient\"") !=
                          std::string::npos,
                      "metadata JSON should export the final wealth Gini coefficient", failures);
    abm::test::expect(
        metadataContent.find("\"mean_allocative_efficiency\"") != std::string::npos &&
            metadataContent.find("\"allocative_efficiency_observations\"") != std::string::npos,
        "metadata JSON should export run-level allocative-efficiency diagnostics", failures);
    abm::test::expect(metadataContent.find("plots_directory") == std::string::npos,
                      "metadata JSON should not advertise an unused plots directory", failures);

    std::ifstream summaryInput(runtimeConfig.output.summaryMetricsCsvPath);
    std::string summaryContent;
    std::string summaryLine;
    while (std::getline(summaryInput, summaryLine)) {
        summaryContent += summaryLine;
        summaryContent += '\n';
    }
    abm::test::expect(summaryContent.find("prospect_theory_agent_fraction") != std::string::npos &&
                          summaryContent.find(",0.3750000000,") != std::string::npos,
                      "summary metrics CSV should export the CPT agent fraction", failures);
    abm::test::expect(summaryContent.find("fundamental_drift_per_step") != std::string::npos &&
                          summaryContent.find(",0.0120000000,2.5000000000,") != std::string::npos,
                      "summary metrics CSV should export the fundamental drift and floor",
                      failures);
    abm::test::expect(summaryContent.find("num_buy_and_hold_agents") != std::string::npos &&
                          summaryContent.find(",2,3,") != std::string::npos,
                      "summary metrics CSV should export buy-and-hold population count", failures);
    abm::test::expect(summaryContent.find("transaction_cost_rate") != std::string::npos &&
                          summaryContent.find("total_transaction_costs") != std::string::npos,
                      "summary metrics CSV should export transaction-cost configuration and totals",
                      failures);
    abm::test::expect(summaryContent.find("final_wealth_gini_coefficient") != std::string::npos,
                      "summary metrics CSV should export the final wealth Gini coefficient",
                      failures);
    abm::test::expect(summaryContent.find("mean_allocative_efficiency") != std::string::npos &&
                          summaryContent.find("allocative_efficiency_observations") !=
                              std::string::npos,
                      "summary metrics CSV should export run-level allocative-efficiency "
                      "diagnostics",
                      failures);

    std::ifstream runLogInput(runtimeConfig.output.runLogPath);
    std::string runLogContent;
    std::string runLogLine;
    while (std::getline(runLogInput, runLogLine)) {
        runLogContent += runLogLine;
        runLogContent += '\n';
    }
    abm::test::expect(runLogContent.find("Prospect Theory agent fraction: 0.3750000000") !=
                          std::string::npos,
                      "run log should export the CPT agent fraction", failures);
    abm::test::expect(runLogContent.find("Trade ledger enabled: 1") != std::string::npos,
                      "run log should record enabled trade-ledger diagnostics", failures);
    abm::test::expect(runLogContent.find("Fundamental drift per step: 0.0120000000") !=
                          std::string::npos,
                      "run log should record the fundamental drift per step", failures);
    abm::test::expect(runLogContent.find("Buy-and-hold agents: 3") != std::string::npos,
                      "run log should record the buy-and-hold population count", failures);
    abm::test::expect(runLogContent.find("Buy-and-hold target risky weight: 0.6500000000") !=
                          std::string::npos,
                      "run log should record the buy-and-hold target risky weight", failures);
    abm::test::expect(runLogContent.find("Final wealth Gini coefficient: ") != std::string::npos,
                      "run log should record the final wealth Gini coefficient", failures);
    abm::test::expect(
        runLogContent.find("Mean allocative efficiency: ") != std::string::npos &&
            runLogContent.find("Allocative-efficiency observations: ") != std::string::npos,
        "run log should record run-level allocative-efficiency diagnostics", failures);

    fs::remove_all(outputRoot, cleanupError);
}

void testRunArtifactWriterSkipsDisabledTradeLedger(int& failures) {
    namespace fs = std::filesystem;

    const fs::path outputRoot = fs::temp_directory_path() / "abm_run_artifact_writer_no_ledger";
    std::error_code cleanupError;
    fs::remove_all(outputRoot, cleanupError);
    fs::create_directories(outputRoot, cleanupError);
    if (cleanupError) {
        abm::test::expect(false, "test setup should create disabled-ledger output directory",
                          failures);
        return;
    }

    abm::RuntimeConfig runtimeConfig;
    runtimeConfig.simulation = abm::test::deterministicSmokeConfig();
    runtimeConfig.sourcePath = (outputRoot / "source.cfg").string();
    runtimeConfig.output.experimentName = "smoke_experiment";
    runtimeConfig.output.runLabel = "no_ledger";
    runtimeConfig.output.createdAtLocal = "20260427143012";
    runtimeConfig.output.runId = "no_ledger_run";
    runtimeConfig.output.simulationCsvPath = (outputRoot / "step_timeseries.csv").string();
    runtimeConfig.output.agentCsvPath = (outputRoot / "agents_final.csv").string();
    runtimeConfig.output.tradeLedgerEnabled = false;
    runtimeConfig.output.tradeLedgerCsvPath = (outputRoot / "trade_ledger.csv").string();
    runtimeConfig.output.summaryMetricsCsvPath = (outputRoot / "summary_metrics.csv").string();
    runtimeConfig.output.stylisedFactsCsvPath = (outputRoot / "stylised_facts.csv").string();
    runtimeConfig.output.configJsonPath = (outputRoot / "config.json").string();
    runtimeConfig.output.metadataJsonPath = (outputRoot / "metadata.json").string();
    runtimeConfig.output.runLogPath = (outputRoot / "logs" / "run.log").string();

    abm::SimulationEngine simulation(runtimeConfig.simulation);
    const abm::SimulationRunResult simulationResult = simulation.run();
    abm::test::expect(simulationResult.externalTradeLedger().empty(),
                      "disabled trade ledger should leave the result ledger empty", failures);

    const abm::RunMetrics metrics = abm::calculateRunMetrics(simulationResult);
    abm::RunArtifactWriteResult result;
    std::string error;
    const bool wroteArtifacts = abm::RunArtifactWriter::writeCompletedRun(
        runtimeConfig, simulationResult, metrics, result, error);

    abm::test::expect(
        wroteArtifacts,
        "artifact writer should succeed when trade ledger output is disabled: " + error, failures);
    abm::test::expect(!fs::exists(runtimeConfig.output.tradeLedgerCsvPath),
                      "disabled trade ledger should not create trade_ledger.csv", failures);

    std::ifstream metadataInput(runtimeConfig.output.metadataJsonPath);
    std::string metadataContent;
    std::string metadataLine;
    while (std::getline(metadataInput, metadataLine)) {
        metadataContent += metadataLine;
        metadataContent += '\n';
    }
    abm::test::expect(metadataContent.find("\"trade_ledger_enabled\": false") !=
                              std::string::npos &&
                          metadataContent.find("\"trade_ledger_csv\": null") != std::string::npos,
                      "metadata JSON should record disabled trade-ledger output", failures);

    std::ifstream runLogInput(runtimeConfig.output.runLogPath);
    std::string runLogContent;
    std::string runLogLine;
    while (std::getline(runLogInput, runLogLine)) {
        runLogContent += runLogLine;
        runLogContent += '\n';
    }
    abm::test::expect(runLogContent.find("Trade ledger enabled: 0") != std::string::npos,
                      "run log should record disabled trade-ledger diagnostics", failures);

    std::ostringstream consoleOutput;
    std::streambuf* originalBuffer = std::cout.rdbuf(consoleOutput.rdbuf());
    abm::ProcessMemoryUsage memoryUsage;
    memoryUsage.residentSetBytes = 64U * 1024U * 1024U;
    memoryUsage.peakResidentSetBytes = 96U * 1024U * 1024U;
    abm::printCompletedSimulationSummary(runtimeConfig, simulationResult, metrics, memoryUsage);
    std::cout.rdbuf(originalBuffer);
    /*
     * The summary aligns its values into a column, so assertions compare the
     * whitespace-collapsed text. That keeps them checking what the reader sees
     * without pinning the report to a particular column width.
     */
    const std::string console = collapseWhitespace(consoleOutput.str());
    abm::test::expect(
        console.find("Trade ledger CSV: disabled (trade_ledger_enabled = 0)") != std::string::npos,
        "console reporter should state when trade-ledger CSV output is disabled", failures);
    abm::test::expect(console.find("Resident memory: 64.00 MiB") != std::string::npos,
                      "console reporter should include resident memory after simulation", failures);
    abm::test::expect(console.find("Mean allocative efficiency: ") != std::string::npos,
                      "console reporter should include allocative-efficiency diagnostics",
                      failures);
    abm::test::expect(console.find("Peak resident memory: 96.00 MiB") != std::string::npos,
                      "console reporter should include peak resident memory during process",
                      failures);
    abm::test::expect(console.find("Configuration") != std::string::npos &&
                          console.find("Market outcome") != std::string::npos &&
                          console.find("Diagnostics") != std::string::npos &&
                          console.find("Artefacts") != std::string::npos,
                      "console reporter should group the summary into labelled sections", failures);

    fs::remove_all(outputRoot, cleanupError);
}

} // namespace

namespace abm::test {

void runRunArtifactWriterTests(int& failures) {
    testRunArtifactWriterProducesRequiredFiles(failures);
    testRunArtifactWriterSkipsDisabledTradeLedger(failures);
}

} // namespace abm::test
