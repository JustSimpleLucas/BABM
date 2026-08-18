// Results/SimulationRunResult.h

#ifndef ABM_RESULTS_SIMULATION_RUN_RESULT_H
#define ABM_RESULTS_SIMULATION_RUN_RESULT_H

#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "Config/SimulationConfig.h"
#include "OrderBook/Order.h"

namespace abm {

/** Aggregate diagnostics from one completed simulation run. */
struct SimulationStats {
    /** Number of post-warm-up simulation steps completed. */
    std::size_t completedSteps{0};

    /** Last realised market price stored by the market. */
    double finalMarketPrice{0.0};

    /** Last latent fundamental value stored by the market. */
    double finalFundamentalPrice{0.0};

    /** Total executed quantity across all trades. */
    double totalTradedVolume{0.0};

    /** Average absolute notional order imbalance across simulation steps. */
    double averageAbsoluteOrderImbalance{0.0};

    /** Total proportional transaction costs paid by agents. */
    double totalTransactionCosts{0.0};
};

/** Per-(step, asset) diagnostic record exported for multi-asset analysis. */
struct AssetStepDetails {
    std::size_t step{0};
    std::uint32_t assetIndex{0};
    double referencePrice{0.0};
    double marketPrice{0.0};
    double fundamentalPrice{0.0};
    double rawReturn{0.0};
    double logReturn{0.0};
    std::size_t submittedLimitOrders{0};
    std::size_t submittedMarketOrders{0};
    double tradedVolume{0.0};
    std::size_t executedTrades{0};
    double lastTradePrice{0.0};
    double bestBid{0.0};
    double bestAsk{0.0};
    double bidAskSpread{0.0};
    double midQuote{0.0};
    double bidDepth{0.0};
    double askDepth{0.0};
    std::size_t restingBidOrders{0};
    std::size_t restingAskOrders{0};
    std::size_t staleCancelledOrders{0};
    std::size_t expiredOrders{0};
    std::size_t infeasibleRestingCancellations{0};
    std::size_t infeasibleIncomingCancellations{0};
    std::size_t selfTradePreventions{0};
    std::size_t collarRejectedOrders{0};
    double totalTransactionCosts{0.0};

    /** Gross surplus realised by this asset's double-auction executions. */
    double realizedAllocativeSurplus{0.0};

    /** Maximum gross surplus available from this asset's submitted and resting orders. */
    double maximumAllocativeSurplus{0.0};

    /** Realised surplus divided by maximum positive surplus, or zero if unavailable. */
    double allocativeEfficiency{0.0};

    /**
     * Cross-sectional mean portfolio weight held in this asset after the step.
     *
     * For agent i, w_ij = (q_ij * P_j) / W_i with W_i = c_i + sum_k q_ik * P_k,
     * averaged over agents with strictly positive wealth. Agents with
     * non-positive wealth are excluded because their weights are not
     * economically interpretable and would dominate the mean.
     *
     * Because the mean is linear, the mean cash weight is recovered downstream
     * as 1 - sum_j meanAgentPortfolioWeight_j, so cash needs no column of its
     * own. Weights are not clipped: leverage and short positions legitimately
     * push individual weights outside [0, 1].
     */
    double meanAgentPortfolioWeight{0.0};

    /** Number of agents with strictly positive wealth included in the mean. */
    std::size_t portfolioWeightAgentCount{0};
};

/**
 * Per-step diagnostic record for the primary asset.
 *
 * The per-asset half is the primary asset's AssetStepDetails record rather than
 * a second copy of the same twenty-three fields. Only the members declared
 * below it are genuinely extra: they are cross-asset (submittedOrders),
 * population level (wealthGiniCoefficient), or derived quantities that are
 * computed for the primary asset's book alone.
 */
struct StepDetails {
    /** The primary asset's per-step record. */
    AssetStepDetails asset{};

    /** Orders submitted across every asset during this step. */
    std::size_t submittedOrders{0};

    /** Net signed demand resting on the primary asset's book. */
    double netDemand{0.0};

    /** netDemand valued at the primary asset's reference price. */
    double notionalImbalance{0.0};

    /** notionalImbalance scaled by aggregate starting cash, clamped to [-1, 1]. */
    double normalizedImbalance{0.0};

