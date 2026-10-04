// ChartistStrategy.h

#ifndef ABM_AGENT_STRATEGY_CHARTIST_STRATEGY_H
#define ABM_AGENT_STRATEGY_CHARTIST_STRATEGY_H

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
 * Shared parameters for chartist technical strategies.
 *
 * Each concrete chartist rule owns only its technical signal formation. Common
 * portfolio sizing, CPT adjustment, social quote adjustment, and short-exposure
 * controls remain centralised in ChartistStrategy so the strategy family stays
 * comparable across experiments.
 */
struct ChartistStrategyParameters {
    /** Asset key traded by this chartist. */
    std::size_t assetIndex{0};

    /**
     * Mean-variance portfolio sizing rule used after signal formation.
     *
     * The default lower bound of -0.30 matches the default maxShortWeight so
     * short exposure is available out of the box; the configured allocation
     * floor and the short-exposure cap bind independently at sizing time.
     */
    AssetAllocationLine allocationLine{3.0, -0.30, 1.0};

    /** Number of recent one-period log returns used to estimate volatility. */
    std::size_t volatilityWindow{20};

    /** Per-step risk-free return used in allocation. */
    double riskFreeRate{0.0};

    /** Maximum absolute short risky weight available to this strategy. */
    double maxShortWeight{0.30};

    /** Prospect Theory reference point rule used when CPT valuation is enabled. */
    ProspectReferencePointMode referencePointMode{ProspectReferencePointMode::AveragePurchasePrice};

    /** Lookback window used when the reference point mode is MovingAveragePrice. */
    std::size_t referenceMovingAverageWindow{20};

    /** Cap on portfolio gross exposure sum_j |w_j| in the multi-asset rule. */
    double maxGrossExposure{1.0};

    /**
     * Steps over which the technical forecast is expected to play out (at least one).
     *
     * The forecast is the log return expected over this horizon: the valuation
     * quote is the price expected at the horizon, sizing uses the forecast
     * divided by the horizon, and CPT values the gamble over the horizon.
     */
    double forecastHorizon{1.0};
};

/**
 * Abstract base for technical chartist strategies.
 *
 * Chartists infer expected returns from realised market-price patterns rather
 * than from the latent fundamental value. Derived classes implement a single
 * academically traceable technical rule, while this base class turns that rule
 * into reproducible orders using the shared behavioural-finance machinery.
 */
class ChartistStrategy : public TradingStrategy {
  public:
    ~ChartistStrategy() override = default;

    /** Returns the export label for this concrete technical rule. */
    [[nodiscard]] std::string strategyType() const override = 0;

    using TradingStrategy::generateOrder;

    /** Returns the asset key traded by this chartist. */
    [[nodiscard]] std::size_t assetIndex() const;

    /** Updates the per-step risk-free return used in allocation. */
    void setRiskFreeRate(double riskFreeRate);

    /** Returns the per-step risk-free return. */
    [[nodiscard]] double riskFreeRate() const;

    /** Updates the maximum short exposure applied at portfolio sizing time. */
    void setMaxShortWeight(double maxShortWeight);

    /** Returns the maximum absolute short exposure. */
    [[nodiscard]] double maxShortWeight() const;

    /** Updates the realised-volatility estimation window. */
    void setVolatilityWindow(std::size_t volatilityWindow);

    /** Returns the realised-volatility estimation window. */
    [[nodiscard]] std::size_t volatilityWindow() const;

    /**
     * Generates a limit order from the chartist signal and portfolio rule.
     *
     * @param agent Persistent agent whose accounting and preferences are used.
     * @param market Market state containing price history.
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
     * When the context carries a market view, the concrete technical rule is
     * evaluated per asset and the CPT-adjusted forecasts feed the full
     * mean-variance solve. Without a view the single-asset legacy path is used.
     */
    [[nodiscard]] std::vector<Order> generateOrders(Agent& agent, const Market& market,
                                                    int timeStep,
                                                    const TradingOrderContext& context,
                                                    const MarketStepView& marketView) override;

  protected:
    /** Constructs a concrete chartist strategy from shared strategy parameters. */
    explicit ChartistStrategy(ChartistStrategyParameters parameters);

    /** Returns the raw technical buy/sell/hold signal for the concrete rule. */
    [[nodiscard]] virtual AgentAction generateSignal(const Market& market) const = 0;

    /** Returns the expected excess log return implied by the concrete rule for one asset. */
    [[nodiscard]] virtual double forecastExcessReturn(const Market& market,
                                                      std::size_t forecastAssetIndex) const = 0;

  private:
    /** Returns the (CPT-adjusted) excess log return expected over the forecast horizon. */
    [[nodiscard]] double prospectAdjustedHorizonReturn(Agent& agent, const Market& market,
                                                       std::size_t forecastAssetIndex,
                                                       double expectedExcessReturn,
                                                       double volatility, double marketPrice) const;

    std::size_t assetIndex_;
    AssetAllocationLine allocationLine_;
    std::size_t volatilityWindow_;
    double riskFreeRate_;
    double maxShortWeight_;
    ProspectReferencePointMode referencePointMode_;
    std::size_t referenceMovingAverageWindow_;
    double maxGrossExposure_{1.0};
    double forecastHorizon_{1.0};
};

} // namespace abm

#endif // ABM_AGENT_STRATEGY_CHARTIST_STRATEGY_H
