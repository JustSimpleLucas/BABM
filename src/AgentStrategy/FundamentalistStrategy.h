// FundamentalistStrategy.h

#ifndef ABM_AGENT_STRATEGY_FUNDAMENTALIST_STRATEGY_H
#define ABM_AGENT_STRATEGY_FUNDAMENTALIST_STRATEGY_H

#include <cstddef>
#include <optional>
#include <string>

#include "Agent/AgentAction.h"
#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/TradingStrategy.h"
#include "Config/SimulationConfig.h"

namespace abm {
class Agent;
class Market;

/**
 * Stop-loss and take-profit controls for value-oriented agents.
 *
 * Grouping these thresholds makes the behavioural risk-management rule explicit
 * and prevents accidentally swapping two adjacent floating-point arguments.
 */
struct FundamentalistRiskThresholds {
    /** Loss ratio from entry price that triggers forced liquidation. */
    double stopLossThreshold{0.05};

    /** Gain ratio from entry price that triggers profit-taking liquidation. */
    double takeProfitThreshold{0.10};
};

/**
 * Construction parameters for a fundamentalist strategy.
 *
 * The parameters map directly to the thesis-level modelling assumptions:
 * mispricing sensitivity, behavioural risk limits, volatility estimation, and
 * the mean-variance portfolio sizing rule.
 */
struct FundamentalistStrategyParameters {
    /** Asset key traded by this agent. */
    std::size_t assetIndex{0};

    /** Mean-variance portfolio sizing rule. */
    AssetAllocationLine allocationLine;

    /** Relative mispricing required before trading. */
    double mispricingThreshold{0.02};

    /** Stop-loss and take-profit liquidation thresholds. */
    FundamentalistRiskThresholds riskThresholds{};

    /** Number of recent log returns used to estimate volatility. */
    std::size_t volatilityWindow{20};

    /** Per-step risk-free return. */
    double riskFreeRate{0.0};

    /** CPT reference point rule. */
    ProspectReferencePointMode referencePointMode{ProspectReferencePointMode::AveragePurchasePrice};

    /** Reference window used when CPT anchors on moving-average price. */
    std::size_t referenceMovingAverageWindow{20};

    /** Cap on portfolio gross exposure sum_j |w_j| in the multi-asset rule. */
    double maxGrossExposure{1.0};

    /**
     * Steps over which the mispricing is expected to close (at least one).
     *
     * The mispricing is the log return expected over this horizon. Sizing uses
     * it divided by the horizon, a per-step return commensurate with the
     * per-step covariance, and CPT values the gamble over the same horizon.
     */
    double forecastHorizon{1.0};
};

/**
 * Value-oriented strategy trading on market price versus latent fundamental value.
 *
 * Fundamentalists represent boundedly rational investors who react when
 * mispricing is large enough to overcome a threshold. Stop-loss and
 * take-profit rules expose behavioural risk-management assumptions that are
 * especially relevant during crisis simulations.
 */
class FundamentalistStrategy : public TradingStrategy {
  public:
    /** Constructs a default fundamentalist strategy for tests or placeholders. */
    FundamentalistStrategy();

    /**
     * Constructs a fundamentalist strategy with explicit valuation and risk controls.
     *
     * @param parameters Named strategy controls for mispricing sensitivity,
     * liquidation thresholds, volatility estimation, and portfolio sizing.
     */
    explicit FundamentalistStrategy(const FundamentalistStrategyParameters& parameters);

    /** Returns the export label for this strategy rule. */
    [[nodiscard]] std::string strategyType() const override;

    using TradingStrategy::generateOrder;

    /** Returns the asset key traded by this fundamentalist. */
    [[nodiscard]] std::size_t assetIndex() const;

    /** Updates the per-step risk-free return used in allocation. */
    void setRiskFreeRate(double riskFreeRate);

    /** Returns the per-step risk-free return. */
    [[nodiscard]] double riskFreeRate() const;

    /** Updates the minimum relative mispricing required before trading. */
    void setMispricingThreshold(double threshold);

    /** Returns the minimum relative mispricing required before trading. */
    [[nodiscard]] double mispricingThreshold() const;

    /** Updates stop-loss and take-profit liquidation thresholds. */
    void setRiskThresholds(FundamentalistRiskThresholds thresholds);

    /** Returns the stop-loss threshold. */
    [[nodiscard]] double stopLossThreshold() const;

