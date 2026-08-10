// TradeLedgerCsvWriter.h

#ifndef ABM_OUTPUT_TRADE_LEDGER_CSV_WRITER_H
#define ABM_OUTPUT_TRADE_LEDGER_CSV_WRITER_H

#include <string>

namespace abm {
class SimulationRunResult;

namespace output_detail {

[[nodiscard]] bool exportTradeLedgerCsv(const std::string& outputPath,
                                        const SimulationRunResult& result, std::string& error);

} // namespace output_detail
} // namespace abm

#endif // ABM_OUTPUT_TRADE_LEDGER_CSV_WRITER_H