    /** Relative gap between the new fundamental and the reference price. */
    double fundamentalSignal{0.0};

    /** Reserved exogenous price shock; continuous-LOB price formation leaves it at zero. */
    double randomShock{0.0};

    /**
     * Legacy aggregate cancellation count for the primary asset.
     *
     * Retained because the step_timeseries column contract predates the split
     * counters; `asset` carries the components (stale, infeasible resting, and
     * infeasible incoming) separately.
     */
    std::size_t cancelledOrders{0};

    /** Cross-sectional Gini coefficient of non-negative agent wealth after the step. */
    double wealthGiniCoefficient{0.0};
};

/**
 * Per-asset run output grouped so single-asset call sites stay unchanged.
 *
 * All vectors follow SimulationConfig::assets index order; assetStepDetails
 * holds one record per (step, asset) with assets contiguous inside each step.
 */
struct MultiAssetRunData {
    std::vector<std::string> assetNames{};
    std::vector<std::vector<double>> marketPriceHistories{};
    std::vector<std::vector<double>> fundamentalPriceHistories{};
    std::vector<AssetStepDetails> assetStepDetails{};
};

/**
 * Per-step record locating the protagonist inside the wealth cross-section.
 *
 * The end-of-run agent snapshot already says where he finished. This series says
 * how he got there, and — more usefully for a case study — whether the path was
 * his own doing or the market's: his wealth alone cannot distinguish an investor
 * who traded well from one who simply held a rising asset. Carrying the
 * population mean and median beside his wealth, and his rank within it, makes
 * that distinction readable directly off the chart.
 *
 * Recorded only when a protagonist is configured; the vector is empty otherwise.
 */
struct ProtagonistStepDetails {
    std::size_t step{0};

    /** Stable agent identifier, repeated on every row so the series is self-describing. */
    std::uint32_t agentId{0};

    double cash{0.0};

    /**
     * Inventory in the primary asset only.
     *
     * Named for what it is because riskyWeight sits beside it and covers every
     * asset: in a two-asset run he can hold nothing in the primary market and
     * still carry half his wealth in risk, and a column called `stock` would
     * make that look like an accounting error.
     */
    double primaryAssetStock{0.0};

    /** Mark-to-market wealth after the step's clearing and any forced buy-in. */
    double wealth{0.0};

    /** Share of his wealth held across all risky assets: (W - cash) / W, zero when insolvent. */
    double riskyWeight{0.0};

    std::size_t cumulativeTradeCount{0};
    double cumulativeTradedVolume{0.0};
    double cumulativeTransactionCostsPaid{0.0};

    /** Cross-sectional mean wealth over the whole population, including him. */
    double populationMeanWealth{0.0};

    /** Cross-sectional median wealth, which a skewed wealth distribution needs. */
    double populationMedianWealth{0.0};

    /**
     * Share of the population strictly poorer than he is, in [0, 1].
     *
     * A rank rather than a wealth difference, because it is the quantity that
     * stays comparable across runs with different price levels and endowments.
     */
    double wealthPercentileRank{0.0};

    /** Population size the rank was computed over, including the protagonist. */
    std::size_t populationSize{0};
};

/** Final agent-level state exported after a simulation run. */
struct AgentSnapshot {
    std::uint32_t agentId{0};
    std::string initialStrategyType;
    std::string currentStrategyType;
    double initialCash{0.0};
    double initialStock{0.0};
    double initialWealth{0.0};
    double xCoordinate{0.0};
    double yCoordinate{0.0};
    double socialGamma{0.0};
    double privateSignalStdDev{0.0};
    double finalOpinion{0.0};
    double finalCash{0.0};
    double finalStock{0.0};
    std::size_t tradeCount{0};
    double tradedVolume{0.0};
    double cumulativeTransactionCostsPaid{0.0};
    double finalWealth{0.0};
    double averageEntryPrice{0.0};
    double recentPeakWealth{0.0};
    double lastProspectReferencePoint{0.0};
    bool prospectTheoryEnabled{false};
    double prospectLossAversion{0.0};
    double prospectCurvatureForGain{0.0};
    double prospectCurvatureForLoss{0.0};
    double prospectProbabilityDistortionForGain{0.0};
    double prospectProbabilityDistortionForLoss{0.0};
    std::size_t prospectScenarioCount{0};

