// ProspectTheory.cpp

#include "BehaviouralFinance/ProspectTheory.h"
#include "Utility/NumericValidation.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace abm {
namespace {
constexpr double kProbabilityTolerance = 1e-8;
constexpr double kMaxScenarioReturn = 0.95;

bool gainOutcomeRanksBefore(const ProspectOutcome& lhs, const ProspectOutcome& rhs) {
    return lhs.relativeOutcome > rhs.relativeOutcome;
}

bool lossOutcomeRanksBefore(const ProspectOutcome& lhs, const ProspectOutcome& rhs) {
    return lhs.relativeOutcome < rhs.relativeOutcome;
}

void requireValidScenarioCount(std::size_t scenarioCount) {
    if (scenarioCount < 3 || scenarioCount % 2 == 0) {
        throw std::invalid_argument(
            "Prospect scenario count must be an odd integer greater than or equal to 3.");
    }
}
} // namespace

ProspectTheory::ProspectTheory() : ProspectTheory(ProspectTheoryParameters{}) {}

ProspectTheory::ProspectTheory(const ProspectTheoryParameters& parameters)
    : lossAversion_(parameters.lossAversion), curvatureForGain_(parameters.curvatureForGain),
      curvatureForLoss_(parameters.curvatureForLoss),
      probDistortionForGain_(parameters.probDistortionForGain),
      probDistortionForLoss_(parameters.probDistortionForLoss),
      referencePoint_(parameters.referencePoint), scenarioCount_(parameters.scenarioCount) {
    requireStrictlyPositive(parameters.lossAversion, "Loss aversion");
    requireStrictlyPositive(parameters.curvatureForGain, "Curvature for gain");
    requireStrictlyPositive(parameters.curvatureForLoss, "Curvature for loss");
    requireStrictlyPositive(parameters.probDistortionForGain, "Probability distortion for gain");
    requireStrictlyPositive(parameters.probDistortionForLoss, "Probability distortion for loss");
    requireStrictlyPositive(parameters.referencePoint, "Reference point");
    requireValidScenarioCount(parameters.scenarioCount);
}

double ProspectTheory::lossAversion() const {
    return lossAversion_;
}

double ProspectTheory::curvatureForGain() const {
    return curvatureForGain_;
}

double ProspectTheory::curvatureForLoss() const {
    return curvatureForLoss_;
}

double ProspectTheory::probDistortionForGain() const {
    return probDistortionForGain_;
}

double ProspectTheory::probDistortionForLoss() const {
    return probDistortionForLoss_;
}

double ProspectTheory::referencePoint() const {
    return referencePoint_;
}

std::size_t ProspectTheory::scenarioCount() const {
    return scenarioCount_;
}

double ProspectTheory::valueFunction(double relativeOutcome) const {
    requireFinite(relativeOutcome, "Relative outcome");

    /*
     * Formula note:
     * v(x) = x^alpha_gain for x >= 0,
     * v(x) = -lambda * (-x)^alpha_loss for x < 0.
     *
     * This is the Tversky-Kahneman CPT value function: gains are concave,
     * losses are convex, and lambda > 1 gives losses greater psychological
     * impact than equally sized gains.
     */
    if (relativeOutcome >= 0.0) {
        return std::pow(relativeOutcome, curvatureForGain_);
    }

    return -lossAversion_ * std::pow(-relativeOutcome, curvatureForLoss_);
}

double ProspectTheory::probabilityWeight(double probability, ProspectDomain domain) const {
    requireProbability(probability, "Scenario probability");
    if (probability <= 0.0) {
        return 0.0;
    }
    if (probability >= 1.0) {
        return 1.0;
    }

    const double gamma =
        domain == ProspectDomain::Gain ? probDistortionForGain_ : probDistortionForLoss_;
    const double weightedProbability = std::pow(probability, gamma);
    const double weightedComplement = std::pow(1.0 - probability, gamma);
    const double denominator = std::pow(weightedProbability + weightedComplement, 1.0 / gamma);

    /*
     * Formula note:
     * w(p) = p^gamma / (p^gamma + (1 - p)^gamma)^(1 / gamma).
     *
     * Separate gamma parameters allow the calibration to capture different
     * probability distortions for gains and losses.
     */
    return weightedProbability / denominator;
}

