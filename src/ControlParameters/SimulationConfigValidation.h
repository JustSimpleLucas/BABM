// SimulationConfigValidation.h

#ifndef SIMULATION_CONFIG_VALIDATION_H
#define SIMULATION_CONFIG_VALIDATION_H

#include "ControlParameters/SimulationConfig.h"

namespace abm {

/**
 * Validates all simulation parameters that affect model feasibility.
 *
 * Validation is intentionally separate from simulation construction so that
 * experiment configuration can be tested independently from the simulation
 * lifecycle.
 */
void validateSimulationConfig(const SimulationConfig& config);

/**
 * Applies deterministic normalisation after validation.
 *
 * These adjustments preserve the intended experiment semantics, for example
 * disabling chartist short exposure when the run forbids short selling.
 */
void normaliseSimulationConfig(SimulationConfig& config);

} // namespace abm

#endif // SIMULATION_CONFIG_VALIDATION_H
