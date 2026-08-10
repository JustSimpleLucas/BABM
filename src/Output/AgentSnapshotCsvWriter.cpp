// AgentSnapshotCsvWriter.cpp

#include "Output/AgentSnapshotCsvWriter.h"

#include "Output/CsvSchema.h"
#include "Output/OutputSerialization.h"
#include "Results/SimulationRunResult.h"

#include <fstream>
#include <iomanip>

namespace abm::output_detail {
namespace {

using Row = AgentSnapshot;

constexpr CsvColumn<Row> kColumns[] = {
    {"agent_id", [](std::ostream& out, const Row& r) { out << r.agentId; }},
    {"initial_strategy_type",
     [](std::ostream& out, const Row& r) { out << r.initialStrategyType; }},
    {"current_strategy_type",
     [](std::ostream& out, const Row& r) { out << r.currentStrategyType; }},
    {"initial_cash", [](std::ostream& out, const Row& r) { out << r.initialCash; }},
    {"initial_stock", [](std::ostream& out, const Row& r) { out << r.initialStock; }},
    {"initial_wealth", [](std::ostream& out, const Row& r) { out << r.initialWealth; }},
    {"x_coordinate", [](std::ostream& out, const Row& r) { out << r.xCoordinate; }},
    {"y_coordinate", [](std::ostream& out, const Row& r) { out << r.yCoordinate; }},
    {"social_gamma", [](std::ostream& out, const Row& r) { out << r.socialGamma; }},
    {"private_signal_std", [](std::ostream& out, const Row& r) { out << r.privateSignalStdDev; }},
    {"final_opinion", [](std::ostream& out, const Row& r) { out << r.finalOpinion; }},
    {"final_cash", [](std::ostream& out, const Row& r) { out << r.finalCash; }},
    {"final_stock", [](std::ostream& out, const Row& r) { out << r.finalStock; }},
    {"number_of_trades", [](std::ostream& out, const Row& r) { out << r.tradeCount; }},
    {"traded_volume", [](std::ostream& out, const Row& r) { out << r.tradedVolume; }},
    {"final_wealth", [](std::ostream& out, const Row& r) { out << r.finalWealth; }},
    {"cumulative_transaction_costs_paid",
     [](std::ostream& out, const Row& r) { out << r.cumulativeTransactionCostsPaid; }},
    {"average_entry_price", [](std::ostream& out, const Row& r) { out << r.averageEntryPrice; }},
    {"recent_peak_wealth", [](std::ostream& out, const Row& r) { out << r.recentPeakWealth; }},
    {"last_prospect_reference_point",
     [](std::ostream& out, const Row& r) { out << r.lastProspectReferencePoint; }},
    {"prospect_theory_enabled",
     [](std::ostream& out, const Row& r) { out << boolToFlag(r.prospectTheoryEnabled); }},
    {"prospect_loss_aversion",
     [](std::ostream& out, const Row& r) { out << r.prospectLossAversion; }},
    {"prospect_curvature_gain",
     [](std::ostream& out, const Row& r) { out << r.prospectCurvatureForGain; }},
    {"prospect_curvature_loss",
     [](std::ostream& out, const Row& r) { out << r.prospectCurvatureForLoss; }},
    {"prospect_gamma_gain",
     [](std::ostream& out, const Row& r) { out << r.prospectProbabilityDistortionForGain; }},
    {"prospect_gamma_loss",
     [](std::ostream& out, const Row& r) { out << r.prospectProbabilityDistortionForLoss; }},
    {"prospect_scenario_count",
     [](std::ostream& out, const Row& r) { out << r.prospectScenarioCount; }},
};

} // namespace

bool exportAgentDetailsCsv(const std::string& outputPath, const SimulationRunResult& result,
                           std::string& error) {
    if (!ensureParentDirectoryExists(outputPath, error)) {
        return false;
    }

    std::ofstream out(outputPath);
    if (!out.is_open()) {
        error = "Unable to open output file: " + outputPath;
        return false;
    }

    writeCsvHeader(out, kColumns);
    out << std::fixed << std::setprecision(8);

    for (const Row& snapshot : result.agentSnapshots()) {
        writeCsvRow(out, kColumns, snapshot);
    }

    out.flush();
    if (!out.good()) {
        error = "Failed while writing CSV file: " + outputPath;
        return false;
    }

    return true;
}

} // namespace abm::output_detail
