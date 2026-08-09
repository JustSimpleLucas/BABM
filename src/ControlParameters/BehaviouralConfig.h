// BehaviouralConfig.h

#ifndef CONTROL_PARAMETERS_BEHAVIOURAL_CONFIG_H
#define CONTROL_PARAMETERS_BEHAVIOURAL_CONFIG_H

#include <cstddef>
#include <cstdint>

namespace abm {

/**
 * Selects the anchor used when agents evaluate gains and losses under CPT.
 *
 * The configured reference point preserves the original fixed-anchor model,
 * while the other modes let each agent carry a personal reference state. This
 * makes the behavioural assumption explicit for reproducible experiments.
 */
enum class ProspectReferencePointMode : std::uint8_t {
    Configured = 0,
    AveragePurchasePrice = 1,
    RecentPeakWealth = 2,
    MovingAveragePrice = 3,
    InitialWealth = 4,
};

/**
 * Behavioural-finance parameters used by Cumulative Prospect Theory preferences.
 *
 * These values should be treated as research assumptions. Keeping them in a
 * central configuration object makes calibration experiments reproducible and
 * allows thesis documentation to point to one source of truth.
 */
struct ControlParameters {
    /** Enables CPT valuation when true; false restores baseline expected returns. */
    bool prospectTheoryEnabled{true};

    /** Fraction of all agents assigned to use CPT valuation when the global switch is enabled. */
    double prospectTheoryAgentFraction{1.0};

    /** Enables agent-specific CPT parameters when true. */
    bool prospectParameterHeterogeneityEnabled{false};

    /** Relative penalty assigned to losses compared with gains. */
    double lossAversion{2.25};

    /** Cross-agent standard deviation for loss aversion when heterogeneity is enabled. */
    double lossAversionStdDev{0.25};

    /** Value-function curvature for positive deviations from the reference point. */
    double curvatureForGain{0.88};

    /** Cross-agent standard deviation for gain curvature when heterogeneity is enabled. */
    double curvatureForGainStdDev{0.05};

    /** Value-function curvature for negative deviations from the reference point. */
    double curvatureForLoss{0.88};

    /** Cross-agent standard deviation for loss curvature when heterogeneity is enabled. */
    double curvatureForLossStdDev{0.05};

    /** Probability weighting parameter for gain-domain outcomes. */
    double probDistortionForGain{0.61};

    /** Probability weighting parameter for loss-domain outcomes. */
    double probDistortionForLoss{0.69};

    /** Lower bound for heterogeneous probability weighting gamma. */
    double probabilityDistortionMin{0.65};

    /** Upper bound for heterogeneous probability weighting gamma. */
    double probabilityDistortionMax{0.85};

    /** Baseline wealth or price level used when evaluating gains and losses. */
    double referencePoint{100.0};

    /** Rule used to resolve the agent-specific CPT reference point. */
    ProspectReferencePointMode referencePointMode{ProspectReferencePointMode::AveragePurchasePrice};

    /** Lookback window used when referencePointMode is MovingAveragePrice. */
    std::size_t referenceMovingAverageWindow{20};

    /** Odd number of subjective return scenarios used in CPT valuation. */
    std::size_t prospectScenarioCount{3};
};

} // namespace abm

#endif // CONTROL_PARAMETERS_BEHAVIOURAL_CONFIG_H
