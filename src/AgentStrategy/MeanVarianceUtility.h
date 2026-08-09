// MeanVarianceUtility.h
#ifndef MEAN_VARIANCE_UTILITY_H
#define MEAN_VARIANCE_UTILITY_H

namespace abm {

/**
 * Inputs to the one-period mean-variance portfolio rule.
 *
 * The rule is intentionally explicit because risk aversion and volatility are
 * research-critical assumptions in behavioural market simulations.
 */
struct MeanVarianceInputs {
    /** Expected return on the risky asset over one simulation step. */
    double expectedRiskyReturn;

    /** Risk-free return over one simulation step. */
    double riskFreeRate;

    /** Realised or forecast risky-asset volatility over one simulation step. */
    double volatility;

    /** Positive coefficient controlling demand sensitivity to risk. */
    double riskAversion;
};

/**
 * Computes the clipped optimal risky-asset weight.
 *
 * Formula note:
 * w* = (mu - r_f) / (rho * sigma^2), then clipped to the configured lower and
 * upper portfolio bounds.
 *
 * @param inputs Expected return, risk-free return, volatility, and risk aversion.
 * @param minRiskyWeight Lower portfolio bound; can be negative for shorting.
 * @param maxRiskyWeight Upper portfolio bound.
 * @return Risky-asset portfolio weight after applying bounds.
 */
[[nodiscard]] double optimalRiskyWeight(const MeanVarianceInputs& inputs,
                                        double minRiskyWeight,
                                        double maxRiskyWeight);

} // namespace abm

#endif // MEAN_VARIANCE_UTILITY_H
