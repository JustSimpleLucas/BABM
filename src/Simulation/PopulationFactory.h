// PopulationFactory.h

#ifndef ABM_SIMULATION_POPULATION_FACTORY_H
#define ABM_SIMULATION_POPULATION_FACTORY_H

#include "ControlParameters/SimulationConfig.h"
#include "RandomGenerator/RandomGenerator.h"
#include "Simulation/SimulationState.h"

namespace abm {

/**
 * Builds the heterogeneous agent population for a simulation run.
 *
 * Agent construction is separated from the engine so strategy composition,
 * prospect-preference sampling, and stable ID assignment can be tested as
 * modelling assumptions rather than hidden controller side effects.
 */
class PopulationFactory {
  public:
    /** Creates agents, initial strategies, and the ID lookup table. */
    [[nodiscard]] static SimulationPopulation createPopulation(const SimulationConfig& config,
                                                               RandomEngine& random);

    /** Clears run-local trade statistics and opinion state before a fresh run. */
    static void resetRunState(SimulationPopulation& population);
};

} // namespace abm

#endif // ABM_SIMULATION_POPULATION_FACTORY_H