    /** True for the one individually parameterised participant, when configured. */
    bool isProtagonist{false};
};

/** Optional agent-facing trade ledger record exported for order-flow analysis. */
struct ExternalTradeLedgerRecord {
    std::size_t tradeId{0};
    std::size_t timeStep{0};
    std::uint32_t agentId{0};
    std::uint32_t counterpartyAgentId{0};
    OrderType side{OrderType::BUY};
    double price{0.0};
    double quantity{0.0};
    double grossNotional{0.0};
    double transactionCost{0.0};
    double netCashFlow{0.0};
    std::string asset;
    int orderId{0};
    int counterpartyOrderId{0};
};

/**
 * Immutable output-facing state for one completed simulation run.
 *
 * The simulation engine returns this value object so analysis, reporting, and
 * output writers depend on completed run data rather than on the mutable
 * controller that produced it.
 */
class SimulationRunResult {
  public:
    SimulationRunResult(SimulationConfig config, const SimulationStats& stats,
                        std::vector<StepDetails> stepDetails,
                        std::vector<AgentSnapshot> agentSnapshots,
                        std::vector<ExternalTradeLedgerRecord> externalTradeLedger,
                        MultiAssetRunData multiAssetData,
                        std::vector<ProtagonistStepDetails> protagonistStepDetails = {})
        : config_(std::move(config)), stats_(stats), stepDetails_(std::move(stepDetails)),
          agentSnapshots_(std::move(agentSnapshots)),
          externalTradeLedger_(std::move(externalTradeLedger)),
          multiAssetData_(std::move(multiAssetData)),
          protagonistStepDetails_(std::move(protagonistStepDetails)) {}

    /** Returns the effective simulation configuration after validation/clamping. */
    [[nodiscard]] const SimulationConfig& config() const {
        return config_;
    }

    /*
     * Primary-asset projections of the per-asset histories.
     *
     * These are derived rather than stored: they used to be separate vectors
     * copied alongside multiAssetData, which meant the same series existed
     * twice in every result and could in principle disagree.
     */

    /** Returns realised market prices including initial and warm-up observations. */
    [[nodiscard]] const std::vector<double>& marketPriceHistory() const {
        return multiAssetData_.marketPriceHistories.at(config_.assets.primaryIndex());
    }

    /** Returns latent fundamental values including initial and warm-up observations. */
    [[nodiscard]] const std::vector<double>& fundamentalPriceHistory() const {
        return multiAssetData_.fundamentalPriceHistories.at(config_.assets.primaryIndex());
    }

    /** Returns aggregate simulation diagnostics. */
    [[nodiscard]] const SimulationStats& stats() const {
        return stats_;
    }

    /** Returns per-step diagnostics for CSV export and stylised-fact analysis. */
    [[nodiscard]] const std::vector<StepDetails>& stepDetails() const {
        return stepDetails_;
    }

    /** Returns final agent-level state snapshots. */
    [[nodiscard]] const std::vector<AgentSnapshot>& agentSnapshots() const {
        return agentSnapshots_;
    }

    /** Returns the agent-facing trade ledger. */
    [[nodiscard]] const std::vector<ExternalTradeLedgerRecord>& externalTradeLedger() const {
        return externalTradeLedger_;
    }

    /** Returns per-asset histories and per-(step, asset) diagnostics. */
    [[nodiscard]] const MultiAssetRunData& multiAssetData() const {
        return multiAssetData_;
    }

    /** Returns the protagonist's per-step series, empty when none was configured. */
    [[nodiscard]] const std::vector<ProtagonistStepDetails>& protagonistStepDetails() const {
        return protagonistStepDetails_;
    }

  private:
    SimulationConfig config_{};
    SimulationStats stats_{};
    std::vector<StepDetails> stepDetails_;
    std::vector<AgentSnapshot> agentSnapshots_;
    std::vector<ExternalTradeLedgerRecord> externalTradeLedger_;
    MultiAssetRunData multiAssetData_{};
    std::vector<ProtagonistStepDetails> protagonistStepDetails_;
};

} // namespace abm

#endif // ABM_RESULTS_SIMULATION_RUN_RESULT_H
