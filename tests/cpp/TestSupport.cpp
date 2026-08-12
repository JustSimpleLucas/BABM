// TestSupport.cpp

#include "tests/cpp/TestSupport.h"

#include "Simulation/SimulationEngine.h"

#include <cmath>
#include <exception>
#include <iostream>
#include <stdexcept>

namespace abm::test {

bool nearlyEqual(double lhs, double rhs, double tolerance) {
    return std::abs(lhs - rhs) <= tolerance;
}

void expect(bool condition, const std::string& message, int& failures) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

void expectInvalidConfigContaining(const SimulationConfig& config,
                                   const std::string& expectedMessageFragment,
                                   const std::string& message, int& failures) {
    try {
        const SimulationEngine simulation(config);
        static_cast<void>(simulation);
        expect(false, message, failures);
    } catch (const std::invalid_argument& error) {
        expect(std::string(error.what()).find(expectedMessageFragment) != std::string::npos,
               message, failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << message << " Expected std::invalid_argument, got: " << error.what()
                  << '\n';
        ++failures;
    }
}

AssetDefinition makeAssetDefinition(const std::string& name, double initialPrice,
                                    double initialStock, double priceTickSize,
                                    double fundamentalShockStdDev, double fundamentalDriftPerStep,
                                    double minimumFundamentalValue,
                                    FundamentalProcessType fundamentalProcess, bool enabled) {
    AssetDefinition asset;
    asset.name = name;
    asset.enabled = enabled;
    asset.fundamentalProcess = fundamentalProcess;
    asset.initialPrice = initialPrice;
    asset.initialStock = initialStock;
    asset.priceTickSize = priceTickSize;
    asset.fundamentalShockStdDev = fundamentalShockStdDev;
    asset.fundamentalDriftPerStep = fundamentalDriftPerStep;
    asset.minimumFundamentalValue = minimumFundamentalValue;
    return asset;
}

AssetDefinition& soleAsset(SimulationConfig& config) {
    AssetDefinition* asset = config.assets.legacyScalarAsset();
    if (asset == nullptr) {
        throw std::invalid_argument(
            "soleAsset() requires a config without an 'assets' declaration.");
    }
    return *asset;
}

SimulationConfig deterministicSmokeConfig() {
    SimulationConfig config;
    AssetDefinition& asset = soleAsset(config);
    asset.name = "test_asset";
    asset.initialPrice = 100.0;
    asset.initialStock = 5.0;
    asset.priceTickSize = 0.01;
    asset.fundamentalShockStdDev = 0.01;
    config.timeSteps = 8;
    config.warmupSteps = 25;
    config.numFundamentalists = 4;
    config.numChartists = 4;
    config.initialCash = 1000.0;
    config.shortSellingEnabled = false;
    config.riskFreeRate = 0.0001;
    config.agentActivityRate = 1.0;
    config.warmupPriceProcess.noiseStdDev = 0.001;
    config.warmupPriceProcess.fundamentalPullStrength = 0.05;
    config.seed = 20260420U;
    config.fundamentalist.mispricingThreshold = 0.001;
    config.chartist.strategyMode = ChartistStrategyMode::Momentum;
    config.social.enabled = true;
    config.social.interactionRadius = 1.5;
    config.social.privateSignalStdMin = 0.001;
    config.social.privateSignalStdMax = 0.002;
    return config;
}

} // namespace abm::test
