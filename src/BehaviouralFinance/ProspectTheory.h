// ProspectTheory.h

#ifndef ABM_BEHAVIOURAL_FINANCE_PROSPECT_THEORY_H
#define ABM_BEHAVIOURAL_FINANCE_PROSPECT_THEORY_H

#include <cstddef>
#include <cstdint>
#include <vector>

namespace abm {

/** Gain/loss domain used by the probability weighting function. */
enum class ProspectDomain : std::uint8_t {
    Gain,
    Loss,
};

/**
 * One possible outcome in a Prospect Theory valuation.
 *
 * relativeOutcome is already measured relative to the agent's reference point.
 * In the return-space transform it is a log return, so -0.02 is a loss of two
 * per cent relative to the reference.
 */
struct ProspectOutcome {
    double relativeOutcome{0.0};
    double probability{0.0};
};

/**
 * Research parameters controlling Cumulative Prospect Theory preferences.
 *
 * Defaults follow the empirical baseline commonly used after Tversky and
 * Kahneman (1992): loss aversion above one, concave gains, convex losses, and
 * inverse-S probability weighting. Keeping these values in a named structure
 * makes calibration code harder to misread than a long sequence of doubles.
 */
struct ProspectTheoryParameters {
    double lossAversion{2.25};
    double curvatureForGain{0.88};
    double curvatureForLoss{0.88};
    double probDistortionForGain{0.61};
    double probDistortionForLoss{0.69};
    double referencePoint{100.0};
    std::size_t scenarioCount{3};
};

/**
 * Forecast input evaluated under Prospect Theory.
 *
 * All fields are expressed in one-step log-return units. expectedReturn is the
 * forecast excess return and volatility its standard deviation.
 * referenceLogReturn is the reference-point anchor mapped into return space
 * (for example the log ratio of the average entry price to the current price),
 * so a positive value is a paper loss and a negative value a paper gain;
 * scenario returns are measured as gains or losses relative to it, which keeps
 * the valuation invariant to the price or wealth level of the underlying asset.
 * riskFreeLogReturn, log(1 + r_f), is the sure return of the cash alternative
 * that the asset is compared with.
 */
struct ProspectReturnForecast {
    double expectedReturn{0.0};
    double volatility{0.0};
    double referenceLogReturn{0.0};
    double riskFreeLogReturn{0.0};
};

/**
 * Cumulative Prospect Theory preference model for behavioural trading decisions.
 *
 * The class implements the rank-dependent Cumulative Prospect Theory score
 * used in the ABM:
 *
 * Formula note:
 * V = sum_s pi_s * v(x_s)
 *
 * where x_s is the gain or loss relative to a reference point and pi_s is the
 * cumulative decision weight implied by rank-dependent probability weighting.
 * Gains are ranked from best to worst and losses from worst to best, so the
 * valuation can overweight distribution tails in the way proposed by
 * Tversky and Kahneman's Cumulative Prospect Theory. The helper
 * prospectAdjustedReturn turns a return forecast into a moment-matched
 * scenario ladder, values holding the asset against holding cash, and reports
 * the difference as a certainty-equivalent premium in log-return units, so
 * agent strategies can use it without duplicating CPT equations.
 */
class ProspectTheory {
  public:
    /** Constructs the empirical baseline commonly used in CPT studies. */
    ProspectTheory();

    /** Constructs Cumulative Prospect Theory preferences with explicit research parameters. */
    explicit ProspectTheory(const ProspectTheoryParameters& parameters);

    /** Returns the configured loss-aversion parameter. */
    [[nodiscard]] double lossAversion() const;

    /** Returns the configured gain curvature. */
    [[nodiscard]] double curvatureForGain() const;

    /** Returns the configured loss curvature. */
    [[nodiscard]] double curvatureForLoss() const;

    /** Returns the configured probability distortion for gains. */
    [[nodiscard]] double probDistortionForGain() const;

    /** Returns the configured probability distortion for losses. */
    [[nodiscard]] double probDistortionForLoss() const;

    /** Returns the configured reference price or wealth scale. */
    [[nodiscard]] double referencePoint() const;

    /** Returns the odd number of return scenarios used in CPT valuation. */
    [[nodiscard]] std::size_t scenarioCount() const;

    /** Evaluates the CPT value function v(x). */
    [[nodiscard]] double valueFunction(double relativeOutcome) const;

    /**
     * Evaluates the inverse value function v^-1(y).
     *
     * Returns the sure gain or loss whose value equals the argument. Applied to
     * the value of a prospect, it gives the prospect's certainty equivalent
     * relative to the reference point.
     */
    [[nodiscard]] double inverseValueFunction(double value) const;

    /** Evaluates the probability weighting function w(p) for a gain/loss domain. */
    [[nodiscard]] double probabilityWeight(double probability, ProspectDomain domain) const;

    /** Calculates the rank-dependent CPT value for explicit relative outcomes. */
    [[nodiscard]] double calculateProspectValue(const std::vector<ProspectOutcome>& outcomes) const;

    /**
     * Builds the subjective one-step return scenarios of holding the asset.
     *
     * The odd scenario count creates symmetric adverse and favourable shocks
     * around the risk-free plus expected return. The binomial ladder is moment
     * matched: its mean is riskFreeLogReturn + expectedReturn and its variance
     * is volatility^2 for every scenario count, so the count controls only the
     * resolution of the tails. Outcomes are returned as gains or losses
     * relative to the reference log return, with their probabilities.
     */
    [[nodiscard]] std::vector<ProspectOutcome>
    returnScenarios(const ProspectReturnForecast& forecast) const;

    /**
     * Converts a return forecast into a prospect-adjusted excess return.
     *
     * The result is the certainty-equivalent premium of holding the asset for
     * one step over holding cash, in log-return units:
     * v^-1(V_hold) + referenceLogReturn - riskFreeLogReturn. It is positive
     * exactly when CPT prefers holding to selling, equals the forecast when
     * volatility is zero, and is identical for identical forecasts whatever
     * the asset's price level.
     */
    [[nodiscard]] double prospectAdjustedReturn(const ProspectReturnForecast& forecast) const;

  private:
    double lossAversion_;
    double curvatureForGain_;
    double curvatureForLoss_;
    double probDistortionForGain_;
    double probDistortionForLoss_;
    double referencePoint_;
    std::size_t scenarioCount_;
};

} // namespace abm

#endif // ABM_BEHAVIOURAL_FINANCE_PROSPECT_THEORY_H
