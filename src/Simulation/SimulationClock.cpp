// SimulationClock.cpp

#include "Simulation/SimulationClock.h"

namespace abm {

SimulationClock::SimulationClock(std::size_t totalSteps) : totalSteps_(totalSteps) {}

std::size_t SimulationClock::totalSteps() const {
    return totalSteps_;
}

std::size_t SimulationClock::completedSteps() const {
    return completedSteps_;
}

void SimulationClock::markStepCompleted(std::size_t completedStep,
                                        const ProgressCallback& progressCallback) {
    completedSteps_ = completedStep;
    if (progressCallback) {
        progressCallback(completedSteps_, totalSteps_);
    }
}

} // namespace abm
