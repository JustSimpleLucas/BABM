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

ChartistStrategyParameters makeCommonChartistParameters(const ChartistRuleSettings& settings) {
    ChartistStrategyParameters parameters;
    parameters.assetIndex = settings.assetIndex;
    parameters.allocationLine = settings.allocationLine;
    parameters.volatilityWindow = settings.volatilityWindow;
    parameters.riskFreeRate = settings.riskFreeRate;
    parameters.maxShortWeight = settings.maxShortWeight;
    parameters.referencePointMode = settings.referencePointMode;
    parameters.referenceMovingAverageWindow = settings.referenceMovingAverageWindow;
    parameters.maxGrossExposure = settings.maxGrossExposure;
    parameters.forecastHorizon = settings.forecastHorizon;
    return parameters;
}

MomentumChartistStrategyParameters
makeMomentumChartistParameters(const ChartistRuleSettings& settings) {
    MomentumChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters(settings);
    parameters.shortWindow = settings.shortWindow;
    parameters.longWindow = settings.longWindow;
    parameters.momentumSignalThreshold = settings.momentumSignalThreshold;
    return parameters;
}

MeanReversionChartistStrategyParameters
makeMeanReversionChartistParameters(const ChartistRuleSettings& settings) {
    MeanReversionChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters(settings);
    parameters.longWindow = settings.longWindow;
    return parameters;
}

BreakoutChartistStrategyParameters
makeBreakoutChartistParameters(const ChartistRuleSettings& settings) {
    BreakoutChartistStrategyParameters parameters;
    parameters.commonParameters = makeCommonChartistParameters(settings);
    parameters.breakoutWindow = settings.breakoutWindow;
    return parameters;
}

/** Gathers the population-wide chartist settings from the simulation config. */
ChartistRuleSettings populationChartistSettings(const SimulationConfig& config,
                                                const AssetAllocationLine& allocationLine) {
    ChartistRuleSettings settings;
    settings.assetIndex = config.assets.primaryIndex();
    settings.allocationLine = allocationLine;
    settings.shortWindow = config.chartist.shortWindow;
    settings.longWindow = config.chartist.longWindow;
    settings.momentumSignalThreshold = config.chartist.momentumSignalThreshold;
    settings.breakoutWindow = config.chartist.breakoutWindow;
    settings.volatilityWindow = config.chartist.volatilityWindow;
    settings.maxShortWeight = config.chartist.maxShortWeight;
    settings.maxGrossExposure = config.chartist.allocation.maxGrossExposure;
    settings.forecastHorizon = config.chartist.forecastHorizon;
    settings.riskFreeRate = config.riskFreeRate;
    settings.referencePointMode = config.control.referencePointMode;
    settings.referenceMovingAverageWindow = config.control.referenceMovingAverageWindow;
    return settings;
}

} // namespace

std::unique_ptr<TradingStrategy> createChartistStrategy(ChartistStrategyMode mode,
                                                        const ChartistRuleSettings& settings) {
    switch (mode) {
    case ChartistStrategyMode::Momentum:
        return std::make_unique<MomentumChartistStrategy>(makeMomentumChartistParameters(settings));
    case ChartistStrategyMode::MeanReversion:
        return std::make_unique<MeanReversionChartistStrategy>(
            makeMeanReversionChartistParameters(settings));
    case ChartistStrategyMode::RelativeStrengthIndex:
        return std::make_unique<RelativeStrengthIndexChartistStrategy>(
            makeCommonChartistParameters(settings));
    case ChartistStrategyMode::Breakout:
        return std::make_unique<BreakoutChartistStrategy>(makeBreakoutChartistParameters(settings));
    case ChartistStrategyMode::Random:
        break;
    }

    return std::make_unique<MomentumChartistStrategy>(makeMomentumChartistParameters(settings));
}

std::unique_ptr<TradingStrategy> createChartistStrategy(const SimulationConfig& config,
                                                        const AssetAllocationLine& allocationLine,
                                                        RandomEngine& random) {
    const ChartistStrategyMode selectedMode =
        selectConcreteChartistMode(config.chartist.strategyMode, random);
    return createChartistStrategy(selectedMode, populationChartistSettings(config, allocationLine));
}

} // namespace abm
