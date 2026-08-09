// ConsoleProgressBar.cpp

#include "Utility/ConsoleProgressBar.h"

#include <algorithm>
#include <chrono>
#include <iomanip>
#include <ostream>
#include <utility>

namespace abm {

ConsoleProgressBar::ConsoleProgressBar(std::ostream& output,
                                       std::size_t totalSteps,
                                       std::string label,
                                       std::size_t barWidth)
    : output_(output),
      totalSteps_(std::max<std::size_t>(1, totalSteps)),
      label_(std::move(label)),
      barWidth_(std::max<std::size_t>(10, barWidth)),
      startTime_(std::chrono::steady_clock::now()),
      lastRenderedPercent_(static_cast<std::size_t>(-1)),
      finished_(false) {}

void ConsoleProgressBar::update(std::size_t completedSteps) {
    render(completedSteps, false);
}

void ConsoleProgressBar::finish() {
    if (finished_) {
        return;
    }

    if (lastRenderedPercent_ != 100) {
        render(totalSteps_, true);
    }
    output_ << '\n';
    output_.flush();
    finished_ = true;
}

void ConsoleProgressBar::render(std::size_t completedSteps, bool forceRender) {
    completedSteps = std::min(completedSteps, totalSteps_);
    const double progress =
        static_cast<double>(completedSteps) / static_cast<double>(totalSteps_);
    const auto percent = static_cast<std::size_t>(progress * 100.0);

    // Redrawing only when the visible percentage changes avoids excessive
    // terminal I/O during large Monte Carlo or sensitivity-analysis runs.
    if (!forceRender && percent == lastRenderedPercent_) {
        return;
    }
    lastRenderedPercent_ = percent;

    const std::size_t filledWidth =
        std::min(barWidth_, static_cast<std::size_t>(progress * static_cast<double>(barWidth_)));
    const auto elapsedSeconds =
        std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - startTime_)
            .count();

    output_ << '\r' << label_ << " [";
    for (std::size_t i = 0; i < barWidth_; ++i) {
        output_ << (i < filledWidth ? '#' : '.');
    }
    output_ << "] "
            << std::setw(3) << percent << "% "
            << '(' << completedSteps << '/' << totalSteps_ << " steps, "
            << elapsedSeconds << "s)" << std::flush;
}

} // namespace abm
