// AgentActivationScheduler.cpp

#include "Simulation/AgentActivationScheduler.h"

#include <numeric>

namespace abm {

const std::vector<std::size_t>&
AgentActivationScheduler::schedule(const AgentActivationRequest& request, RandomEngine& random) {
    if (activationOrderScratch_.size() != request.populationSize) {
        activationOrderScratch_.resize(request.populationSize);
    }
    std::iota(activationOrderScratch_.begin(), activationOrderScratch_.end(), std::size_t{0});

    random.shuffle(activationOrderScratch_.begin(), activationOrderScratch_.end());

    activeAgentIndices_.clear();
    activeAgentIndices_.reserve(request.populationSize);
    for (const std::size_t scheduledAgentIndex : activationOrderScratch_) {
        if (random.generateUniformDist(0.0, 1.0) > request.activityRate) {
            continue;
        }
        activeAgentIndices_.push_back(scheduledAgentIndex);
    }

    return activeAgentIndices_;
}

} // namespace abm