    /** Returns the take-profit threshold. */
    [[nodiscard]] double takeProfitThreshold() const;

    /** Updates the realised-volatility estimation window. */
    void setVolatilityWindow(std::size_t window);

    /** Returns the realised-volatility estimation window. */
    [[nodiscard]] std::size_t volatilityWindow() const;

    /**
     * Generates a limit order from fundamental mispricing and portfolio demand.
     *
     * @param agent Persistent agent whose accounting and preferences are used.
     * @param market Market state containing both realised and fundamental histories.
     * @param timeStep Simulation time step assigned to the order.
     * @param context Simulation-level controls for valuation quotes, social
     * opinion, hold tolerance, and price-grid quantisation.
     * @return A validated order, or std::nullopt when the agent elects not to trade.
     */
    [[nodiscard]] std::optional<Order> generateOrder(Agent& agent, const Market& market,
                                                     int timeStep,
                                                     const TradingOrderContext& context) override;

    /**
     * Generates up to one order per asset from joint Markowitz portfolio demand.
     *
     * When the context carries a market view (per-asset prices and the shared
     * log-return covariance), per-asset CPT-adjusted mispricing forecasts feed
     * the full mean-variance solve and each asset is rebalanced toward its
     * optimal weight. Without a view the single-asset legacy path is used.
     */
    [[nodiscard]] std::vector<Order> generateOrders(Agent& agent, const Market& market,
                                                    int timeStep,
                                                    const TradingOrderContext& context,
                                                    const MarketStepView& marketView) override;

  private:
    struct PriceInputs {
        double marketPrice;
        double fundamentalPrice;
    };

    struct SignalDecision {
        AgentAction action;
        bool forceLiquidation;
    };

    struct PortfolioSizingInputs {
        double wealth;
        double riskyWeight;
        double marketPrice;
        bool forceLiquidation;
    };

    struct OrderSizingInputs {
        PriceInputs prices;
        double targetRiskyUnits;
    };

    struct OrderIntent {
        OrderType type;
        double price;
        double quantity;
    };

    struct ProspectAdjustmentInputs {
        double expectedExcessReturn;
        double volatility;
        double marketPrice;
    };

    [[nodiscard]] SignalDecision generateSignal(const Agent& agent, const PriceInputs& prices,
                                                double transactionCostReturnHurdle) const;
    [[nodiscard]] SignalDecision
    generateSignalForPosition(const PriceInputs& prices, double stock, double averageEntryPrice,
                              double transactionCostReturnHurdle) const;
    [[nodiscard]] static double mispricing(const PriceInputs& prices);
    [[nodiscard]] static double forecastExcessReturn(double mispricingValue);
    [[nodiscard]] static double targetRiskyUnits(const PortfolioSizingInputs& inputs);
    [[nodiscard]] static double buyQuantity(const Agent& agent, const OrderSizingInputs& inputs,
                                            double orderPrice, double transactionCostRate);
    [[nodiscard]] static double sellQuantity(const Agent& agent, const SignalDecision& decision,
                                             const OrderSizingInputs& inputs);
    [[nodiscard]] static std::optional<OrderIntent>
    buildSignalOrderIntent(const Agent& agent, const SignalDecision& decision,
                           const OrderSizingInputs& inputs, const TradingOrderContext& context);
    [[nodiscard]] static std::optional<OrderIntent>
    buildValuationOrderIntent(const Agent& agent, const SignalDecision& decision,
                              const OrderSizingInputs& inputs, const TradingOrderContext& context);
    /** Returns the (CPT-adjusted) excess log return expected over the forecast horizon. */
    [[nodiscard]] double
    prospectAdjustedHorizonReturn(Agent& agent, const Market& market, std::size_t assetIndex,
                                  const ProspectAdjustmentInputs& inputs) const;

    std::size_t assetIndex_;
    AssetAllocationLine allocationLine_;
    double mispricingThreshold_;
    double stopLossThreshold_;
    double takeProfitThreshold_;
    std::size_t volatilityWindow_;
    double riskFreeRate_;
    ProspectReferencePointMode referencePointMode_;
    std::size_t referenceMovingAverageWindow_;
    double maxGrossExposure_{1.0};
    double forecastHorizon_{1.0};
};

} // namespace abm

#endif // ABM_AGENT_STRATEGY_FUNDAMENTALIST_STRATEGY_H
