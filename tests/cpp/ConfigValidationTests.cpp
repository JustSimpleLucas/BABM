#include "tests/cpp/TestSupport.h"

#include "Simulation/SimulationEngine.h"

#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void testSimulationConfigRejectsInvalidAllocationBounds(int& failures) {
    abm::SimulationConfig fundamentalistConfig = abm::test::deterministicSmokeConfig();
    fundamentalistConfig.fundamentalist.allocation.minRiskyWeight = 1.25;
    fundamentalistConfig.fundamentalist.allocation.maxRiskyWeight = 1.0;
    abm::test::expectInvalidConfigContaining(
        fundamentalistConfig, "Fundamentalist allocation minimum risky weight",
        "config validation should reject invalid fundamentalist allocation bounds", failures);

    abm::SimulationConfig chartistConfig = abm::test::deterministicSmokeConfig();
    chartistConfig.chartist.allocation.minRiskyWeight = 1.25;
    chartistConfig.chartist.allocation.maxRiskyWeight = 1.0;
    abm::test::expectInvalidConfigContaining(
        chartistConfig, "Chartist allocation minimum risky weight",
        "config validation should reject invalid chartist allocation bounds", failures);
}

/*
 * A forecast horizon is the number of steps over which an agent expects its
 * forecast to play out; it cannot be shorter than the single step on which the
 * trade is decided, so values below one are rejected for every owner.
 */
void testSimulationConfigRejectsForecastHorizonBelowOneStep(int& failures) {
    abm::SimulationConfig fundamentalistConfig = abm::test::deterministicSmokeConfig();
    fundamentalistConfig.fundamentalist.forecastHorizon = 0.5;
    abm::test::expectInvalidConfigContaining(
        fundamentalistConfig, "fundamentalist_forecast_horizon",
        "config validation should reject a fundamentalist forecast horizon below one step",
        failures);

    abm::SimulationConfig chartistConfig = abm::test::deterministicSmokeConfig();
    chartistConfig.chartist.forecastHorizon = 0.0;
    abm::test::expectInvalidConfigContaining(
        chartistConfig, "chartist_forecast_horizon",
        "config validation should reject a chartist forecast horizon below one step", failures);

    abm::SimulationConfig protagonistConfig = abm::test::deterministicSmokeConfig();
    protagonistConfig.protagonist.enabled = true;
    protagonistConfig.protagonist.forecastHorizon = 0.9;
    abm::test::expectInvalidConfigContaining(
        protagonistConfig, "protagonist_forecast_horizon",
        "config validation should reject a protagonist forecast horizon below one step", failures);
}

void testSimulationConfigRejectsInsufficientWarmupHistory(int& failures) {
    abm::SimulationConfig fundamentalistConfig = abm::test::deterministicSmokeConfig();
    fundamentalistConfig.numChartists = 0;
    fundamentalistConfig.fundamentalist.volatilityWindow = 6;
    fundamentalistConfig.warmupSteps = 5;
    abm::test::expectInvalidConfigContaining(
        fundamentalistConfig, "active fundamentalist volatility estimation",
        "config validation should reject insufficient fundamentalist warm-up history", failures);

    abm::SimulationConfig chartistConfig = abm::test::deterministicSmokeConfig();
    chartistConfig.numFundamentalists = 0;
    chartistConfig.chartist.strategyMode = abm::ChartistStrategyMode::Momentum;
    chartistConfig.chartist.shortWindow = 3;
    chartistConfig.chartist.longWindow = 8;
    chartistConfig.chartist.volatilityWindow = 2;
    chartistConfig.warmupSteps = 6;
    abm::test::expectInvalidConfigContaining(
        chartistConfig, "active chartist lookback indicators",
        "config validation should reject insufficient chartist warm-up history", failures);

    abm::SimulationConfig breakoutConfig = abm::test::deterministicSmokeConfig();
    breakoutConfig.numFundamentalists = 0;
    breakoutConfig.chartist.strategyMode = abm::ChartistStrategyMode::Breakout;
    breakoutConfig.chartist.breakoutWindow = 8;
    breakoutConfig.chartist.volatilityWindow = 2;
    breakoutConfig.warmupSteps = 7;
    abm::test::expectInvalidConfigContaining(
        breakoutConfig, "active chartist lookback indicators",
        "config validation should reject insufficient breakout warm-up history", failures);
}

