// ChartistStrategyFactory.cpp

#include "AgentStrategy/ChartistStrategyFactory.h"

#include "AgentStrategy/BreakoutChartistStrategy.h"
#include "AgentStrategy/MeanReversionChartistStrategy.h"
#include "AgentStrategy/MomentumChartistStrategy.h"
#include "AgentStrategy/RelativeStrengthIndexChartistStrategy.h"
#include "RandomGenerator/RandomGenerator.h"

namespace abm {
namespace {

ChartistStrategyMode selectConcreteChartistMode(ChartistStrategyMode mode, RandomEngine& random) {
    if (mode != ChartistStrategyMode::Random) {
        return mode;
    }

    /*
     * Random chartist mode samples across every available technical rule. The
     * draw still uses the seeded simulation stream, so the realised strategy
     * mix remains reproducible for a fixed configuration and seed.
     */
    switch (random.generateUniformIntDist(0, 3)) {
    case 0:
        return ChartistStrategyMode::Momentum;
    case 1:
        return ChartistStrategyMode::MeanReversion;
    case 2:
        return ChartistStrategyMode::RelativeStrengthIndex;
    default:
        return ChartistStrategyMode::Breakout;
    }
}

ChartistStrategyParameters makeCommonChartistParameters(const SimulationConfig& config,
                                                        const AssetAllocationLine& allocationLine) {
    ChartistStrategyParameters parameters;
    parameters.assetIndex = config.assets.primaryIndex();
    parameters.allocationLine = allocationLine;
    parameters.volatilityWindow = config.chartist.volatilityWindow;
    parameters.riskFreeRate = config.riskFreeRate;
    parameters.maxShortWeight = config.chartist.maxShortWeight;
    parameters.referencePointMode = config.control.referencePointMode;
    parameters.referenceMovingAverageWindow = config.control.referenceMovingAverageWindow;
    parameters.maxGrossExposure = config.chartist.allocation.maxGrossExposure;
    return parameters;
}

MomentumChartistStrategyParameters
makeMomentumChartistParameters(const SimulationConfig& config,
                               const AssetAllocationLine& allocationLine) {
    MomentumChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters(config, allocationLine);
    parameters.shortWindow = config.chartist.shortWindow;
    parameters.longWindow = config.chartist.longWindow;
    parameters.momentumSignalThreshold = config.chartist.momentumSignalThreshold;
    return parameters;
}

MeanReversionChartistStrategyParameters
makeMeanReversionChartistParameters(const SimulationConfig& config,
                                    const AssetAllocationLine& allocationLine) {
    MeanReversionChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters(config, allocationLine);
    parameters.longWindow = config.chartist.longWindow;
    return parameters;
}

BreakoutChartistStrategyParameters
makeBreakoutChartistParameters(const SimulationConfig& config,
                               const AssetAllocationLine& allocationLine) {
    BreakoutChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters(config, allocationLine);
    parameters.breakoutWindow = config.chartist.breakoutWindow;
    return parameters;
}

} // namespace

std::unique_ptr<TradingStrategy> createChartistStrategy(const SimulationConfig& config,
                                                        const AssetAllocationLine& allocationLine,
                                                        RandomEngine& random) {
    const ChartistStrategyMode selectedMode =
        selectConcreteChartistMode(config.chartist.strategyMode, random);

    switch (selectedMode) {
    case ChartistStrategyMode::Momentum:
        return std::make_unique<MomentumChartistStrategy>(
            makeMomentumChartistParameters(config, allocationLine));
    case ChartistStrategyMode::MeanReversion:
        return std::make_unique<MeanReversionChartistStrategy>(
            makeMeanReversionChartistParameters(config, allocationLine));
    case ChartistStrategyMode::RelativeStrengthIndex:
        return std::make_unique<RelativeStrengthIndexChartistStrategy>(
            makeCommonChartistParameters(config, allocationLine));
    case ChartistStrategyMode::Breakout:
        return std::make_unique<BreakoutChartistStrategy>(
            makeBreakoutChartistParameters(config, allocationLine));
    case ChartistStrategyMode::Random:
        break;
    }

    return std::make_unique<MomentumChartistStrategy>(
        makeMomentumChartistParameters(config, allocationLine));
}

} // namespace abm
