// MomentumChartistStrategy.cpp

#include "AgentStrategy/MomentumChartistStrategy.h"

#include "AgentStrategy/StrategyMarketHelpers.h"
#include "Market/Market.h"
#include "Utility/NumericValidation.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace abm {

MomentumChartistStrategy::MomentumChartistStrategy(MomentumChartistStrategyParameters parameters)
    : ChartistStrategy(std::move(parameters.commonParameters)),
      shortWindow_(parameters.shortWindow),
      longWindow_(parameters.longWindow),
      momentumSignalThreshold_(0.0) {
    setWindows(parameters.shortWindow, parameters.longWindow);
    setMomentumSignalThreshold(parameters.momentumSignalThreshold);
}

std::string MomentumChartistStrategy::strategyType() const {
    return "chartist_momentum";
}

void MomentumChartistStrategy::setWindows(std::size_t shortWindow, std::size_t longWindow) {
    requirePositiveSize(shortWindow, "Short window");
    requirePositiveSize(longWindow, "Long window");
    if (shortWindow > longWindow) {
        throw std::invalid_argument("Short window cannot be larger than long window.");
    }

    shortWindow_ = shortWindow;
    longWindow_ = longWindow;
}

void MomentumChartistStrategy::setMomentumSignalThreshold(double momentumSignalThreshold) {
    requireInHalfOpenUnitInterval(momentumSignalThreshold, "Momentum signal threshold");
    momentumSignalThreshold_ = momentumSignalThreshold;
}

double MomentumChartistStrategy::momentumSignalThreshold() const {
    return momentumSignalThreshold_;
}

AgentAction MomentumChartistStrategy::generateSignal(const Market& market) const {
    const double gap = movingAverageGap(market, assetIndex());
    if (gap > momentumSignalThreshold_) {
        return AgentAction::Buy;
    }
    if (gap < -momentumSignalThreshold_) {
        return AgentAction::Sell;
    }
    return AgentAction::Hold;
}

double MomentumChartistStrategy::forecastExcessReturn(
    const Market& market, std::size_t forecastAssetIndex) const {
    const double gap = movingAverageGap(market, forecastAssetIndex);
    if (std::abs(gap) <= momentumSignalThreshold_) {
        return 0.0;
    }
    return std::clamp(gap, -1.0, 1.0);
}

double MomentumChartistStrategy::movingAverageGap(const Market& market,
                                                  std::size_t forecastAssetIndex) const {
    const double shortMa = market.calculateMovingAverage(forecastAssetIndex, shortWindow_);
    const double longMa = market.calculateMovingAverage(forecastAssetIndex, longWindow_);

    /*
     * Formula note:
     * gap_t = log(MA_short,t / MA_long,t).
     *
     * A positive gap is interpreted as upward momentum; the configured
     * deadband suppresses small moving-average differences. The log form keeps
     * the forecast commensurate with log-return volatility.
     */
    return strategy_detail::safeLogRatio(shortMa, longMa);
}

} // namespace abm
