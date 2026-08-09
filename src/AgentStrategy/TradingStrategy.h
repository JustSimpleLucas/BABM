// TradingStrategy.h

#ifndef TRADING_STRATEGY_H
#define TRADING_STRATEGY_H

#include <optional>
#include <string>
#include <vector>

#include "OrderBook/Order.h"

namespace abm {
class Agent;
class AssetUniverse;
class Market;
struct SymmetricMatrix;

/**
 * Shared per-step market view supplied to every strategy.
 *
 * The engine computes this once per step so every agent prices the same
 * cross-asset state without per-agent recomputation. All vectors follow
 * AssetUniverse index order.
 *
 * The members are references rather than pointers because the view is always
 * complete: there is no "no market" case for a running simulation. Strategies
 * used to accept a nullable view and fall back to a single-asset routine when
 * any member was missing, which meant a one-asset run executed different code
 * from a two-asset run. Making the view non-nullable — and `assets` an
 * AssetUniverse, which is never empty — leaves that fallback inexpressible.
 */
struct MarketStepView {
    const std::vector<double>& latestPrices;
    const SymmetricMatrix& covariance;
    const AssetUniverse& assets;
};

/**
 * Contextual controls used when a strategy converts its signal into an order.
 *
 * These values are grouped because they are simulation-level trading controls,
 * not part of the strategy's persistent behavioural rule. Naming them at the
 * call site also avoids error-prone positional runs of floating-point arguments.
 */
struct TradingOrderContext {
    /** Whether the quote should be anchored to the agent's valuation. */
    bool useValuationLimitPrice{false};

    /** Current social opinion signal; zero represents neutral social influence. */
    double socialOpinion{0.0};

    /** Strength of the social opinion signal in log-price space. */
    double opinionKappa{0.0};

    /** Minimum absolute log-price gap required before submitting an order. */
    double holdTolerance{0.0};

    /** Price grid used for limit-order quantisation; non-positive disables snapping. */
    double priceTickSize{0.0};

    /** One-way proportional transaction-cost rate paid at execution. */
    double transactionCostRate{0.0};

    /** Whether strategy decisions should include transaction-cost no-trade bands. */
    bool transactionCostAffectsDecisions{true};
};

/**
 * Interface for behavioural trading rules applied to persistent agents.
 *
 * A TradingStrategy transforms market information and the current state of an
 * Agent into an optional limit order. The Agent owns identity, accounting, and
 * behavioural preference parameters, while the strategy owns only the rule used
 * to interpret market signals. This separation keeps agent identity independent
 * from the initial strategy assignment and prepares the model for future
 * strategy-switching rules.
 */
class TradingStrategy {
  public:
    virtual ~TradingStrategy() = default;

    /** Returns the export label for the active strategy rule. */
    [[nodiscard]] virtual std::string strategyType() const = 0;

    /**
     * Generates an order with the baseline individual-only trading settings.
     *
     * This non-virtual overload keeps simple test and research call sites concise
     * without placing default arguments on the virtual dispatch interface. Social
     * influence, valuation-price quoting, hold tolerance, and tick quantisation are
     * disabled by default.
     */
    [[nodiscard]] std::optional<Order> generateOrder(Agent& agent, const Market& market,
                                                     int timeStep) {
        return generateOrder(agent, market, timeStep, TradingOrderContext{});
    }

    /**
     * Generates a limit order for the supplied persistent agent.
     *
     * @param agent Persistent market participant that owns accounting state.
     * @param market Market state containing price and fundamental histories.
     * @param timeStep Simulation time step assigned to the order.
     * @param context Simulation-level controls for valuation quotes, social
     * opinion, hold tolerance, and price-grid quantisation.
     * @return A validated order, or std::nullopt when the agent does not trade.
     */
    [[nodiscard]] virtual std::optional<Order>
    generateOrder(Agent& agent, const Market& market, int timeStep,
                  const TradingOrderContext& context) = 0;

    /**
     * Generates up to one order per asset for the supplied persistent agent.
     *
     * Every strategy rebalances against the whole asset universe; a one-asset
     * universe is the degenerate case of that rule, not a separate routine.
     * There is deliberately no default implementation: the previous default
     * wrapped generateOrder into a single asset-zero order and served as the
     * fallback that let some strategies treat one asset as a special case.
     *
     * @param marketView Per-step cross-asset state shared by all agents.
     */
    [[nodiscard]] virtual std::vector<Order> generateOrders(Agent& agent, const Market& market,
                                                            int timeStep,
                                                            const TradingOrderContext& context,
                                                            const MarketStepView& marketView) = 0;
};

} // namespace abm

#endif // TRADING_STRATEGY_H
