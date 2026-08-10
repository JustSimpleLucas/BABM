// StrategyConfig.h

#ifndef ABM_CONTROL_PARAMETERS_STRATEGY_CONFIG_H
#define ABM_CONTROL_PARAMETERS_STRATEGY_CONFIG_H

#include <cstddef>
#include <cstdint>

namespace abm {

/** Selects how chartist agents form technical-trading signals. */
enum class ChartistStrategyMode : std::uint8_t {
    Random = 0,
    Momentum = 1,
    MeanReversion = 2,
    RelativeStrengthIndex = 3,
    Breakout = 4,
};

/**
 * Mean-variance allocation bounds shared by agent strategy classes.
 *
 * The allocation line converts expected excess return and volatility into a
 * risky-asset portfolio weight, then clips that weight to these bounds.
 */
struct AllocationConfig {
    /** Coefficient of relative risk aversion used in mean-variance demand. */
    double riskAversion{3.0};

    /** Lower risky-asset weight; negative values permit short exposure. */
    double minRiskyWeight{0.0};

    /** Upper risky-asset weight used to prevent unrealistic leverage. */
    double maxRiskyWeight{1.0};

    /** Cap on multi-asset portfolio gross exposure sum_j |w_j|. */
    double maxGrossExposure{1.0};
};

/** Parameters controlling fundamentalist mispricing and risk-management rules. */
struct FundamentalistConfig {
    /** Minimum relative mispricing required before a fundamentalist trades. */
    double mispricingThreshold{0.02};

    /** Loss ratio from entry price that triggers forced liquidation. */
    double stopLossThreshold{0.05};

    /** Gain ratio from entry price that triggers profit-taking liquidation. */
    double takeProfitThreshold{0.10};

    /** Number of recent one-period log returns used to estimate realised volatility. */
    std::size_t volatilityWindow{20};

    /** Portfolio allocation rule used after a fundamentalist signal is formed. */
    AllocationConfig allocation{};
};

/** Parameters controlling chartist technical signals and short exposure. */
struct ChartistConfig {
    /** Short moving-average window for momentum comparisons. */
    std::size_t shortWindow{5};

    /** Long moving-average window for trend and mean-reversion comparisons. */
    std::size_t longWindow{20};

    /**
     * Minimum absolute moving-average gap required for momentum signals.
     *
     * The threshold is a deadband around zero: weak short-minus-long moving
     * average differences are treated as economically uninformative noise.
     */
    double momentumSignalThreshold{0.0};

    /**
     * Lookback window for Donchian-style breakout chartists.
     *
     * The latest price is compared with the highest and lowest prices from the
     * previous breakoutWindow observations. Equality is treated as no breakout.
     */
    std::size_t breakoutWindow{20};

    /** Number of recent one-period log returns used to estimate realised volatility. */
    std::size_t volatilityWindow{20};

    /** Maximum absolute short weight available to chartists when shorting is enabled. */
    double maxShortWeight{0.30};

    /**
     * Portfolio allocation rule used after a chartist signal is formed.
     *
     * The lower bound defaults to -0.30 (matching maxShortWeight) so the
     * default configuration permits short exposure; the effective floor at
     * sizing time is max(minRiskyWeight, -maxShortWeight).
     */
    AllocationConfig allocation{3.0, -0.30, 1.0};

    /** Technical signal family assigned to chartist agents. */
    ChartistStrategyMode strategyMode{ChartistStrategyMode::Random};
};

/**
 * Parameters controlling uninformed random-liquidity traders.
 *
 * Noise traders submit orders from stochastic, non-fundamental beliefs rather
 * than from valuation or technical signals. This follows the behavioural
 * finance interpretation that erroneous and unpredictable investor beliefs can
 * create price risk and delay arbitrage correction.
 */
struct NoiseTraderConfig {
    /** Standard deviation of the zero-mean log-belief shock. */
    double beliefShockStdDev{0.02};

    /** Fraction of current mark-to-market wealth committed to one noise order. */
    double orderSizeFraction{0.05};

    /** Maximum absolute short risky weight available to noise traders. */
    double maxShortWeight{0.30};
};

/**
 * Parameters controlling passive buy-and-hold investors.
 *
 * Buy-and-hold agents represent long-horizon passive demand. They accumulate
 * risky-asset exposure until a desired portfolio weight is reached and then
 * hold the position, so the target weight is a modelling assumption rather
 * than a short-term signal sensitivity.
 */
struct BuyAndHoldConfig {
    /** Desired risky-asset share of current mark-to-market wealth. */
    double targetRiskyWeight{0.60};
};

} // namespace abm

#endif // ABM_CONTROL_PARAMETERS_STRATEGY_CONFIG_H