void testSimulationConfigRejectsInvalidReferenceMovingAverageWindow(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.control.prospectTheoryEnabled = true;
    config.control.referencePointMode = abm::ProspectReferencePointMode::MovingAveragePrice;
    config.control.referenceMovingAverageWindow = 0;

    abm::test::expectInvalidConfigContaining(
        config, "Control reference moving-average window",
        "config validation should reject a zero CPT moving-average reference window", failures);
}

void testSimulationConfigRejectsInvalidProspectTheoryAgentFraction(int& failures) {
    abm::SimulationConfig negativeFraction = abm::test::deterministicSmokeConfig();
    negativeFraction.control.prospectTheoryAgentFraction = -0.01;
    abm::test::expectInvalidConfigContaining(
        negativeFraction, "Control Prospect Theory agent fraction",
        "config validation should reject negative CPT agent fractions", failures);

    abm::SimulationConfig tooLargeFraction = abm::test::deterministicSmokeConfig();
    tooLargeFraction.control.prospectTheoryAgentFraction = 1.01;
    abm::test::expectInvalidConfigContaining(
        tooLargeFraction, "Control Prospect Theory agent fraction",
        "config validation should reject CPT agent fractions above one", failures);
}

void testSimulationConfigRejectsInvalidMomentumThreshold(int& failures) {
    abm::SimulationConfig negativeThreshold = abm::test::deterministicSmokeConfig();
    negativeThreshold.chartist.momentumSignalThreshold = -0.01;
    abm::test::expectInvalidConfigContaining(
        negativeThreshold, "Chartist momentum signal threshold",
        "config validation should reject negative chartist momentum thresholds", failures);

    abm::SimulationConfig unitThreshold = abm::test::deterministicSmokeConfig();
    unitThreshold.chartist.momentumSignalThreshold = 1.0;
    abm::test::expectInvalidConfigContaining(
        unitThreshold, "Chartist momentum signal threshold",
        "config validation should reject chartist momentum thresholds outside [0, 1)", failures);
}

void testSimulationConfigRejectsInvalidBreakoutWindow(int& failures) {
    abm::SimulationConfig zeroWindow = abm::test::deterministicSmokeConfig();
    zeroWindow.chartist.breakoutWindow = 0;
    abm::test::expectInvalidConfigContaining(
        zeroWindow, "Chartist breakout window",
        "config validation should reject zero chartist breakout windows", failures);
}

void testSimulationConfigRejectsInvalidMicrostructureControls(int& failures) {
    abm::SimulationConfig zeroExpiry = abm::test::deterministicSmokeConfig();
    zeroExpiry.microstructure.orderExpirySteps = 0;
    abm::test::expectInvalidConfigContaining(
        zeroExpiry, "Order expiry steps", "config validation should reject zero order-expiry steps",
        failures);

    abm::SimulationConfig badMarketOrderProbability = abm::test::deterministicSmokeConfig();
    badMarketOrderProbability.microstructure.marketOrderProbability = 1.25;
    abm::test::expectInvalidConfigContaining(
        badMarketOrderProbability, "Market order probability",
        "config validation should reject market-order probabilities outside [0, 1]", failures);

    abm::SimulationConfig zeroDepth = abm::test::deterministicSmokeConfig();
    zeroDepth.microstructure.bookDepthLevels = 0;
    abm::test::expectInvalidConfigContaining(
        zeroDepth, "Book depth levels",
        "config validation should reject zero visible book-depth levels", failures);
}

void testSimulationConfigRejectsInvalidTransactionCostControls(int& failures) {
    abm::SimulationConfig negativeRate = abm::test::deterministicSmokeConfig();
    negativeRate.transactionCosts.rate = -0.01;
    abm::test::expectInvalidConfigContaining(
        negativeRate, "Transaction cost rate",
        "config validation should reject negative transaction-cost rates", failures);

    abm::SimulationConfig unitRate = abm::test::deterministicSmokeConfig();
    unitRate.transactionCosts.rate = 1.0;
    abm::test::expectInvalidConfigContaining(
        unitRate, "Transaction cost rate",
        "config validation should reject transaction-cost rates greater than or equal to one",
        failures);
}

