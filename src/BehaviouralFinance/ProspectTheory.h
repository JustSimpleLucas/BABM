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
 * For example, a value of -2.0 means a loss of two price or wealth units.
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
 * All fields are expressed in return units. referenceLogReturn is the
 * reference-point anchor mapped into return space (for example the log ratio
 * of the average entry price to the current price); scenario returns are
 * measured as gains or losses relative to it, which keeps the valuation
 * invariant to the price or wealth level of the underlying asset.
 */
struct ProspectReturnForecast {
    double expectedReturn{0.0};
    double volatility{0.0};
    double referenceLogReturn{0.0};
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
 * prospectAdjustedReturn converts a return forecast into transparent return
 * scenarios so agent strategies can use the score without duplicating CPT
 * equations.
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

    /** Evaluates the probability weighting function w(p) for a gain/loss domain. */
    [[nodiscard]] double probabilityWeight(double probability, ProspectDomain domain) const;

    /** Calculates the rank-dependent CPT value for explicit relative outcomes. */
    [[nodiscard]] double calculateProspectValue(const std::vector<ProspectOutcome>& outcomes) const;

    /**
     * Converts a return forecast into a prospect-adjusted return.
     *
     * The odd scenario count creates symmetric adverse and favourable shocks
     * around the expected return. Binomial probabilities reproduce the familiar
     * three-scenario weights {0.25, 0.50, 0.25} when scenarioCount is three.
     * Scenario outcomes are gains or losses in return space relative to the
     * reference log return, so identical forecasts produce identical adjusted
     * returns regardless of the asset's price level.
     */
    [[nodiscard]] double prospectAdjustedReturn(const ProspectReturnForecast& forecast) const;

  private:
    [[nodiscard]] double returnScenarioProspectValue(const ProspectReturnForecast& forecast) const;

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