double ProspectTheory::calculateProspectValue(const std::vector<ProspectOutcome>& outcomes) const {
    if (outcomes.empty()) {
        throw std::invalid_argument("At least one prospect outcome is required.");
    }

    double totalProbability = 0.0;
    std::vector<ProspectOutcome> gainOutcomes;
    std::vector<ProspectOutcome> lossOutcomes;
    for (const ProspectOutcome& outcome : outcomes) {
        requireFinite(outcome.relativeOutcome, "Relative outcome");
        requireProbability(outcome.probability, "Scenario probability");

        totalProbability += outcome.probability;
        if (outcome.relativeOutcome >= 0.0) {
            gainOutcomes.push_back(outcome);
        } else {
            lossOutcomes.push_back(outcome);
        }
    }

    if (std::abs(totalProbability - 1.0) > kProbabilityTolerance) {
        throw std::invalid_argument("Prospect outcome probabilities must sum to one.");
    }

    std::sort(gainOutcomes.begin(), gainOutcomes.end(), gainOutcomeRanksBefore);
    std::sort(lossOutcomes.begin(), lossOutcomes.end(), lossOutcomeRanksBefore);

    double prospectValue = 0.0;

    // Cumulative Prospect Theory applies rank-dependent decision weights. For
    // gains, the cumulative probability moves from the best payoff downwards;
    // for losses, it moves from the worst payoff upwards. This makes tail gains
    // and tail losses visible to probability weighting instead of weighting
    // every scenario independently.
    //
    // Formula note:
    // pi_s^gain = w(P(X >= x_s)) - w(P(X > x_s)).
    // pi_s^loss = w(P(X <= x_s)) - w(P(X < x_s)).
    double cumulativeGainProbability = 0.0;
    for (const ProspectOutcome& outcome : gainOutcomes) {
        const double nextCumulativeProbability = cumulativeGainProbability + outcome.probability;
        const double decisionWeight =
            probabilityWeight(nextCumulativeProbability, ProspectDomain::Gain) -
            probabilityWeight(cumulativeGainProbability, ProspectDomain::Gain);

        prospectValue += decisionWeight * valueFunction(outcome.relativeOutcome);
        cumulativeGainProbability = nextCumulativeProbability;
    }

    double cumulativeLossProbability = 0.0;
    for (const ProspectOutcome& outcome : lossOutcomes) {
        const double nextCumulativeProbability = cumulativeLossProbability + outcome.probability;
        const double decisionWeight =
            probabilityWeight(nextCumulativeProbability, ProspectDomain::Loss) -
            probabilityWeight(cumulativeLossProbability, ProspectDomain::Loss);

        prospectValue += decisionWeight * valueFunction(outcome.relativeOutcome);
        cumulativeLossProbability = nextCumulativeProbability;
    }

    return prospectValue;
}

double ProspectTheory::prospectAdjustedReturn(const ProspectReturnForecast& forecast) const {
    return returnScenarioProspectValue(forecast);
}

double ProspectTheory::returnScenarioProspectValue(const ProspectReturnForecast& forecast) const {
    requireFinite(forecast.expectedReturn, "Expected return");
    requireNonNegative(forecast.volatility, "Volatility");
    requireFinite(forecast.referenceLogReturn, "Reference log return");

    const double boundedExpected =
        std::clamp(forecast.expectedReturn, -kMaxScenarioReturn, kMaxScenarioReturn);
    const double boundedVolatility = std::clamp(forecast.volatility, 0.0, kMaxScenarioReturn);

    // The odd scenario count creates a central forecast with symmetric adverse
    // and favourable shocks. Binomial probabilities keep the original
    // three-scenario weights {0.25, 0.50, 0.25} when scenarioCount_ is 3, while
    // allowing richer distributions such as five or seven scenarios.
    //
    // Formula note:
    // r_s = clamp(E[r] + k_s * sigma, -0.95, 0.95),
    // x_s = r_s - r_ref,
    // p_s = C(n, s) * 0.5^n, where n = scenarioCount - 1.
    //
    // Outcomes stay in return space relative to the reference log return, so
    // the CPT valuation is invariant to price and wealth levels.
    const std::size_t binomialOrder = scenarioCount_ - 1;
    const int halfWidth = static_cast<int>(binomialOrder / 2);

    std::vector<ProspectOutcome> outcomes;
    outcomes.reserve(scenarioCount_);

    double scenarioProbability = std::pow(0.5, static_cast<double>(binomialOrder));
    for (std::size_t scenarioIndex = 0; scenarioIndex <= binomialOrder; ++scenarioIndex) {
        const int shockMultiplier = static_cast<int>(scenarioIndex) - halfWidth;
        const double scenarioReturn =
            std::clamp(boundedExpected + (static_cast<double>(shockMultiplier) * boundedVolatility),
                       -kMaxScenarioReturn, kMaxScenarioReturn);

        outcomes.push_back({scenarioReturn - forecast.referenceLogReturn, scenarioProbability});

        // Recurrence for the next binomial coefficient:
        // C(n, s + 1) = C(n, s) * (n - s) / (s + 1).
        if (scenarioIndex < binomialOrder) {
            scenarioProbability *= static_cast<double>(binomialOrder - scenarioIndex) /
                                   static_cast<double>(scenarioIndex + 1);
        }
    }
    return calculateProspectValue(outcomes);
}

} // namespace abm
