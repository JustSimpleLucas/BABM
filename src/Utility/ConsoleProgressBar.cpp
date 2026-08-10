// ConsoleProgressBar.cpp

#include "Utility/ConsoleProgressBar.h"

#include <algorithm>
#include <chrono>
#include <iomanip>
#include <ostream>
#include <sstream>
#include <string>
#include <utility>

namespace abm {

namespace {

/** Formats a duration as m:ss, or h:mm:ss once a run passes an hour. */
[[nodiscard]] std::string formatDuration(std::chrono::seconds duration) {
    const long long totalSeconds = duration.count();
    const long long hours = totalSeconds / 3600;
    const long long minutes = (totalSeconds % 3600) / 60;
    const long long seconds = totalSeconds % 60;

    std::ostringstream formatted;
    if (hours > 0) {
        formatted << hours << ':' << std::setw(2) << std::setfill('0') << minutes;
    } else {
        formatted << minutes;
    }
    formatted << ':' << std::setw(2) << std::setfill('0') << seconds;
    return formatted.str();
}

} // namespace

ConsoleProgressBar::ConsoleProgressBar(std::ostream& output, std::size_t totalSteps,
                                       std::string label, std::size_t barWidth, bool enabled)
    : output_(output), totalSteps_(std::max<std::size_t>(1, totalSteps)), label_(std::move(label)),
      barWidth_(std::max<std::size_t>(10, barWidth)), enabled_(enabled),
      startTime_(std::chrono::steady_clock::now()),
      lastRenderedPercent_(static_cast<std::size_t>(-1)), finished_(false) {}

void ConsoleProgressBar::update(std::size_t completedSteps) {
    render(completedSteps, false);
}

void ConsoleProgressBar::finish() {
    if (finished_ || !enabled_) {
        finished_ = true;
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
    if (!enabled_) {
        return;
    }

    completedSteps = std::min(completedSteps, totalSteps_);
    const double progress = static_cast<double>(completedSteps) / static_cast<double>(totalSteps_);
    const auto percent = static_cast<std::size_t>(progress * 100.0);

    // Redrawing only when the visible percentage changes avoids excessive
    // terminal I/O during large Monte Carlo or sensitivity-analysis runs.
    if (!forceRender && percent == lastRenderedPercent_) {
        return;
    }
    lastRenderedPercent_ = percent;

    const std::size_t filledWidth =
        std::min(barWidth_, static_cast<std::size_t>(progress * static_cast<double>(barWidth_)));
    const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::steady_clock::now() - startTime_);

    output_ << '\r' << label_ << " [";
    for (std::size_t i = 0; i < barWidth_; ++i) {
        output_ << (i < filledWidth ? '#' : '.');
    }
    output_ << "] " << std::setw(3) << percent << "% " << '(' << completedSteps << '/'
            << totalSteps_ << " steps, " << formatDuration(elapsed) << " elapsed";

    /*
     * The remaining time is extrapolated from the average rate so far. It is
     * reported only once enough of the run has completed for that average to
     * mean anything, because a projection from the first few steps of a run
     * whose cost varies with book depth would be misleading rather than useful.
     */
    if (completedSteps > 0 && elapsed.count() > 0) {
        const double stepsPerSecond =
            static_cast<double>(completedSteps) / static_cast<double>(elapsed.count());
        if (progress >= 0.05 && completedSteps < totalSteps_ && stepsPerSecond > 0.0) {
            const auto remaining = std::chrono::seconds(static_cast<long long>(
                static_cast<double>(totalSteps_ - completedSteps) / stepsPerSecond));
            output_ << ", ~" << formatDuration(remaining) << " left";
        }
        output_ << ", " << static_cast<long long>(stepsPerSecond) << " steps/s";
    }

    output_ << ')' << std::flush;
}

} // namespace abm
