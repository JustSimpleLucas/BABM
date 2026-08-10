// SimulationClock.h

#ifndef ABM_SIMULATION_SIMULATION_CLOCK_H
#define ABM_SIMULATION_SIMULATION_CLOCK_H

#include <cstddef>
#include <functional>

namespace abm {

/**
 * Owns simulation-step accounting and progress reporting.
 *
 * The clock deliberately contains no market logic. This keeps the temporal
 * structure of experiments testable independently from behavioural assumptions
 * about agents, social influence, or market clearing.
 */
class SimulationClock {
  public:
    /** Receives completed and total simulation steps after each simulated period. */
    using ProgressCallback =
        std::function<void(std::size_t completedSteps, std::size_t totalSteps)>;

    /** Creates a clock for the configured number of post-warm-up periods. */
    explicit SimulationClock(std::size_t totalSteps);

    /** Returns the configured number of post-warm-up simulation periods. */
    [[nodiscard]] std::size_t totalSteps() const;

    /** Returns the number of periods completed by this clock. */
    [[nodiscard]] std::size_t completedSteps() const;

    /** Records a completed period and invokes the optional progress callback. */
    void markStepCompleted(std::size_t completedStep, const ProgressCallback& progressCallback);

  private:
    std::size_t totalSteps_{0};
    std::size_t completedSteps_{0};
};

} // namespace abm

#endif // ABM_SIMULATION_SIMULATION_CLOCK_H
