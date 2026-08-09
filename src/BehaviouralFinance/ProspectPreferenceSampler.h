// ProspectPreferenceSampler.h

#ifndef PROSPECT_PREFERENCE_SAMPLER_H
#define PROSPECT_PREFERENCE_SAMPLER_H

#include "BehaviouralFinance/ProspectTheory.h"
#include "ControlParameters/SimulationConfig.h"
#include "RandomGenerator/RandomGenerator.h"

namespace abm {

/**
 * Draws agent-level Cumulative Prospect Theory preferences from run controls.
 *
 * Homogeneous runs return the configured CPT parameters for every agent.
 * Heterogeneous runs draw bounded preferences from deterministic random
 * streams, allowing agent diversity while preserving seed reproducibility.
 */
[[nodiscard]] ProspectTheory drawProspectPreferences(const ControlParameters& control,
                                                     RandomEngine& random);

} // namespace abm

#endif // PROSPECT_PREFERENCE_SAMPLER_H
