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

double ProspectTheory::inverseValueFunction(double value) const {
    requireFinite(value, "Prospect value");

    /*
     * Formula note:
     * v^-1(y) = y^(1 / alpha_gain) for y >= 0,
     * v^-1(y) = -(-y / lambda)^(1 / alpha_loss) for y < 0.
     *
     * The inverse maps a prospect value back to the sure gain or loss that the
     * agent values equally: the certainty equivalent through which Tversky and
     * Kahneman (1992) measured these preferences. It is what puts CPT output
     * back into the return units that the mean-variance allocation and the
     * valuation quotes require; a raw value is in value units, which bend small
     * returns upwards and scale by c^alpha rather than c with the returns.
     */
    if (value >= 0.0) {
        return std::pow(value, 1.0 / curvatureForGain_);
    }

    return -std::pow(-value / lossAversion_, 1.0 / curvatureForLoss_);
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

std::vector<ProspectOutcome>
ProspectTheory::returnScenarios(const ProspectReturnForecast& forecast) const {
    requireFinite(forecast.expectedReturn, "Expected return");
    requireNonNegative(forecast.volatility, "Volatility");
    requireFinite(forecast.referenceLogReturn, "Reference log return");
    requireFinite(forecast.riskFreeLogReturn, "Risk-free log return");

    const double boundedExpected =
        std::clamp(forecast.expectedReturn, -kMaxScenarioReturn, kMaxScenarioReturn);
    const double boundedVolatility = std::clamp(forecast.volatility, 0.0, kMaxScenarioReturn);

    // The ladder discretises the agent's subjective one-step return
    // distribution N(r_f + E[r], sigma^2). With n - 1 = 2H binomial steps of
    // size Delta, Var(s - H) = H / 2, so Delta = 2 sigma / sqrt(n - 1) gives
    // variance sigma^2 for every odd scenario count: the variance-matching rule
    // of the Cox, Ross and Rubinstein (1979) binomial tree. The count therefore
    // controls only how finely the tails are resolved (de Moivre-Laplace
    // convergence), never the risk the agent perceives; an unscaled step would
    // let a numerical setting act as a preference parameter. Three scenarios
    // keep the weights {0.25, 0.50, 0.25}, placed at +/- sqrt(2) sigma.
    //
    // Formula note:
    // Delta = 2 sigma / sqrt(n - 1),
    // R_s = clamp(r_f + E[r] + (s - H) * Delta, -0.95, 0.95),
    // x_s = R_s - r_ref,
    // p_s = C(n - 1, s) * 0.5^(n - 1).
    //
    // Outcomes stay in return space relative to the reference log return, so
    // the CPT valuation is invariant to price and wealth levels.
    const std::size_t binomialOrder = scenarioCount_ - 1;
    const int halfWidth = static_cast<int>(binomialOrder / 2);
    const double scenarioStep =
        2.0 * boundedVolatility / std::sqrt(static_cast<double>(binomialOrder));

    std::vector<ProspectOutcome> outcomes;
    outcomes.reserve(scenarioCount_);

    double scenarioProbability = std::pow(0.5, static_cast<double>(binomialOrder));
    for (std::size_t scenarioIndex = 0; scenarioIndex <= binomialOrder; ++scenarioIndex) {
        const int shockMultiplier = static_cast<int>(scenarioIndex) - halfWidth;
        const double scenarioReturn =
            std::clamp(forecast.riskFreeLogReturn + boundedExpected +
                           (static_cast<double>(shockMultiplier) * scenarioStep),
                       -kMaxScenarioReturn, kMaxScenarioReturn);

        outcomes.push_back({scenarioReturn - forecast.referenceLogReturn, scenarioProbability});

        // Recurrence for the next binomial coefficient:
        // C(n, s + 1) = C(n, s) * (n - s) / (s + 1).
        if (scenarioIndex < binomialOrder) {
            scenarioProbability *= static_cast<double>(binomialOrder - scenarioIndex) /
                                   static_cast<double>(scenarioIndex + 1);
        }
    }
    return outcomes;
}

double ProspectTheory::prospectAdjustedReturn(const ProspectReturnForecast& forecast) const {
    // The agent chooses between holding the asset for one more step (the
    // scenario ladder) and holding cash, whose sure outcome r_f - r_ref
    // realises today's paper gain or loss. CPT compares the two options by
    // value; expressing both as certainty equivalents measured from today's
    // price keeps the comparison in log-return units.
    //
    // Formula note:
    // CE_hold = r_ref + v^-1(V_hold),
    // CE_cash = r_ref + v^-1(v(r_f - r_ref)) = r_f,
    // premium = CE_hold - CE_cash = v^-1(V_hold) + r_ref - r_f.
    //
    // Because v is strictly increasing, the premium is positive exactly when
    // holding beats selling under CPT. Comparing against cash rather than
    // against zero is what lets reference dependence act on the choice: with a
    // paper loss the convex loss domain favours holding, and with a paper gain
    // the concave gain domain favours realising it (Kahneman and Tversky, 1979;
    // Shefrin and Statman, 1985). A riskless forecast passes through unchanged,
    // so CPT alters how agents treat risk, not how they read a sure return.
    const double holdValue = calculateProspectValue(returnScenarios(forecast));
    return inverseValueFunction(holdValue) + forecast.referenceLogReturn -
           forecast.riskFreeLogReturn;
}

} // namespace abm
