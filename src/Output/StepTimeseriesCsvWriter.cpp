// StepTimeseriesCsvWriter.cpp

#include "Output/StepTimeseriesCsvWriter.h"

#include "Output/CsvSchema.h"
#include "Output/OutputSerialization.h"
#include "Results/SimulationRunResult.h"

#include <algorithm>
#include <fstream>
#include <iomanip>
#include <string>

namespace abm::output_detail {
namespace {

/**
 * One line of the primary-asset step series.
 *
 * `step` is null on the initial and warm-up rows, which carry price levels but
 * no clearing outcome; the columns that read it then emit nothing. This is what
 * removed the hand-maintained field count that used to pad those rows with the
 * right number of commas.
 */
struct Row {
    std::size_t rowIndex{0};
    const char* phase{""};
    double marketPrice{0.0};
    double fundamentalPrice{0.0};
    const StepDetails* step{nullptr};
};

constexpr CsvColumn<Row> kColumns[] = {
    {"row_index", [](std::ostream& out, const Row& r) { out << r.rowIndex; }},
    {"phase", [](std::ostream& out, const Row& r) { out << r.phase; }},
    {"simulation_step",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.step;
         }
     }},
    {"reference_price",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.referencePrice;
         }
     }},
    {"market_price", [](std::ostream& out, const Row& r) { out << r.marketPrice; }},
    {"fundamental_price", [](std::ostream& out, const Row& r) { out << r.fundamentalPrice; }},
    {"submitted_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->submittedOrders;
         }
     }},
    {"net_demand",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->netDemand;
         }
     }},
    {"traded_volume",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.tradedVolume;
         }
     }},
    {"notional_imbalance",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->notionalImbalance;
         }
     }},
    {"normalized_imbalance",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->normalizedImbalance;
         }
     }},
    {"fundamental_signal",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->fundamentalSignal;
         }
     }},
    {"random_shock",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->randomShock;
         }
     }},
    {"raw_return",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.rawReturn;
         }
     }},
    {"log_return",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.logReturn;
         }
     }},
    {"submitted_limit_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.submittedLimitOrders;
         }
     }},
    {"submitted_market_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.submittedMarketOrders;
         }
     }},
    {"cancelled_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->cancelledOrders;
         }
     }},
    {"expired_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.expiredOrders;
         }
     }},
    {"executed_trades",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.executedTrades;
         }
     }},
    {"total_transaction_costs",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.totalTransactionCosts;
         }
     }},
    {"realized_allocative_surplus",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.realizedAllocativeSurplus;
         }
     }},
    {"maximum_allocative_surplus",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.maximumAllocativeSurplus;
         }
     }},
    {"allocative_efficiency",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.allocativeEfficiency;
         }
     }},
    {"last_trade_price",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.lastTradePrice;
         }
     }},
    {"best_bid",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.bestBid;
         }
     }},
    {"best_ask",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.bestAsk;
         }
     }},
    {"bid_ask_spread",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.bidAskSpread;
         }
     }},
    {"mid_quote",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.midQuote;
         }
     }},
    {"bid_depth",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.bidDepth;
         }
     }},
    {"ask_depth",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.askDepth;
         }
     }},
    {"resting_bid_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.restingBidOrders;
         }
     }},
    {"resting_ask_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->asset.restingAskOrders;
         }
     }},
    {"wealth_gini_coefficient",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->wealthGiniCoefficient;
         }
     }},
};

} // namespace

bool exportSimulationDetailsCsv(const std::string& outputPath, const SimulationRunResult& result,
                                std::string& error) {
    if (!ensureParentDirectoryExists(outputPath, error)) {
        return false;
    }

    std::ofstream out(outputPath);
    if (!out.is_open()) {
        error = "Unable to open output file: " + outputPath;
        return false;
    }

    const SimulationConfig& config = result.config();
    const auto& marketValues = result.marketPriceHistory();
    const auto& fundamentalValues = result.fundamentalPriceHistory();
    const auto& details = result.stepDetails();
    const std::size_t totalRows = std::min(marketValues.size(), fundamentalValues.size());

    writeCsvHeader(out, kColumns);
    out << std::fixed << std::setprecision(8);

    for (std::size_t row = 0; row < totalRows; ++row) {
        const bool isSimulationRow = row > config.warmupSteps;
        const std::size_t simulationStep = isSimulationRow ? (row - config.warmupSteps) : 0;
        const StepDetails* step = nullptr;
        if (isSimulationRow && simulationStep - 1 < details.size()) {
            step = &details.at(simulationStep - 1);
        }
        const char* phase = row == 0             ? "initial"
                            : row <= config.warmupSteps ? "warmup"
                                                        : "simulation";

        writeCsvRow(out, kColumns,
                    Row{row, phase, marketValues.at(row), fundamentalValues.at(row), step});
    }

    out.flush();
    if (!out.good()) {
        error = "Failed while writing CSV file: " + outputPath;
        return false;
    }

    return true;
}

} // namespace abm::output_detail