void testSimulationConfigRejectsInvalidWarmupPriceProcess(int& failures) {
    abm::SimulationConfig negativeWarmupNoise = abm::test::deterministicSmokeConfig();
    negativeWarmupNoise.warmupPriceProcess.noiseStdDev = -0.01;
    abm::test::expectInvalidConfigContaining(
        negativeWarmupNoise, "Warm-up price noise stddev",
        "config validation should reject negative warm-up price noise", failures);

    abm::SimulationConfig negativeWarmupPull = abm::test::deterministicSmokeConfig();
    negativeWarmupPull.warmupPriceProcess.fundamentalPullStrength = -0.01;
    abm::test::expectInvalidConfigContaining(
        negativeWarmupPull, "Warm-up fundamental pull strength",
        "config validation should reject negative warm-up fundamental pull", failures);
}

/*
 * The fundamental process is validated per asset, which covers the legacy
 * single-asset spelling too: an undeclared universe still holds one asset, so
 * these fixtures are rejected by the same check that guards a declared asset
 * and the diagnostic names the offending asset.
 */
void testSimulationConfigRejectsInvalidFundamentalProcess(int& failures) {
    abm::SimulationConfig nonFiniteDrift = abm::test::deterministicSmokeConfig();
    abm::test::soleAsset(nonFiniteDrift).fundamentalDriftPerStep =
        std::numeric_limits<double>::infinity();
    abm::test::expectInvalidConfigContaining(
        nonFiniteDrift, "Asset 'test_asset' fundamental drift per step",
        "config validation should reject non-finite fundamental drift", failures);

    abm::SimulationConfig nonPositiveFloor = abm::test::deterministicSmokeConfig();
    abm::test::soleAsset(nonPositiveFloor).minimumFundamentalValue = 0.0;
    abm::test::expectInvalidConfigContaining(
        nonPositiveFloor, "Asset 'test_asset' minimum fundamental value",
        "config validation should reject non-positive fundamental-value floors", failures);
}

void testSimulationConfigRejectsInvalidNoiseTraderControls(int& failures) {
    abm::SimulationConfig badShockScale = abm::test::deterministicSmokeConfig();
    badShockScale.noiseTrader.beliefShockStdDev = 0.0;
    abm::test::expectInvalidConfigContaining(
        badShockScale, "Noise-trader belief shock stddev",
        "config validation should reject non-positive noise-trader belief-shock scales", failures);

    abm::SimulationConfig badOrderFraction = abm::test::deterministicSmokeConfig();
    badOrderFraction.noiseTrader.orderSizeFraction = 0.0;
    abm::test::expectInvalidConfigContaining(
        badOrderFraction, "Noise-trader order size fraction",
        "config validation should reject non-positive noise-trader order-size fractions", failures);

    abm::SimulationConfig badShortWeight = abm::test::deterministicSmokeConfig();
    badShortWeight.noiseTrader.maxShortWeight = 1.25;
    abm::test::expectInvalidConfigContaining(
        badShortWeight, "Noise-trader max short weight",
        "config validation should reject noise-trader short caps outside [0, 1]", failures);
}

void testSimulationConfigRejectsInvalidBuyAndHoldControls(int& failures) {
    abm::SimulationConfig zeroTarget = abm::test::deterministicSmokeConfig();
    zeroTarget.buyAndHold.targetRiskyWeight = 0.0;
    abm::test::expectInvalidConfigContaining(
        zeroTarget, "Buy-and-hold target risky weight",
        "config validation should reject zero buy-and-hold target weights", failures);

    abm::SimulationConfig tooLargeTarget = abm::test::deterministicSmokeConfig();
    tooLargeTarget.buyAndHold.targetRiskyWeight = 1.25;
    abm::test::expectInvalidConfigContaining(
        tooLargeTarget, "Buy-and-hold target risky weight",
        "config validation should reject buy-and-hold target weights above one", failures);
}

