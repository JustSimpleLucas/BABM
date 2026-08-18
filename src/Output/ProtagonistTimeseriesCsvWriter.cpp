// ProtagonistTimeseriesCsvWriter.cpp

#include "Output/ProtagonistTimeseriesCsvWriter.h"

#include "Output/CsvSchema.h"
#include "Output/OutputSerialization.h"
#include "Results/SimulationRunResult.h"

#include <fstream>
#include <iomanip>

namespace abm::output_detail {
namespace {

using Row = ProtagonistStepDetails;

/*
 * The protagonist's own state and the cross-section he sits in are written side
 * by side on every row. Keeping them together is deliberate: his wealth read
 * alone says nothing about whether he did well, and reconstructing the
 * cross-section afterwards is impossible because no other artefact retains the
 * per-step wealth distribution.
 */
constexpr CsvColumn<Row> kColumns[] = {
    {"simulation_step", [](std::ostream& out, const Row& r) { out << r.step; }},
    {"agent_id", [](std::ostream& out, const Row& r) { out << r.agentId; }},
    {"cash", [](std::ostream& out, const Row& r) { out << r.cash; }},
    {"primary_asset_stock", [](std::ostream& out, const Row& r) { out << r.primaryAssetStock; }},
    {"wealth", [](std::ostream& out, const Row& r) { out << r.wealth; }},
    {"risky_weight", [](std::ostream& out, const Row& r) { out << r.riskyWeight; }},
    {"cumulative_trades", [](std::ostream& out, const Row& r) { out << r.cumulativeTradeCount; }},
    {"cumulative_traded_volume",
     [](std::ostream& out, const Row& r) { out << r.cumulativeTradedVolume; }},
    {"cumulative_transaction_costs_paid",
     [](std::ostream& out, const Row& r) { out << r.cumulativeTransactionCostsPaid; }},
    {"population_mean_wealth",
     [](std::ostream& out, const Row& r) { out << r.populationMeanWealth; }},
    {"population_median_wealth",
     [](std::ostream& out, const Row& r) { out << r.populationMedianWealth; }},
    {"wealth_percentile_rank",
     [](std::ostream& out, const Row& r) { out << r.wealthPercentileRank; }},
    {"population_size", [](std::ostream& out, const Row& r) { out << r.populationSize; }},
};

} // namespace

bool exportProtagonistTimeseriesCsv(const std::string& outputPath,
                                    const SimulationRunResult& result, std::string& error) {
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

    for (const Row& record : result.protagonistStepDetails()) {
        writeCsvRow(out, kColumns, record);
    }

    out.flush();
    if (!out.good()) {
        error = "Failed while writing CSV file: " + outputPath;
        return false;
    }

    return true;
}

} // namespace abm::output_detail
