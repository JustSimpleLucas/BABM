// MeanReversionChartistStrategy.cpp

#include "AgentStrategy/MeanReversionChartistStrategy.h"

#include "AgentStrategy/StrategyMarketHelpers.h"
#include "Market/Market.h"
#include "Utility/NumericValidation.h"

#include <algorithm>
#include <utility>

namespace abm {

MeanReversionChartistStrategy::MeanReversionChartistStrategy(
    MeanReversionChartistStrategyParameters parameters)
    : ChartistStrategy(std::move(parameters.commonParameters)), longWindow_(parameters.longWindow) {
    setLongWindow(parameters.longWindow);
}

std::string MeanReversionChartistStrategy::strategyType() const {
    return "chartist_mean_reversion";
}

void MeanReversionChartistStrategy::setLongWindow(std::size_t longWindow) {
    requirePositiveSize(longWindow, "Long window");
    longWindow_ = longWindow;
}

AgentAction MeanReversionChartistStrategy::generateSignal(const Market& market) const {
    const double current = strategy_detail::latestPositiveMarketPrice(market, assetIndex());
    const double longMa = market.calculateMovingAverage(assetIndex(), longWindow_);
    if (current < longMa) {
        return AgentAction::Buy;
    }
    if (current > longMa) {
        return AgentAction::Sell;
    }
    return AgentAction::Hold;
}

double MeanReversionChartistStrategy::forecastExcessReturn(const Market& market,
                                                           std::size_t forecastAssetIndex) const {
    const double current = strategy_detail::latestPositiveMarketPrice(market, forecastAssetIndex);
    const double longMa = market.calculateMovingAverage(forecastAssetIndex, longWindow_);

    /*
     * Formula note:
     * expected_excess_return = clamp(log(MA_long,t / P_t), -1, 1).
     *
     * The sign is deliberately opposite to momentum: prices below the moving
     * average create a positive reversion forecast, and prices above it create
     * a negative forecast. The log form keeps the forecast commensurate with
     * log-return volatility.
     */
    return std::clamp(strategy_detail::safeLogRatio(longMa, current), -1.0, 1.0);
}

} // namespace abm