void testSimulationConfigAcceptsNoiseOnlyPopulation(int& failures) {
    try {
        abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
        config.timeSteps = 4;
        config.warmupSteps = 0;
        config.numFundamentalists = 0;
        config.numChartists = 0;
        config.numNoiseTraders = 6;
        config.initialCash = 5000.0;
        abm::test::soleAsset(config).initialStock = 2.0;
        config.shortSellingEnabled = false;
        config.social.enabled = false;

        abm::SimulationEngine simulation(config);
        const abm::SimulationRunResult simulationResult = simulation.run();

        abm::test::expect(simulationResult.agentSnapshots().size() == config.numNoiseTraders,
                          "noise-only simulations should initialise the configured population",
                          failures);
        for (const abm::AgentSnapshot& snapshot : simulationResult.agentSnapshots()) {
            abm::test::expect(snapshot.initialStrategyType == "noise_trader",
                              "noise-only snapshots should expose the noise_trader strategy label",
                              failures);
        }
    } catch (const std::exception& error) {
        std::cerr << "FAIL: noise-only population should be accepted: " << error.what() << '\n';
        ++failures;
    }
}

void testSimulationConfigAcceptsBuyAndHoldOnlyPopulation(int& failures) {
    try {
        abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
        config.timeSteps = 4;
        config.warmupSteps = 0;
        config.numFundamentalists = 0;
        config.numChartists = 0;
        config.numNoiseTraders = 0;
        config.numBuyAndHoldAgents = 5;
        config.initialCash = 5000.0;
        abm::test::soleAsset(config).initialStock = 0.0;
        config.shortSellingEnabled = false;
        config.social.enabled = false;

        abm::SimulationEngine simulation(config);
        const abm::SimulationRunResult simulationResult = simulation.run();

        abm::test::expect(
            simulationResult.agentSnapshots().size() == config.numBuyAndHoldAgents,
            "buy-and-hold-only simulations should initialise the configured population", failures);
        for (const abm::AgentSnapshot& snapshot : simulationResult.agentSnapshots()) {
            abm::test::expect(snapshot.initialStrategyType == "buy_and_hold",
                              "buy-and-hold-only snapshots should expose the strategy label",
                              failures);
        }
    } catch (const std::exception& error) {
        std::cerr << "FAIL: buy-and-hold-only population should be accepted: " << error.what()
                  << '\n';
        ++failures;
    }
}

void testSimulationConfigRejectsInvalidProtagonistControls(int& failures) {
    abm::SimulationConfig baseline = abm::test::deterministicSmokeConfig();
    baseline.protagonist.enabled = true;

    abm::SimulationConfig negativeCash = baseline;
    negativeCash.protagonist.initialCash = -1.0;
    abm::test::expectInvalidConfigContaining(negativeCash, "protagonist_initial_cash",
                                             "negative protagonist cash should be rejected",
                                             failures);

    abm::SimulationConfig invalidWeights = baseline;
    invalidWeights.protagonist.allocation.minRiskyWeight = 0.9;
    invalidWeights.protagonist.allocation.maxRiskyWeight = 0.1;
    abm::test::expectInvalidConfigContaining(
        invalidWeights, "protagonist_min_risky_weight",
        "inverted protagonist allocation bounds should be rejected", failures);

    abm::SimulationConfig invalidWindows = baseline;
    invalidWindows.protagonist.shortWindow = 30;
    invalidWindows.protagonist.longWindow = 10;
    abm::test::expectInvalidConfigContaining(
        invalidWindows, "protagonist_short_window",
        "a protagonist short window above his long window should be rejected", failures);

    abm::SimulationConfig invalidThreshold = baseline;
    invalidThreshold.protagonist.mispricingThreshold = 1.5;
    abm::test::expectInvalidConfigContaining(
        invalidThreshold, "protagonist_mispricing_threshold",
        "an out-of-range protagonist mispricing threshold should be rejected", failures);

    abm::SimulationConfig invalidOrderSize = baseline;
    invalidOrderSize.protagonist.noiseOrderSizeFraction = 0.0;
    abm::test::expectInvalidConfigContaining(
        invalidOrderSize, "protagonist_noise_order_size_fraction",
        "a zero protagonist noise order size should be rejected", failures);

    abm::SimulationConfig invalidLossAversion = baseline;
    invalidLossAversion.protagonist.prospectTheoryEnabled = true;
    invalidLossAversion.protagonist.lossAversion = 0.0;
    abm::test::expectInvalidConfigContaining(
        invalidLossAversion, "protagonist_loss_aversion",
        "a non-positive protagonist loss aversion should be rejected when CPT is on", failures);
}

