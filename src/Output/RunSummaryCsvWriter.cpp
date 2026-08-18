// RunSummaryCsvWriter.cpp

#include "Output/RunSummaryCsvWriter.h"

#include "Config/SimulationConfigParsing.h"
#include "Output/CsvSchema.h"
#include "Output/OutputSerialization.h"
#include "Results/SimulationRunResult.h"

#include <fstream>
#include <iomanip>
#include <vector>

namespace abm::output_detail {
namespace {

/** The sources a summary row draws from, bundled so one table can read them. */
struct Row {
    const RuntimeConfig& runtimeConfig;
    const SimulationConfig& config;
    const SimulationStats& stats;
    const RunMetrics& metrics;
    const std::string& configHash;

    /** Whole run output, for the few columns that summarise a per-step series. */
    const SimulationRunResult& result;
};

/**
 * Returns the protagonist's last recorded step, or nullptr when he is absent.
 *
 * The final row already carries his closing wealth and his standing in the
 * cross-section, so the summary does not need to recompute either. Returning a
 * pointer lets the columns below emit an empty field rather than a zero when
 * there is no protagonist: an absent measurement and a measured zero are
 * different facts, and a sweep that averaged them together would be wrong.
 */
[[nodiscard]] const ProtagonistStepDetails*
finalProtagonistStep(const SimulationRunResult& result) {
    const std::vector<ProtagonistStepDetails>& series = result.protagonistStepDetails();
    return series.empty() ? nullptr : &series.back();
}

constexpr CsvColumn<Row> kColumns[] = {
    {"run_id",
     [](std::ostream& out, const Row& r) { out << csvEscape(r.runtimeConfig.output.runId); }},
    {"experiment_name",
     [](std::ostream& out, const Row& r) {
         out << csvEscape(r.runtimeConfig.output.experimentName);
     }},
    {"run_label",
     [](std::ostream& out, const Row& r) { out << csvEscape(r.runtimeConfig.output.runLabel); }},
    {"created_at_local",
     [](std::ostream& out, const Row& r) {
         out << csvEscape(r.runtimeConfig.output.createdAtLocal);
     }},
    {"status", [](std::ostream& out, const Row&) { out << "completed"; }},
    {"config_hash", [](std::ostream& out, const Row& r) { out << csvEscape(r.configHash); }},
    {"seed", [](std::ostream& out, const Row& r) { out << r.config.seed; }},
    {"time_steps", [](std::ostream& out, const Row& r) { out << r.config.timeSteps; }},
    {"warmup_steps", [](std::ostream& out, const Row& r) { out << r.config.warmupSteps; }},
    {"fundamental_shock_std_dev",
     [](std::ostream& out, const Row& r) { out << r.config.fundamentalShockStdDev(); }},
    {"fundamental_drift_per_step",
     [](std::ostream& out, const Row& r) { out << r.config.fundamentalDriftPerStep(); }},
    {"minimum_fundamental_value",
     [](std::ostream& out, const Row& r) { out << r.config.minimumFundamentalValue(); }},
    {"num_fundamentalists",
     [](std::ostream& out, const Row& r) { out << r.config.numFundamentalists; }},
    {"num_chartists", [](std::ostream& out, const Row& r) { out << r.config.numChartists; }},
    {"num_noise_traders", [](std::ostream& out, const Row& r) { out << r.config.numNoiseTraders; }},
    {"num_buy_and_hold_agents",
     [](std::ostream& out, const Row& r) { out << r.config.numBuyAndHoldAgents; }},
    {"transaction_cost_rate",
     [](std::ostream& out, const Row& r) { out << r.config.transactionCosts.rate; }},
    {"transaction_cost_affects_decisions",
     [](std::ostream& out, const Row& r) {
         out << boolToFlag(r.config.transactionCosts.affectsDecisions);
     }},
    {"transaction_cost_apply_to_forced_buy_ins",
     [](std::ostream& out, const Row& r) {
         out << boolToFlag(r.config.transactionCosts.applyToForcedBuyIns);
     }},
    {"prospect_theory_enabled",
     [](std::ostream& out, const Row& r) {
         out << boolToFlag(r.config.control.prospectTheoryEnabled);
     }},
    {"prospect_theory_agent_fraction",
     [](std::ostream& out, const Row& r) { out << r.config.control.prospectTheoryAgentFraction; }},
    {"prospect_heterogeneity_enabled",
     [](std::ostream& out, const Row& r) {
         out << boolToFlag(r.config.control.prospectParameterHeterogeneityEnabled);
     }},
    {"social_enabled",
     [](std::ostream& out, const Row& r) { out << boolToFlag(r.config.social.enabled); }},
    {"short_selling_enabled",
     [](std::ostream& out, const Row& r) { out << boolToFlag(r.config.shortSellingEnabled); }},
    {"final_market_price",
     [](std::ostream& out, const Row& r) { out << r.stats.finalMarketPrice; }},
    {"final_fundamental_price",
     [](std::ostream& out, const Row& r) { out << r.stats.finalFundamentalPrice; }},
    {"final_wealth_gini_coefficient",
     [](std::ostream& out, const Row& r) { out << r.metrics.finalWealthGiniCoefficient; }},
    {"total_traded_volume",
     [](std::ostream& out, const Row& r) { out << r.stats.totalTradedVolume; }},
    {"total_transaction_costs",
     [](std::ostream& out, const Row& r) { out << r.stats.totalTransactionCosts; }},
    {"average_absolute_order_imbalance",
     [](std::ostream& out, const Row& r) { out << r.stats.averageAbsoluteOrderImbalance; }},
    {"mean_allocative_efficiency",
     [](std::ostream& out, const Row& r) { out << r.metrics.meanAllocativeEfficiency; }},
    {"allocative_efficiency_observations",
     [](std::ostream& out, const Row& r) { out << r.metrics.allocativeEfficiencyObservations; }},
    {"mean_log_return", [](std::ostream& out, const Row& r) { out << r.metrics.meanLogReturn; }},
    {"log_return_variance",
     [](std::ostream& out, const Row& r) { out << r.metrics.logReturnVariance; }},
    {"log_return_std_dev",
     [](std::ostream& out, const Row& r) { out << r.metrics.logReturnStdDev; }},
    {"skewness", [](std::ostream& out, const Row& r) { out << r.metrics.skewness; }},
    {"excess_kurtosis", [](std::ostream& out, const Row& r) { out << r.metrics.excessKurtosis; }},
    {"max_drawdown", [](std::ostream& out, const Row& r) { out << r.metrics.maxDrawdown; }},
    {"lag1_return_autocorrelation",
     [](std::ostream& out, const Row& r) { out << r.metrics.lag1ReturnAutocorrelation; }},
    {"lag1_abs_return_autocorrelation",
     [](std::ostream& out, const Row& r) { out << r.metrics.lag1AbsoluteReturnAutocorrelation; }},
    {"lag1_squared_return_autocorrelation",
     [](std::ostream& out, const Row& r) { out << r.metrics.lag1SquaredReturnAutocorrelation; }},
    {"mean_traded_volume",
     [](std::ostream& out, const Row& r) { out << r.metrics.meanTradedVolume; }},
    {"zero_return_share",
     [](std::ostream& out, const Row& r) { out << r.metrics.zeroReturnShare; }},
    {"observation_count",
     [](std::ostream& out, const Row& r) { out << r.metrics.observationCount; }},
    /*
     * The protagonist's settings and outcome are recorded here rather than in
     * the run-id, whose schema is frozen. These five columns are what let a
     * parameter sweep compare one identified investor's fate across runs
     * straight from the experiment manifest.
     */
    {"protagonist_enabled",
     [](std::ostream& out, const Row& r) { out << boolToFlag(r.config.protagonist.enabled); }},
    {"protagonist_strategy",
     [](std::ostream& out, const Row& r) {
         if (r.config.protagonist.enabled) {
             out << csvEscape(
                 config_parsing::protagonistStrategyKindName(r.config.protagonist.strategy));
         }
     }},
    {"protagonist_agent_id",
     [](std::ostream& out, const Row& r) {
         if (const ProtagonistStepDetails* step = finalProtagonistStep(r.result)) {
             out << step->agentId;
         }
     }},
    {"protagonist_final_wealth",
     [](std::ostream& out, const Row& r) {
         if (const ProtagonistStepDetails* step = finalProtagonistStep(r.result)) {
             out << step->wealth;
         }
     }},
    {"protagonist_final_wealth_percentile",
     [](std::ostream& out, const Row& r) {
         if (const ProtagonistStepDetails* step = finalProtagonistStep(r.result)) {
             out << step->wealthPercentileRank;
         }
     }},
};

} // namespace

bool exportSummaryMetricsCsv(const std::string& outputPath, const RuntimeConfig& runtimeConfig,
                             const SimulationRunResult& result, const RunMetrics& metrics,
                             const std::string& configHash, std::string& error) {
    if (!ensureParentDirectoryExists(outputPath, error)) {
        return false;
    }

    std::ofstream out(outputPath);
    if (!out.is_open()) {
        error = "Unable to open summary metrics file: " + outputPath;
        return false;
    }

    writeCsvHeader(out, kColumns);
    out << std::fixed << std::setprecision(10);
    writeCsvRow(out, kColumns,
                Row{runtimeConfig, result.config(), result.stats(), metrics, configHash, result});

    out.flush();
    if (!out.good()) {
        error = "Failed while writing summary metrics file: " + outputPath;
        return false;
    }
    return true;
}

} // namespace abm::output_detail
