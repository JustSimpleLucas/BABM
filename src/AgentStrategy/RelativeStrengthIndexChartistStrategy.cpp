// RelativeStrengthIndexChartistStrategy.cpp

#include "AgentStrategy/RelativeStrengthIndexChartistStrategy.h"

#include "Market/Market.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <utility>

namespace abm {
RelativeStrengthIndexChartistStrategy::RelativeStrengthIndexChartistStrategy(
    ChartistStrategyParameters parameters)
    : ChartistStrategy(std::move(parameters)) {}

std::string RelativeStrengthIndexChartistStrategy::strategyType() const {
    return "chartist_relative_strength_index";
}

AgentAction RelativeStrengthIndexChartistStrategy::generateSignal(const Market& market) const {
    const double rsi = market.calculateRSI(assetIndex(), kRelativeStrengthIndexPeriod);
    if (rsi < 30.0) {
        return AgentAction::Buy;
    }
    if (rsi > 70.0) {
        return AgentAction::Sell;
    }
    return AgentAction::Hold;
}

double
RelativeStrengthIndexChartistStrategy::forecastExcessReturn(const Market& market,
                                                            std::size_t forecastAssetIndex) const {
    const double rsi = market.calculateRSI(forecastAssetIndex, kRelativeStrengthIndexPeriod);

    /*
     * Formula note:
     * centered_RSI = (50 - RSI_t) / 50,
     * expected_excess_return = clamp(0.05 * centered_RSI, -1, 1).
     *
     * RSI values below 50 generate a positive contrarian forecast; values
     * above 50 generate a negative forecast.
     */
    const double centered = (50.0 - rsi) / 50.0;
    return std::clamp(centered * 0.05, -1.0, 1.0);
}

} // namespace abm
