// AssetAllocationLine.cpp
#include "AgentStrategy/AssetAllocationLine.h"
#include "AgentStrategy/MeanVarianceUtility.h"
#include "Utility/NumericValidation.h"

#include <stdexcept>

namespace abm {
namespace {
constexpr double kDefaultRiskAversion = 3.0;
constexpr double kDefaultMinRiskyWeight = 0.0;
constexpr double kDefaultMaxRiskyWeight = 1.0;
} // namespace

AssetAllocationLine::AssetAllocationLine()
    : riskAversion_(kDefaultRiskAversion),
      minRiskyWeight_(kDefaultMinRiskyWeight),
      maxRiskyWeight_(kDefaultMaxRiskyWeight) {}

AssetAllocationLine::AssetAllocationLine(double riskAversion,
                                         double minRiskyWeight,
                                         double maxRiskyWeight)
    : riskAversion_(kDefaultRiskAversion),
      minRiskyWeight_(kDefaultMinRiskyWeight),
      maxRiskyWeight_(kDefaultMaxRiskyWeight) {
    setRiskyAversion(riskAversion);
    setRiskyWeightBounds(minRiskyWeight, maxRiskyWeight);
}

void AssetAllocationLine::setRiskyAversion(double aversion) {
    requireStrictlyPositive(aversion, "Risk aversion");
    riskAversion_ = aversion;
}

void AssetAllocationLine::setRiskyWeightBounds(double minRiskyWeight, double maxRiskyWeight) {
    requireFinite(minRiskyWeight, "Minimum risky weight");
    requireFinite(maxRiskyWeight, "Maximum risky weight");
    if (minRiskyWeight > maxRiskyWeight) {
        throw std::invalid_argument("Minimum risky weight cannot exceed maximum risky weight.");
    }
    minRiskyWeight_ = minRiskyWeight;
    maxRiskyWeight_ = maxRiskyWeight;
}

double AssetAllocationLine::riskAversion() const {
    return riskAversion_;
}

double AssetAllocationLine::minRiskyWeight() const {
    return minRiskyWeight_;
}

double AssetAllocationLine::maxRiskyWeight() const {
    return maxRiskyWeight_;
}

double AssetAllocationLine::optimalRiskyWeight(double mu, double rf, double sigma) const {
    return abm::optimalRiskyWeight(
        MeanVarianceInputs{mu, rf, sigma, riskAversion_},
        minRiskyWeight_,
        maxRiskyWeight_);
}


} // namespace abm
