// ProspectPreferenceSampler.cpp

#include "BehaviouralFinance/ProspectPreferenceSampler.h"

#include <algorithm>
#include <cmath>

namespace abm {
namespace {
constexpr int kMaxPreferenceDrawAttempts = 64;
constexpr double kMinProspectPreference = 1e-6;
constexpr double kMaxLossAversionDraw = 10.0;
constexpr double kMaxCurvatureDraw = 1.5;

struct TruncatedNormalDraw {
    double mean{0.0};
    double standardDeviation{0.0};
    double upperBound{kMaxCurvatureDraw};
};

double drawStrictlyPositiveTruncatedNormal(RandomEngine& random, const TruncatedNormalDraw& draw) {
    if (draw.standardDeviation <= 0.0) {
        return std::clamp(draw.mean, kMinProspectPreference, draw.upperBound);
    }

    for (int attempt = 0; attempt < kMaxPreferenceDrawAttempts; ++attempt) {
        const double candidate = random.generateNormalDist(draw.mean, draw.standardDeviation);
        if (std::isfinite(candidate) && candidate >= kMinProspectPreference &&
            candidate <= draw.upperBound) {
            return candidate;
        }
    }

    // Falling back to the clipped mean keeps runs deterministic even under
    // extreme calibration settings that make rejection sampling inefficient.
    return std::clamp(draw.mean, kMinProspectPreference, draw.upperBound);
}
} // namespace

ProspectTheory drawProspectPreferences(const ControlParameters& control, RandomEngine& random) {
    if (!control.prospectTheoryEnabled) {
        return {};
    }

    ProspectTheoryParameters parameters{};
    parameters.lossAversion = control.lossAversion;
    parameters.curvatureForGain = control.curvatureForGain;
    parameters.curvatureForLoss = control.curvatureForLoss;
    parameters.probDistortionForGain = control.probDistortionForGain;
    parameters.probDistortionForLoss = control.probDistortionForLoss;
    parameters.referencePoint = control.referencePoint;
    parameters.scenarioCount = control.prospectScenarioCount;

    if (!control.prospectParameterHeterogeneityEnabled) {
        const ProspectTheory preferences(parameters);
        return preferences;
    }

    parameters.lossAversion = drawStrictlyPositiveTruncatedNormal(
        random, TruncatedNormalDraw{control.lossAversion, control.lossAversionStdDev,
                                    kMaxLossAversionDraw});
    parameters.curvatureForGain = drawStrictlyPositiveTruncatedNormal(
        random, TruncatedNormalDraw{control.curvatureForGain, control.curvatureForGainStdDev,
                                    kMaxCurvatureDraw});
    parameters.curvatureForLoss = drawStrictlyPositiveTruncatedNormal(
        random, TruncatedNormalDraw{control.curvatureForLoss, control.curvatureForLossStdDev,
                                    kMaxCurvatureDraw});
    const double probabilityDistortion = random.generateUniformDist(
        control.probabilityDistortionMin, control.probabilityDistortionMax);

    // A single gamma_i is used for both gain and loss domains to match the
    // heterogeneous specification in the experiment configuration.
    parameters.probDistortionForGain = probabilityDistortion;
    parameters.probDistortionForLoss = probabilityDistortion;

    const ProspectTheory preferences(parameters);
    return preferences;
}

} // namespace abm
