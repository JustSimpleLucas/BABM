// AgentActivationScheduler.h

#ifndef SIMULATION_AGENT_ACTIVATION_SCHEDULER_H
#define SIMULATION_AGENT_ACTIVATION_SCHEDULER_H

#include <cstddef>
#include <vector>

#include "RandomGenerator/RandomGenerator.h"

namespace abm {

/** Inputs for one stochastic agent-activation draw. */
struct AgentActivationRequest {
    std::size_t populationSize{0};
    double activityRate{0.0};
};

/**
 * Produces the within-period order in which agents are allowed to act.
 *
 * Random activation is a modelling assumption: it avoids persistent first-mover
 * priority while preserving exact reproducibility for a fixed seed.
 */
class AgentActivationScheduler {
  public:
    /**
     * Returns active population indices for the current period.
     *
     * A uniform activity draw is consumed for every scheduled agent, even when
     * the activity rate is zero or one. This preserves the stochastic sequence
     * used by downstream order-style draws.
     */
    [[nodiscard]] const std::vector<std::size_t>& schedule(const AgentActivationRequest& request,
                                                           RandomEngine& random);

  private:
    std::vector<std::size_t> activationOrderScratch_;
    std::vector<std::size_t> activeAgentIndices_;
};

} // namespace abm

#endif // SIMULATION_AGENT_ACTIVATION_SCHEDULER_H
