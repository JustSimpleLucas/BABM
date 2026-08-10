// SimulationConfigValidation.h

#ifndef ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_VALIDATION_H
#define ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_VALIDATION_H

#include <vector>

#include "ControlParameters/ConfigDiagnostics.h"
#include "ControlParameters/SimulationConfig.h"

namespace abm {

/**
 * Validates all simulation parameters that affect model feasibility.
 *
 * Validation is intentionally separate from simulation construction so that
 * experiment configuration can be tested independently from the simulation
 * lifecycle.
 *
 * @throws std::invalid_argument on the first constraint that fails.
 */
void validateSimulationConfig(const SimulationConfig& config);

/**
 * Validates the configuration, collecting one diagnostic per failed constraint.
 *
 * Constraints are grouped by the part of the model they govern and each group is
 * evaluated independently, so a single pass can report several unrelated
 * mistakes instead of stopping at the first. Provenance is used to point each
 * diagnostic back at the line that set the offending key.
 *
 * @param config Resolved configuration to check.
 * @param provenance Line each key was assigned on, from RuntimeConfig.
 * @param diagnostics Receives one entry per failure; existing entries are kept.
 */
void collectSimulationConfigDiagnostics(const SimulationConfig& config,
                                        const ConfigProvenance& provenance,
                                        std::vector<ConfigDiagnostic>& diagnostics);

/**
 * Applies deterministic normalisation after validation.
 *
 * These adjustments preserve the intended experiment semantics, for example
 * disabling chartist short exposure when the run forbids short selling.
 */
void normaliseSimulationConfig(SimulationConfig& config);

} // namespace abm

#endif // ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_VALIDATION_H
