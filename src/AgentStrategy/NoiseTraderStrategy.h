// NoiseTraderStrategy.h

#ifndef NOISE_TRADER_STRATEGY_H
#define NOISE_TRADER_STRATEGY_H

#include <optional>
#include <string>

#include "AgentStrategy/TradingStrategy.h"
#include "RandomGenerator/RandomGenerator.h"

namespace abm {
class Agent;
class Market;

/**
 * Uninformed random-liquidity strategy.
 *
 * Noise traders represent agents whose short-run demand is driven by stochastic
 * erroneous beliefs rather than by fundamental value or technical indicators.
 * The random belief shock is deliberately agent-specific and seeded so that the
 * same experiment configuration remains exactly reproducible.
 */
class NoiseTraderStrategy : public TradingStrategy {
  public:
    /** Constructs a default noise-trader strategy for tests or placeholders. */
    NoiseTraderStrategy();

    /**
     * Constructs a noise-trader strategy with explicit random-liquidity controls.
     *
     * @param assetIndex Index of the asset traded by this agent.
     * @param beliefShockStdDev Standard deviation of the zero-mean log-belief shock.
     * @param orderSizeFraction Fraction of current wealth committed to each order.
     * @param maxShortWeight Maximum absolute short risky weight allowed by the strategy.
     * @param seed Deterministic per-agent seed used for belief shocks.
     */
    NoiseTraderStrategy(std::size_t assetIndex, double beliefShockStdDev, double orderSizeFraction,
                        double maxShortWeight, std::uint64_t seed);

    /** Returns the export label for this strategy rule. */
    [[nodiscard]] std::string strategyType() const override;

    using TradingStrategy::generateOrder;

    /** Returns the asset key traded by this noise trader. */
    [[nodiscard]] std::size_t assetIndex() const;

    /** Returns the standard deviation of the log-belief shock. */
    [[nodiscard]] double beliefShockStdDev() const;

    /** Returns the wealth fraction committed to one order. */
    [[nodiscard]] double orderSizeFraction() const;

    /** Returns the maximum absolute short risky weight. */
    [[nodiscard]] double maxShortWeight() const;

    /**
     * Generates a random-liquidity order from a stochastic log-belief shock.
     *
     * Positive shocks submit buy orders and negative shocks submit sell orders.
     * The quote is anchored at the latest market price multiplied by exp(shock).
     */
    [[nodiscard]] std::optional<Order> generateOrder(Agent& agent, const Market& market,
                                                     int timeStep,
                                                     const TradingOrderContext& context) override;

    /**
     * Generates one random-liquidity order on one uniformly drawn asset.
     *
     * With more than one asset in the market view, the trader draws the traded
     * asset from its private engine before forming the belief shock; with one
     * asset (or no view) the private random stream is identical to the
     * historical single-asset behaviour.
     */
    [[nodiscard]] std::vector<Order> generateOrders(Agent& agent, const Market& market,
                                                    int timeStep,
                                                    const TradingOrderContext& context,
                                                    const MarketStepView& marketView) override;

  private:
    [[nodiscard]] std::optional<Order> generateOrderForAsset(Agent& agent, double marketPrice,
                                                             std::size_t assetIndex, int timeStep,
                                                             const TradingOrderContext& context);
    void setBeliefShockStdDev(double beliefShockStdDev);
    void setOrderSizeFraction(double orderSizeFraction);
    void setMaxShortWeight(double maxShortWeight);

    std::size_t assetIndex_;
    double beliefShockStdDev_;
    double orderSizeFraction_;
    double maxShortWeight_;
    RandomEngine random_;
};

} // namespace abm

#endif // NOISE_TRADER_STRATEGY_H
