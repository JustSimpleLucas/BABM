// TradeLedgerCsvWriter.cpp

#include "Output/TradeLedgerCsvWriter.h"

#include "Output/CsvSchema.h"
#include "Output/OutputSerialization.h"
#include "Results/SimulationRunResult.h"

#include <fstream>
#include <iomanip>

namespace abm::output_detail {
namespace {

using Row = ExternalTradeLedgerRecord;

constexpr CsvColumn<Row> kColumns[] = {
    {"trade_id", [](std::ostream& out, const Row& r) { out << r.tradeId; }},
    {"time", [](std::ostream& out, const Row& r) { out << r.timeStep; }},
    {"agent_id", [](std::ostream& out, const Row& r) { out << r.agentId; }},
    {"counterparty_agent_id",
     [](std::ostream& out, const Row& r) { out << r.counterpartyAgentId; }},
    {"side", [](std::ostream& out, const Row& r) { out << orderSideLabel(r.side); }},
    {"price", [](std::ostream& out, const Row& r) { out << r.price; }},
    {"qty", [](std::ostream& out, const Row& r) { out << r.quantity; }},
    {"asset", [](std::ostream& out, const Row& r) { out << r.asset; }},
    {"order_id", [](std::ostream& out, const Row& r) { out << r.orderId; }},
    {"counterparty_order_id",
     [](std::ostream& out, const Row& r) { out << r.counterpartyOrderId; }},
    {"gross_notional", [](std::ostream& out, const Row& r) { out << r.grossNotional; }},
    {"transaction_cost", [](std::ostream& out, const Row& r) { out << r.transactionCost; }},
    {"net_cash_flow", [](std::ostream& out, const Row& r) { out << r.netCashFlow; }},
};

} // namespace

bool exportTradeLedgerCsv(const std::string& outputPath, const SimulationRunResult& result,
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

    for (const Row& record : result.externalTradeLedger()) {
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
