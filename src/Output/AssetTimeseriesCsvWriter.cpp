// AssetTimeseriesCsvWriter.cpp

#include "Output/AssetTimeseriesCsvWriter.h"

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
 * One (row, asset) line of the long-format asset series.
 *
 * `step` is null on the initial and warm-up rows, which carry price levels but
 * no clearing outcome; the columns that read it then emit nothing.
 */
struct Row {
    std::size_t rowIndex{0};
    const char* phase{""};
    const std::string& assetName;
    double marketPrice{0.0};
    double fundamentalPrice{0.0};
    const AssetStepDetails* step{nullptr};
};

constexpr CsvColumn<Row> kColumns[] = {
    {"row_index", [](std::ostream& out, const Row& r) { out << r.rowIndex; }},
    {"phase", [](std::ostream& out, const Row& r) { out << r.phase; }},
    {"simulation_step",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->step;
         }
     }},
    {"asset", [](std::ostream& out, const Row& r) { out << r.assetName; }},
    {"market_price", [](std::ostream& out, const Row& r) { out << r.marketPrice; }},
    {"fundamental_price", [](std::ostream& out, const Row& r) { out << r.fundamentalPrice; }},
    {"raw_return",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->rawReturn;
         }
     }},
    {"log_return",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->logReturn;
         }
     }},
    {"submitted_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->submittedLimitOrders + r.step->submittedMarketOrders;
         }
     }},
    {"submitted_limit_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->submittedLimitOrders;
         }
     }},
    {"submitted_market_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->submittedMarketOrders;
         }
     }},
    {"traded_volume",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->tradedVolume;
         }
     }},
    {"executed_trades",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->executedTrades;
         }
     }},
    {"last_trade_price",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->lastTradePrice;
         }
     }},
    {"best_bid",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->bestBid;
         }
     }},
    {"best_ask",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->bestAsk;
         }
     }},
    {"bid_ask_spread",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->bidAskSpread;
         }
     }},
    {"mid_quote",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->midQuote;
         }
     }},
    {"bid_depth",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->bidDepth;
         }
     }},
    {"ask_depth",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->askDepth;
         }
     }},
    {"resting_bid_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->restingBidOrders;
         }
     }},
    {"resting_ask_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->restingAskOrders;
         }
     }},
    {"stale_cancelled_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->staleCancelledOrders;
         }
     }},
    {"expired_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->expiredOrders;
         }
     }},
    {"infeasible_resting_cancellations",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->infeasibleRestingCancellations;
         }
     }},
    {"infeasible_incoming_cancellations",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->infeasibleIncomingCancellations;
         }
     }},
    {"self_trade_preventions",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->selfTradePreventions;
         }
     }},
    {"collar_rejected_orders",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->collarRejectedOrders;
         }
     }},
    {"total_transaction_costs",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->totalTransactionCosts;
         }
     }},
    {"realized_allocative_surplus",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->realizedAllocativeSurplus;
         }
     }},
    {"maximum_allocative_surplus",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->maximumAllocativeSurplus;
         }
     }},
    {"allocative_efficiency",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->allocativeEfficiency;
         }
     }},
    {"mean_agent_portfolio_weight",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->meanAgentPortfolioWeight;
         }
     }},
    {"portfolio_weight_agent_count",
     [](std::ostream& out, const Row& r) {
         if (r.step != nullptr) {
             out << r.step->portfolioWeightAgentCount;
         }
     }},
};

} // namespace

bool exportAssetTimeseriesCsv(const std::string& outputPath, const SimulationRunResult& result,
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
    const MultiAssetRunData& multiAsset = result.multiAssetData();
    const std::size_t assetCount = multiAsset.assetNames.size();

    std::size_t totalRows = multiAsset.marketPriceHistories.front().size();
    for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
        totalRows = std::min({totalRows, multiAsset.marketPriceHistories[assetIndex].size(),
                              multiAsset.fundamentalPriceHistories[assetIndex].size()});
    }

    writeCsvHeader(out, kColumns);
    out << std::fixed << std::setprecision(8);

    std::size_t rowIndex = 0;
    for (std::size_t row = 0; row < totalRows; ++row) {
        const bool isSimulationRow = row > config.warmupSteps;
        const std::size_t simulationStep = isSimulationRow ? (row - config.warmupSteps) : 0;
        const char* phase = row == 0             ? "initial"
                            : row <= config.warmupSteps ? "warmup"
                                                        : "simulation";

        for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
            const AssetStepDetails* step = nullptr;
            if (isSimulationRow) {
                const std::size_t detailIndex = ((simulationStep - 1) * assetCount) + assetIndex;
                if (detailIndex < multiAsset.assetStepDetails.size()) {
                    const AssetStepDetails& candidate = multiAsset.assetStepDetails[detailIndex];
                    if (candidate.step == simulationStep && candidate.assetIndex == assetIndex) {
                        step = &candidate;
                    }
                }
            }

            writeCsvRow(out, kColumns,
                        Row{rowIndex++, phase, multiAsset.assetNames[assetIndex],
                            multiAsset.marketPriceHistories[assetIndex].at(row),
                            multiAsset.fundamentalPriceHistories[assetIndex].at(row), step});
        }
    }

    out.flush();
    if (!out.good()) {
        error = "Failed while writing CSV file: " + outputPath;
        return false;
    }

    return true;
}

} // namespace abm::output_detail
