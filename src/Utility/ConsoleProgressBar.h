// ConsoleProgressBar.h

#ifndef CONSOLE_PROGRESS_BAR_H
#define CONSOLE_PROGRESS_BAR_H

#include <chrono>
#include <cstddef>
#include <iosfwd>
#include <string>

namespace abm {

/**
 * Small terminal progress bar for long simulation runs.
 *
 * The class is deliberately independent from the market model. It reports
 * execution progress only and does not affect stochastic draws, order
 * generation, pricing, or any research-critical state. This separation keeps
 * reproducible simulation results independent of console output behaviour.
 */
class ConsoleProgressBar {
public:
    explicit ConsoleProgressBar(std::ostream& output,
                                std::size_t totalSteps,
                                std::string label = "Simulation progress",
                                std::size_t barWidth = 40);

    /** Redraws the progress bar for the current completed step count. */
    void update(std::size_t completedSteps);

    /** Forces the bar to 100% and moves subsequent output to a fresh line. */
    void finish();

private:
    std::ostream& output_;
    std::size_t totalSteps_;
    std::string label_;
    std::size_t barWidth_;
    std::chrono::steady_clock::time_point startTime_;
    std::size_t lastRenderedPercent_;
    bool finished_;

    void render(std::size_t completedSteps, bool forceRender);
};

} // namespace abm

#endif // CONSOLE_PROGRESS_BAR_H
