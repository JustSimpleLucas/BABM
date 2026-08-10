// ConsoleProgressBar.h

#ifndef ABM_UTILITY_CONSOLE_PROGRESS_BAR_H
#define ABM_UTILITY_CONSOLE_PROGRESS_BAR_H

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
 *
 * Callers are expected to pass a diagnostic stream rather than standard output.
 * Keeping the bar off stdout means a redirected run captures only the summary
 * and artefact paths, with no carriage-return frames interleaved through them.
 */
class ConsoleProgressBar {
  public:
    explicit ConsoleProgressBar(std::ostream& output, std::size_t totalSteps,
                                std::string label = "Simulation progress",
                                std::size_t barWidth = 40, bool enabled = true);

    /** Redraws the progress bar for the current completed step count. */
    void update(std::size_t completedSteps);

    /** Forces the bar to 100% and moves subsequent output to a fresh line. */
    void finish();

  private:
    std::ostream& output_;
    std::size_t totalSteps_;
    std::string label_;
    std::size_t barWidth_;
    bool enabled_;
    std::chrono::steady_clock::time_point startTime_;
    std::size_t lastRenderedPercent_;
    bool finished_;

    void render(std::size_t completedSteps, bool forceRender);
};

} // namespace abm

#endif // ABM_UTILITY_CONSOLE_PROGRESS_BAR_H