/**
 * His own lookbacks must be covered by the warm-up, not just the population's.
 *
 * The population here runs windows that the configured warm-up already covers,
 * so a failure can only come from his longer breakout window: this pins the
 * check to the protagonist rather than to a strategy that happens to share it.
 */
void testSimulationConfigRejectsWarmupTooShortForTheProtagonist(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.warmupSteps = 25;
    config.protagonist.enabled = true;
    config.protagonist.strategy = abm::ProtagonistStrategyKind::Chartist;
    config.protagonist.chartistRule = abm::ChartistStrategyMode::Breakout;
    config.protagonist.breakoutWindow = 400;

    abm::test::expectInvalidConfigContaining(
        config, "protagonist",
        "a warm-up too short for the protagonist's own lookback should be rejected", failures);
}

/**
 * A protagonist alone is a legitimate, if degenerate, market.
 *
 * Refusing it would make the isolated single-agent diagnostic impossible to
 * run, which is a useful thing to be able to do when a strategy misbehaves.
 */
void testSimulationConfigAcceptsProtagonistOnlyPopulation(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 5;
    config.numFundamentalists = 0;
    config.numChartists = 0;
    config.numNoiseTraders = 0;
    config.numBuyAndHoldAgents = 0;
    config.protagonist.enabled = true;
    config.social.enabled = false;

    try {
        abm::SimulationEngine simulation(config);
        const abm::SimulationRunResult simulationResult = simulation.run();

        abm::test::expect(simulationResult.agentSnapshots().size() == 1,
                          "a protagonist-only population should hold exactly one agent", failures);
        abm::test::expect(!simulationResult.agentSnapshots().empty() &&
                              simulationResult.agentSnapshots().front().isProtagonist,
                          "the sole agent of a protagonist-only run should carry the flag",
                          failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: protagonist-only population should be accepted: " << error.what()
                  << '\n';
        ++failures;
    }
}

} // namespace

namespace abm::test {

void runConfigValidationTests(int& failures) {
    testSimulationConfigRejectsInvalidProtagonistControls(failures);
    testSimulationConfigRejectsWarmupTooShortForTheProtagonist(failures);
    testSimulationConfigAcceptsProtagonistOnlyPopulation(failures);
    testSimulationConfigRejectsInvalidAllocationBounds(failures);
    testSimulationConfigRejectsForecastHorizonBelowOneStep(failures);
    testSimulationConfigRejectsInsufficientWarmupHistory(failures);
    testSimulationConfigRejectsInvalidReferenceMovingAverageWindow(failures);
    testSimulationConfigRejectsInvalidProspectTheoryAgentFraction(failures);
    testSimulationConfigRejectsInvalidMomentumThreshold(failures);
    testSimulationConfigRejectsInvalidBreakoutWindow(failures);
    testSimulationConfigRejectsInvalidMicrostructureControls(failures);
    testSimulationConfigRejectsInvalidTransactionCostControls(failures);
    testSimulationConfigRejectsInvalidFundamentalProcess(failures);
    testSimulationConfigRejectsInvalidWarmupPriceProcess(failures);
    testSimulationConfigRejectsInvalidNoiseTraderControls(failures);
    testSimulationConfigRejectsInvalidBuyAndHoldControls(failures);
    testSimulationConfigAcceptsNoiseOnlyPopulation(failures);
    testSimulationConfigAcceptsBuyAndHoldOnlyPopulation(failures);
}

} // namespace abm::test
