// Simulation/SimulationRunResult.h

#ifndef SIMULATION_SIMULATION_RUN_RESULT_COMPATIBILITY_H
#define SIMULATION_SIMULATION_RUN_RESULT_COMPATIBILITY_H

/*
 * Transitional include wrapper.
 *
 * New code should include Results/SimulationRunResult.h. This wrapper keeps
 * existing simulation-facing include paths valid while the result DTOs live in
 * the output/results module rather than in the simulation engine module.
 */
#include "Results/SimulationRunResult.h"

#endif // SIMULATION_SIMULATION_RUN_RESULT_COMPATIBILITY_H
