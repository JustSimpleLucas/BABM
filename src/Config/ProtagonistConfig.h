// ProtagonistConfig.h

#ifndef ABM_CONFIG_PROTAGONIST_CONFIG_H
#define ABM_CONFIG_PROTAGONIST_CONFIG_H

#include <cstddef>
#include <cstdint>
#include <string>

#include "Config/StrategyConfig.h"

namespace abm {

/** Trading rule assigned to the protagonist. */
enum class ProtagonistStrategyKind : std::uint8_t {
    Fundamentalist = 0,
    Chartist = 1,
    NoiseTrader = 2,
    BuyAndHold = 3,
};

/**
 * Parameters for one individually specified market participant.
 *
 * Every other agent in the model is anonymous: it belongs to a strategy
 * population, and its behavioural preferences are drawn from a shared
 * distribution. That is the right representation for studying aggregate market
 * outcomes, but it cannot answer the question a behavioural-finance narrative
 * usually asks — what happened to *one* identified investor with a stated
 * endowment, a stated risk appetite, and stated loss aversion.
 *
 * The protagonist is that investor. He is deliberately an ordinary trader: he
 * runs one of the four existing strategies through the same order-generation,
 * clearing, and risk machinery as everybody else, and the market is not told
 * that he is special. Only his *parameters* are individual, which is what makes
 * him a case study rather than a new modelling mechanism.
 *
 * Two design consequences are worth stating explicitly, because they are what
 * keep the construct reproducible:
 *
 *  - He is an **additional** agent. The population counts continue to mean
 *    exactly what they say, so a run with a protagonist has one more
 *    participant than the same configuration without one.
 *  - None of his parameters are sampled. His prospect-theory preferences and
 *    his chartist rule are configured rather than drawn, so constructing him
 *    consumes no values from the shared agent random stream. With
 *    `enabled = false` a run therefore reproduces byte-for-byte what it
 *    produced before the protagonist existed.
 */
struct ProtagonistConfig {
    /** Adds the protagonist to the population when true. */
    bool enabled{false};

    /** Human-readable label carried into reports and the dashboard panel. */
    std::string name{"protagonist"};

    /** Trading rule he follows for the whole run. */
    ProtagonistStrategyKind strategy{ProtagonistStrategyKind::Fundamentalist};

    /**
     * Concrete technical rule used when `strategy` is Chartist.
     *
     * ChartistStrategyMode::Random is rejected by validation. A population may
     * legitimately sample across the four technical rules, but an identified
     * individual whose rule is unknown until the seed is drawn cannot be
     * described in a write-up, so his rule must be stated.
     */
    ChartistStrategyMode chartistRule{ChartistStrategyMode::Momentum};

    /** Cash endowment at initialisation, independent of the population's. */
    double initialCash{10000.0};

    /** Per-asset share endowment; applied to every asset in the universe. */
    double initialStock{100.0};

    /** Mean-variance sizing bounds applied to whatever signal his rule produces. */
    AllocationConfig allocation{3.0, 0.0, 1.0, 1.0};

    /*
     * Rule parameters.
     *
     * Only the block matching `strategy` is read when his strategy object is
     * built, but every value is validated regardless. A mistyped threshold that
     * happens to belong to an unselected rule should still fail the run rather
     * than sit unnoticed in the configuration file.
     */

    /** Minimum relative mispricing before he trades, under the fundamentalist rule. */
    double mispricingThreshold{0.02};

    /** Relative loss from his entry price that forces him to close. */
    double stopLossThreshold{0.05};

    /** Relative gain from his entry price at which he takes profit. */
    double takeProfitThreshold{0.10};

    /** Recent one-period log returns he uses to estimate realised volatility. */
    std::size_t volatilityWindow{20};

    /** Short moving-average window used by the momentum rule. */
    std::size_t shortWindow{5};

    /** Long moving-average window used by the momentum and mean-reversion rules. */
    std::size_t longWindow{20};

    /** Deadband applied to weak short-minus-long moving-average gaps. */
    double momentumSignalThreshold{0.0};

    /** Donchian-style lookback used by the breakout rule. */
    std::size_t breakoutWindow{20};

    /** Maximum absolute short weight; forced to zero when shorting is disabled. */
    double maxShortWeight{0.30};

    /** Standard deviation of his zero-mean log-belief shock, under the noise rule. */
    double noiseBeliefShockStdDev{0.02};

    /** Fraction of investable wealth he commits to one noise order. */
    double noiseOrderSizeFraction{0.05};

    /** Risky-asset share he accumulates to and then holds, under the passive rule. */
    double buyHoldTargetRiskyWeight{0.60};

    /*
     * Behavioural preferences.
     *
     * These are independent of control_prospect_theory_agent_fraction: that
     * fraction assigns CPT valuation across the anonymous population by a
     * seeded draw, which is exactly the mechanism an identified individual must
     * not be subject to. His switch and his four preference parameters are set
     * directly, so an experiment can make him the loss-averse investor in an
     * otherwise expected-utility market, or the reverse.
     */

    /** Applies Cumulative Prospect Theory valuation to his decisions when true. */
    bool prospectTheoryEnabled{false};

    /** Loss-aversion coefficient lambda: how much more losses weigh than gains. */
    double lossAversion{2.25};

    /** Value-function curvature over gains. */
    double curvatureForGain{0.88};

    /** Value-function curvature over losses. */
    double curvatureForLoss{0.88};

    /** Probability-weighting parameter applied to gain-side cumulative probabilities. */
    double probDistortionForGain{0.61};

    /** Probability-weighting parameter applied to loss-side cumulative probabilities. */
    double probDistortionForLoss{0.69};
};

} // namespace abm

#endif // ABM_CONFIG_PROTAGONIST_CONFIG_H
