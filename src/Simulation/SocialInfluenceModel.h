// SocialInfluenceModel.h

#ifndef ABM_SIMULATION_SOCIAL_INFLUENCE_MODEL_H
#define ABM_SIMULATION_SOCIAL_INFLUENCE_MODEL_H

#include <vector>

#include "Config/SimulationConfig.h"
#include "RandomGenerator/RandomGenerator.h"
#include "Simulation/SimulationState.h"

namespace abm {

/**
 * Owns synthetic social-network construction and opinion updating.
 *
 * Keeping social influence outside the engine makes the herding assumption
 * testable without running the full market-clearing loop.
 */
class SocialInfluenceModel {
  public:
    /** Assigns social profiles and constructs the neighbour graph. */
    void initialize(const SimulationPopulation& population, const SocialInfluenceConfig& config,
                    RandomEngine& random);

    /** Resizes scratch storage for a new run without consuming random draws. */
    void prepareForRun(const SimulationPopulation& population);

    /** Updates each agent's current opinion from neighbours and private noise. */
    void updateOpinions(const SimulationPopulation& population, const SocialInfluenceConfig& config,
                        RandomEngine& random);

  private:
    std::vector<std::vector<SocialNeighbor>> socialNeighbors_;
    std::vector<double> nextOpinionScratch_;
};

} // namespace abm

#endif // ABM_SIMULATION_SOCIAL_INFLUENCE_MODEL_H
