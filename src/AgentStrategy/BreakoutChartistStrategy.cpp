// BreakoutChartistStrategy.cpp

#include "AgentStrategy/BreakoutChartistStrategy.h"

#include "AgentStrategy/StrategyMarketHelpers.h"
#include "Market/Market.h"
#include "Utility/NumericValidation.h"

#include <algorithm>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <utility>

namespace abm {

BreakoutChartistStrategy::BreakoutChartistStrategy(BreakoutChartistStrategyParameters parameters)
    : ChartistStrategy(std::move(parameters.commonParameters)),
      breakoutWindow_(parameters.breakoutWindow) {
    setBreakoutWindow(parameters.breakoutWindow);
}

std::string BreakoutChartistStrategy::strategyType() const {
    return "chartist_breakout";
}

void BreakoutChartistStrategy::setBreakoutWindow(std::size_t breakoutWindow) {
    requirePositiveSize(breakoutWindow, "Breakout window");
    breakoutWindow_ = breakoutWindow;
}

std::size_t BreakoutChartistStrategy::breakoutWindow() const {
    return breakoutWindow_;
}

AgentAction BreakoutChartistStrategy::generateSignal(const Market& market) const {
    const double latest = strategy_detail::latestPositiveMarketPrice(market, assetIndex());
    const auto [channelLow, channelHigh] = previousPriceChannel(market, assetIndex());

    if (latest > channelHigh) {
        return AgentAction::Buy;
    }
    if (latest < channelLow) {
        return AgentAction::Sell;
    }
    return AgentAction::Hold;
}

double BreakoutChartistStrategy::forecastExcessReturn(const Market& market,
                                                      std::size_t forecastAssetIndex) const {
    const double latest = strategy_detail::latestPositiveMarketPrice(market, forecastAssetIndex);
    const auto [channelLow, channelHigh] = previousPriceChannel(market, forecastAssetIndex);

    if (latest > channelHigh) {
        /*
         * Formula note:
         * expected_excess_return = clamp(log(P_t / H_t), -1, 1),
         * where H_t is the previous-window high. The log form keeps the
         * forecast commensurate with log-return volatility.
         */
        return std::clamp(strategy_detail::safeLogRatio(latest, channelHigh), -1.0, 1.0);
    }
    if (latest < channelLow) {
        /*
         * Formula note:
         * expected_excess_return = clamp(log(P_t / L_t), -1, 1),
         * where L_t is the previous-window low.
         */
        return std::clamp(strategy_detail::safeLogRatio(latest, channelLow), -1.0, 1.0);
    }
    return 0.0;
}

std::pair<double, double>
BreakoutChartistStrategy::previousPriceChannel(const Market& market,
                                               std::size_t forecastAssetIndex) const {
    const auto& values = market.getMarketValues(forecastAssetIndex);
    if (values.size() <= breakoutWindow_) {
        throw std::invalid_argument(
            "Insufficient market values to calculate breakout channel for asset index " +
            std::to_string(forecastAssetIndex) + '.');
    }

    const auto channelBegin = values.end() - static_cast<std::ptrdiff_t>(breakoutWindow_) - 1;
    const auto channelEnd = values.end() - 1;
    /*
     * Formula note:
     * L_t = min(P_{t-h}, ..., P_{t-1}) and
     * H_t = max(P_{t-h}, ..., P_{t-1}).
     *
     * The latest price P_t is excluded from the channel so a breakout is
     * tested against information available before the current observation.
     */
    const auto [lowIt, highIt] = std::minmax_element(channelBegin, channelEnd);
    return {*lowIt, *highIt};
}

} // namespace abm
