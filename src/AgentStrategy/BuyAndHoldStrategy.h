// BuyAndHoldStrategy.h

#ifndef ABM_AGENT_STRATEGY_BUY_AND_HOLD_STRATEGY_H
#define ABM_AGENT_STRATEGY_BUY_AND_HOLD_STRATEGY_H

#include <optional>
#include <string>

#include "AgentStrategy/TradingStrategy.h"

namespace abm {
class Agent;
class Market;

/**
 * Passive long-only allocation rule for buy-and-hold investors.
 *
 * The strategy represents investors who aim to accumulate a desired risky-asset
 * portfolio weight and then hold the acquired position. It does not react to
 * short-term signals, social opinion, or Prospect Theory valuation. This makes
 * the behavioural assumption explicit: passive demand supplies persistent
 * one-sided buying pressure until the configured risky allocation is reached.
 */
class BuyAndHoldStrategy : public TradingStrategy {
  public:
    /** Constructs a default strategy for tests or placeholder use. */
    BuyAndHoldStrategy();

    /**
     * Constructs a buy-and-hold strategy with explicit asset and allocation target.
     *
     * @param assetIndex Index of the asset traded by this passive investor.
     * @param targetRiskyWeight Desired risky-asset portfolio share in (0, 1].
     */
    BuyAndHoldStrategy(std::size_t assetIndex, double targetRiskyWeight);

    /** Returns the export label for this strategy rule. */
    [[nodiscard]] std::string strategyType() const override;

    using TradingStrategy::generateOrder;

    /** Returns the asset key traded by this buy-and-hold investor. */
    [[nodiscard]] std::size_t assetIndex() const;

    /** Returns the desired risky-asset portfolio share. */
    [[nodiscard]] double targetRiskyWeight() const;

    /** Updates the desired risky-asset portfolio share. */
    void setTargetRiskyWeight(double targetRiskyWeight);

    /**
     * Generates a buy order until the target risky allocation has been reached.
     *
     * @return A BUY order for the full remaining target gap, or std::nullopt
     * when the investor already holds at least the desired risky allocation or
     * lacks cash to buy a positive quantity.
     */
    [[nodiscard]] std::optional<Order> generateOrder(Agent& agent, const Market& market,
                                                     int timeStep,
                                                     const TradingOrderContext& context) override;

    /**
     * Generates buy orders that split the target weight equally across assets.
     *
     * Each asset receives targetRiskyWeight / N of current wealth; underweight
     * assets are bought toward their share, subject to remaining cash. Without
     * a market view the single-asset legacy path is used.
     */
    [[nodiscard]] std::vector<Order> generateOrders(Agent& agent, const Market& market,
                                                    int timeStep,
                                                    const TradingOrderContext& context,
                                                    const MarketStepView& marketView) override;

  private:
    std::size_t assetIndex_;
    double targetRiskyWeight_;
};

} // namespace abm

#endif // ABM_AGENT_STRATEGY_BUY_AND_HOLD_STRATEGY_H
