// MeanVarianceUtility.cpp
#include "AgentStrategy/MeanVarianceUtility.h"
#include "Utility/NumericValidation.h"

#include <algorithm>
#include <stdexcept>

namespace abm {
namespace {
void validateInputs(const MeanVarianceInputs& inputs) {
    requireFinite(inputs.expectedRiskyReturn, "Expected risky return");
    requireFinite(inputs.riskFreeRate, "Risk-free rate");
    requireStrictlyPositive(inputs.volatility, "Risky asset volatility");
    requireStrictlyPositive(inputs.riskAversion, "Risk aversion");
}
} // namespace

double optimalRiskyWeight(const MeanVarianceInputs& inputs,
                          double minRiskyWeight,
                          double maxRiskyWeight) {
    validateInputs(inputs);
    requireFinite(minRiskyWeight, "Minimum risky weight");
    requireFinite(maxRiskyWeight, "Maximum risky weight");

    if (minRiskyWeight > maxRiskyWeight) {
        throw std::invalid_argument("Minimum risky weight cannot exceed maximum risky weight.");
    }

    /*
     * Formula note:
     * w* = (mu - r_f) / (rho * sigma^2).
     *
     * The numerator is expected excess return; the denominator scales demand
     * down as risk aversion or realised volatility increases.
     */
    const double unconstrainedWeight =
        (inputs.expectedRiskyReturn - inputs.riskFreeRate) /
        (inputs.riskAversion * inputs.volatility * inputs.volatility);
    return std::clamp(unconstrainedWeight, minRiskyWeight, maxRiskyWeight);
}

} // namespace abm
