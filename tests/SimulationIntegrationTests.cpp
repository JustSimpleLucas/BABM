// SimulationIntegrationTests.cpp

#include "tests/TestSupport.h"

#include "Simulation/SimulationEngine.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace {

void testTwoAssetRunProducesIndependentPerAssetOutput(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 40;
    config.numFundamentalists = 6;
    config.numChartists = 6;
    // Noise traders supply the two-sided order flow that valuation-driven
    // agents alone do not: fundamentalists and chartists share one view of
    // each asset and therefore quote the same side.
    config.numNoiseTraders = 8;
    config.initialCash = 10000.0;
    config.assets.declare(
        {abm::test::makeAssetDefinition("alpha", 100.0, 5.0, 0.01, 0.01, 0.02, 1.0),
         abm::test::makeAssetDefinition("beta", 40.0, 5.0, 0.05, 0.02, -0.01, 1.0)});
    config.primaryAssetName = "alpha";

    abm::SimulationEngine engine(config);
    const abm::SimulationRunResult result = engine.run();
    const abm::MultiAssetRunData& multiAsset = result.multiAssetData();

    abm::test::expect(multiAsset.assetNames.size() == 2 &&
                          multiAsset.assetNames[0] == "alpha" &&
                          multiAsset.assetNames[1] == "beta",
                      "a two-asset run should record both assets in declared order", failures);
    abm::test::expect(multiAsset.assetStepDetails.size() == config.timeSteps * 2,
                      "per-asset diagnostics should hold one record per step and asset", failures);

    const std::vector<double>& alphaFundamentals = multiAsset.fundamentalPriceHistories.at(0);
    const std::vector<double>& betaFundamentals = multiAsset.fundamentalPriceHistories.at(1);
    abm::test::expect(alphaFundamentals.back() > alphaFundamentals.front() &&
                          betaFundamentals.back() < betaFundamentals.front(),
                      "each asset's fundamental should follow its own configured drift", failures);
    abm::test::expect(multiAsset.marketPriceHistories.at(0) != multiAsset.marketPriceHistories.at(1),
                      "assets with distinct parameters should produce distinct price paths",
                      failures);

    abm::test::expect(result.marketPriceHistory() == multiAsset.marketPriceHistories.at(0),
                      "single-asset outputs should project the designated primary asset",
                      failures);

    double alphaVolume = 0.0;
    double betaVolume = 0.0;
    for (const abm::AssetStepDetails& record : multiAsset.assetStepDetails) {
        (record.assetIndex == 0 ? alphaVolume : betaVolume) += record.tradedVolume;
    }
    abm::test::expect(alphaVolume > 0.0 && betaVolume > 0.0,
                      "both assets should trade in a mixed-population run", failures);
}

void testTwoAssetRunConservesCashAndShares(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 40;
    config.numFundamentalists = 6;
    config.numChartists = 6;
    config.numNoiseTraders = 8;
    config.initialCash = 10000.0;
    config.transactionCosts.rate = 0.0;
    config.riskFreeRate = 0.0;
    config.shortSellingEnabled = false;
    config.assets.declare(
        {abm::test::makeAssetDefinition("alpha", 100.0, 5.0, 0.01, 0.01, 0.0, 1.0),
         abm::test::makeAssetDefinition("beta", 40.0, 5.0, 0.05, 0.01, 0.0, 1.0)});

    abm::SimulationEngine engine(config);
    const abm::SimulationRunResult result = engine.run();

    /*
     * With zero transaction costs, no risk-free accrual, and short selling
     * disabled, every execution is an internal transfer: aggregate cash and
     * per-asset share counts must be unchanged from the endowment. Forced
     * buy-ins would break this identity because they trade against external
     * liquidity, but they cannot fire while shorting is disabled.
     */
    const std::size_t agentCount = result.agentSnapshots().size();
    double totalFinalCash = 0.0;
    double totalFinalAlphaShares = 0.0;
    for (const abm::AgentSnapshot& snapshot : result.agentSnapshots()) {
        totalFinalCash += snapshot.finalCash;
        // AgentSnapshot exports the primary asset's inventory.
        totalFinalAlphaShares += snapshot.finalStock;
    }

    const double expectedCash = static_cast<double>(agentCount) * config.initialCash;
    const double riskFreeGrowth =
        std::pow(1.0 + config.riskFreeRate, static_cast<double>(config.timeSteps));
    abm::test::expect(abm::test::nearlyEqual(totalFinalCash, expectedCash * riskFreeGrowth, 1e-6),
                      "aggregate cash should only change through risk-free accrual", failures);

    const double expectedAlphaShares =
        static_cast<double>(agentCount) * config.assets.at(0).initialStock;
    abm::test::expect(abm::test::nearlyEqual(totalFinalAlphaShares, expectedAlphaShares, 1e-6),
                      "executions should redistribute shares without creating or destroying them",
                      failures);
}

void testMultiAssetDeclarationPreservesLegacyTrajectory(int& failures) {
    const abm::SimulationConfig legacyConfig = abm::test::deterministicSmokeConfig();

    /*
     * Gate A: declaring the same single asset through the multi-asset config
     * path must reproduce the legacy scalar-config trajectory bit-for-bit.
     */
    abm::SimulationConfig declaredConfig = legacyConfig;
    abm::AssetDefinition asset;
    asset.name = legacyConfig.assetName();
    /*
     * Declared assets default to geometric Brownian motion, whereas the legacy
     * scalar keys are price-unit parameters for the arithmetic walk. Requesting
     * the arithmetic process explicitly is what makes the two paths comparable;
     * without it the declared asset would read the same numbers as log returns.
     */
    asset.fundamentalProcess = abm::FundamentalProcessType::ArithmeticRandomWalk;
    asset.initialPrice = legacyConfig.initialPrice();
    asset.initialStock = legacyConfig.initialStock();
    asset.priceTickSize = legacyConfig.priceTickSize();
    asset.fundamentalShockStdDev = legacyConfig.fundamentalShockStdDev();
    asset.fundamentalDriftPerStep = legacyConfig.fundamentalDriftPerStep();
    asset.minimumFundamentalValue = legacyConfig.minimumFundamentalValue();
    declaredConfig.assets.declare({asset});

    abm::SimulationEngine legacyEngine(legacyConfig);
    abm::SimulationEngine declaredEngine(declaredConfig);
    const abm::SimulationRunResult legacyResult = legacyEngine.run();
    const abm::SimulationRunResult declaredResult = declaredEngine.run();

    abm::test::expect(legacyResult.marketPriceHistory() == declaredResult.marketPriceHistory(),
                      "declared single-asset config should reproduce the legacy market price "
                      "series exactly",
                      failures);
    abm::test::expect(legacyResult.fundamentalPriceHistory() ==
                          declaredResult.fundamentalPriceHistory(),
                      "declared single-asset config should reproduce the legacy fundamental "
                      "series exactly",
                      failures);
    abm::test::expect(legacyResult.externalTradeLedger().size() ==
                          declaredResult.externalTradeLedger().size(),
                      "declared single-asset config should reproduce the legacy trade count",
                      failures);
}

void testSimulationIsSeedReproducible(int& failures) {
    const abm::SimulationConfig config = abm::test::deterministicSmokeConfig();

    abm::SimulationEngine firstEngine(config);
    abm::SimulationEngine secondEngine(config);
    const abm::SimulationRunResult first = firstEngine.run();
    const abm::SimulationRunResult second = secondEngine.run();

    const std::vector<double>& firstPrices = first.marketPriceHistory();
    const std::vector<double>& secondPrices = second.marketPriceHistory();
    const std::vector<double>& firstFundamentals = first.fundamentalPriceHistory();
    const std::vector<double>& secondFundamentals = second.fundamentalPriceHistory();

    abm::test::expect(first.stepDetails().size() == config.timeSteps,
                      "step details should contain one row per simulation step", failures);
    abm::test::expect(firstPrices.size() == secondPrices.size(),
                      "seeded simulations should produce price histories of equal length",
                      failures);
    abm::test::expect(firstFundamentals.size() == secondFundamentals.size(),
                      "seeded simulations should produce fundamental histories of equal length",
                      failures);
    abm::test::expect(firstPrices.size() == config.warmupSteps + config.timeSteps + 1,
                      "market history should include initial, warm-up, and simulation prices",
                      failures);
    abm::test::expect(first.stepDetails().size() == second.stepDetails().size(),
                      "seeded simulations should produce equal diagnostic row counts", failures);
    abm::test::expect(first.agentSnapshots().size() == second.agentSnapshots().size(),
                      "seeded simulations should produce equal final snapshot counts", failures);
    abm::test::expect(first.externalTradeLedger().size() == second.externalTradeLedger().size(),
                      "seeded simulations should produce equal trade-ledger lengths", failures);
    abm::test::expect(
        abm::test::nearlyEqual(first.stats().finalMarketPrice, second.stats().finalMarketPrice),
        "seeded simulations should have identical final market prices", failures);
    abm::test::expect(abm::test::nearlyEqual(first.stats().finalFundamentalPrice,
                                             second.stats().finalFundamentalPrice),
                      "seeded simulations should have identical final fundamental prices",
                      failures);

    const std::size_t comparedRows = std::min(firstPrices.size(), secondPrices.size());
    for (std::size_t i = 0; i < comparedRows; ++i) {
        abm::test::expect(std::isfinite(firstPrices[i]) && firstPrices[i] > 0.0,
                          "market prices should remain finite and positive", failures);
        abm::test::expect(abm::test::nearlyEqual(firstPrices[i], secondPrices[i]),
                          "seeded simulations should reproduce every market price", failures);
    }
    const std::size_t comparedFundamentalRows =
        std::min(firstFundamentals.size(), secondFundamentals.size());
    for (std::size_t i = 0; i < comparedFundamentalRows; ++i) {
        abm::test::expect(abm::test::nearlyEqual(firstFundamentals[i], secondFundamentals[i]),
                          "seeded simulations should reproduce every fundamental value", failures);
    }

    const std::size_t comparedStepRows =
        std::min(first.stepDetails().size(), second.stepDetails().size());
    for (std::size_t i = 0; i < comparedStepRows; ++i) {
        const abm::StepDetails& lhs = first.stepDetails()[i];
        const abm::StepDetails& rhs = second.stepDetails()[i];
        abm::test::expect(lhs.submittedOrders == rhs.submittedOrders &&
                              lhs.asset.executedTrades == rhs.asset.executedTrades,
                          "seeded simulations should reproduce order-count diagnostics", failures);
        abm::test::expect(
                abm::test::nearlyEqual(lhs.asset.marketPrice, rhs.asset.marketPrice) &&
                abm::test::nearlyEqual(lhs.asset.tradedVolume, rhs.asset.tradedVolume) &&
                abm::test::nearlyEqual(lhs.asset.realizedAllocativeSurplus,
                                       rhs.asset.realizedAllocativeSurplus) &&
                abm::test::nearlyEqual(lhs.asset.maximumAllocativeSurplus,
                                       rhs.asset.maximumAllocativeSurplus) &&
                abm::test::nearlyEqual(lhs.asset.allocativeEfficiency, rhs.asset.allocativeEfficiency) &&
                abm::test::nearlyEqual(lhs.wealthGiniCoefficient, rhs.wealthGiniCoefficient),
            "seeded simulations should reproduce per-step prices, volume, efficiency, and Gini",
            failures);
    }

    const std::size_t comparedSnapshots =
        std::min(first.agentSnapshots().size(), second.agentSnapshots().size());
    for (std::size_t i = 0; i < comparedSnapshots; ++i) {
        const abm::AgentSnapshot& lhs = first.agentSnapshots()[i];
        const abm::AgentSnapshot& rhs = second.agentSnapshots()[i];
        abm::test::expect(
            lhs.agentId == rhs.agentId && lhs.initialStrategyType == rhs.initialStrategyType,
            "seeded simulations should reproduce agent identities and strategies", failures);
        abm::test::expect(abm::test::nearlyEqual(lhs.finalCash, rhs.finalCash) &&
                              abm::test::nearlyEqual(lhs.finalStock, rhs.finalStock),
                          "seeded simulations should reproduce final agent balances", failures);
    }

    for (const abm::StepDetails& step : first.stepDetails()) {
        abm::test::expect(abm::test::nearlyEqual(step.asset.logReturn,
                                                 std::log(step.asset.marketPrice / step.asset.referencePrice),
                                                 1e-12),
                          "step diagnostics should expose realised log returns", failures);
        abm::test::expect(
            step.submittedOrders == step.asset.submittedLimitOrders + step.asset.submittedMarketOrders,
            "microstructure diagnostics should partition submitted order styles", failures);
        abm::test::expect(std::isfinite(step.asset.bestBid) && std::isfinite(step.asset.bestAsk) &&
                              std::isfinite(step.asset.bidAskSpread) && std::isfinite(step.asset.midQuote),
                          "book quote diagnostics should remain finite", failures);
        abm::test::expect(step.asset.bidDepth >= 0.0 && step.asset.askDepth >= 0.0,
                          "book depth diagnostics should be non-negative", failures);
        abm::test::expect(std::isfinite(step.wealthGiniCoefficient) &&
                              step.wealthGiniCoefficient >= 0.0 &&
                              step.wealthGiniCoefficient <= 1.0,
                          "wealth Gini diagnostics should remain finite and bounded", failures);
        abm::test::expect(std::isfinite(step.asset.realizedAllocativeSurplus) &&
                              std::isfinite(step.asset.maximumAllocativeSurplus) &&
                              std::isfinite(step.asset.allocativeEfficiency),
                          "allocative-efficiency diagnostics should remain finite", failures);
        abm::test::expect(step.asset.maximumAllocativeSurplus >= -1e-12,
                          "maximum allocative surplus should be non-negative", failures);
        if (step.asset.maximumAllocativeSurplus <= 1e-12) {
            abm::test::expect(abm::test::nearlyEqual(step.asset.allocativeEfficiency, 0.0),
                              "no-opportunity steps should export zero allocative efficiency",
                              failures);
        }
        if (step.asset.executedTrades > 0) {
            abm::test::expect(abm::test::nearlyEqual(step.asset.marketPrice, step.asset.lastTradePrice, 1e-12),
                              "last trade price should become the next market price", failures);
        } else {
            abm::test::expect(abm::test::nearlyEqual(step.asset.marketPrice, step.asset.referencePrice, 1e-12),
                              "no-trade steps should carry forward the previous price", failures);
        }
    }
}

void testDifferentSeedsProduceDivergentPricePaths(int& failures) {
    // Converse guard for testSimulationIsSeedReproducible: the replication
    // workflow (abm_analysis replicate) treats each seed as an independent
    // Monte Carlo draw. If the configured seed were silently ignored, every
    // "replicate" would be the same run and all cross-seed robustness
    // statistics would be meaningless while still looking perfectly stable.
    // The population and horizon are enlarged relative to the smoke config so
    // trades actually execute during the simulation phase; otherwise both
    // runs would carry warm-up prices forward with all-zero log returns and
    // the return-level divergence check below would be vacuous.
    abm::SimulationConfig baseConfig = abm::test::deterministicSmokeConfig();
    baseConfig.timeSteps = 20;
    baseConfig.numFundamentalists = 10;
    baseConfig.numChartists = 10;
    baseConfig.initialCash = 5000.0;
    abm::test::soleAsset(baseConfig).initialStock = 10.0;
    abm::SimulationConfig reseededConfig = baseConfig;
    reseededConfig.seed = baseConfig.seed + 1U;

    abm::SimulationEngine baseEngine(baseConfig);
    abm::SimulationEngine reseededEngine(reseededConfig);
    const abm::SimulationRunResult baseResult = baseEngine.run();
    const abm::SimulationRunResult reseededResult = reseededEngine.run();

    const std::vector<double>& basePrices = baseResult.marketPriceHistory();
    const std::vector<double>& reseededPrices = reseededResult.marketPriceHistory();
    abm::test::expect(basePrices.size() == reseededPrices.size(),
                      "different seeds should still produce histories of equal length",
                      failures);

    // Index 0 is the shared initial price; warm-up rows occupy indices
    // 1..warmupSteps and simulation rows follow. Divergence must appear in
    // the simulation phase as well, so a seed that only perturbed the warm-up
    // price process would still be caught.
    const std::size_t comparedRows = std::min(basePrices.size(), reseededPrices.size());
    const std::size_t firstSimulationRow = baseConfig.warmupSteps + 1;
    bool anyPriceDiffers = false;
    bool simulationPhasePriceDiffers = false;
    for (std::size_t i = 0; i < comparedRows; ++i) {
        if (!abm::test::nearlyEqual(basePrices[i], reseededPrices[i], 1e-12)) {
            anyPriceDiffers = true;
            if (i >= firstSimulationRow) {
                simulationPhasePriceDiffers = true;
            }
        }
    }
    abm::test::expect(anyPriceDiffers,
                      "different seeds should produce different market price paths", failures);
    abm::test::expect(simulationPhasePriceDiffers,
                      "different seeds should diverge within the simulation phase, not only "
                      "during warm-up",
                      failures);

    const std::size_t comparedStepRows =
        std::min(baseResult.stepDetails().size(), reseededResult.stepDetails().size());
    bool anyLogReturnDiffers = false;
    for (std::size_t i = 0; i < comparedStepRows; ++i) {
        if (!abm::test::nearlyEqual(baseResult.stepDetails()[i].asset.logReturn,
                                    reseededResult.stepDetails()[i].asset.logReturn,
                                    1e-12)) {
            anyLogReturnDiffers = true;
            break;
        }
    }
    abm::test::expect(anyLogReturnDiffers,
                      "different seeds should produce different per-step log returns", failures);
}

void testTradeLedgerToggleDoesNotChangeAggregateSimulation(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 20;
    config.numFundamentalists = 10;
    config.numChartists = 10;
    config.initialCash = 5000.0;
    abm::test::soleAsset(config).initialStock = 10.0;

    abm::SimulationEngine disabledLedgerEngine(config);
    abm::SimulationEngine enabledLedgerEngine(config);
    const abm::SimulationRunResult disabledLedgerResult = disabledLedgerEngine.run();
    const abm::SimulationRunResult enabledLedgerResult = enabledLedgerEngine.run({}, true);

    abm::test::expect(disabledLedgerResult.externalTradeLedger().empty(),
                      "disabled trade ledger should not collect audit rows", failures);
    abm::test::expect(!enabledLedgerResult.externalTradeLedger().empty(),
                      "enabled trade ledger should collect audit rows when trades execute",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(disabledLedgerResult.stats().finalMarketPrice,
                                             enabledLedgerResult.stats().finalMarketPrice),
                      "trade-ledger toggle should not change final market price", failures);
    abm::test::expect(abm::test::nearlyEqual(disabledLedgerResult.stats().totalTradedVolume,
                                             enabledLedgerResult.stats().totalTradedVolume),
                      "trade-ledger toggle should not change aggregate traded volume", failures);

    const std::vector<double>& disabledPrices = disabledLedgerResult.marketPriceHistory();
    const std::vector<double>& enabledPrices = enabledLedgerResult.marketPriceHistory();
    abm::test::expect(disabledPrices.size() == enabledPrices.size(),
                      "trade-ledger toggle should not change price-history length", failures);
    const std::size_t comparedPrices = std::min(disabledPrices.size(), enabledPrices.size());
    for (std::size_t index = 0; index < comparedPrices; ++index) {
        abm::test::expect(abm::test::nearlyEqual(disabledPrices[index], enabledPrices[index]),
                          "trade-ledger toggle should not change simulated prices", failures);
    }
}

void testNoiseTraderRunIsSeedReproducible(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 20;
    config.numFundamentalists = 0;
    config.numChartists = 0;
    config.numNoiseTraders = 12;
    config.initialCash = 5000.0;
    abm::test::soleAsset(config).initialStock = 5.0;
    config.shortSellingEnabled = false;
    config.social.enabled = false;

    abm::SimulationEngine firstEngine(config);
    abm::SimulationEngine secondEngine(config);
    const abm::SimulationRunResult first = firstEngine.run();
    const abm::SimulationRunResult second = secondEngine.run();

    abm::test::expect(
        abm::test::nearlyEqual(first.stats().finalMarketPrice, second.stats().finalMarketPrice),
        "seeded noise-trader simulations should have identical final market prices", failures);
    abm::test::expect(first.agentSnapshots().size() == config.numNoiseTraders,
                      "noise-trader simulations should export the configured noise population",
                      failures);
    for (const abm::AgentSnapshot& snapshot : first.agentSnapshots()) {
        abm::test::expect(snapshot.initialStrategyType == "noise_trader",
                          "noise-trader simulations should label noise agents in snapshots",
                          failures);
    }
}

void testMarketPriceOnlyChangesAfterExecutedTrades(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 6;
    config.numFundamentalists = 6;
    config.numChartists = 0;
    config.initialCash = 100000.0;
    abm::test::soleAsset(config).initialStock = 100.0;
    config.agentActivityRate = 0.0;
    abm::test::soleAsset(config).fundamentalShockStdDev = 0.25;
    config.warmupPriceProcess.noiseStdDev = 0.10;
    config.warmupPriceProcess.fundamentalPullStrength = 0.0;
    config.fundamentalist.mispricingThreshold = 0.0;

    abm::SimulationEngine simulation(config);

    const abm::SimulationRunResult simulationResult = simulation.run();
    const double preTradingMarketPrice = simulationResult.marketPriceHistory()[config.warmupSteps];

    abm::test::expect(simulationResult.stats().totalTradedVolume == 0.0,
                      "one-sided submitted orders should produce no executed trades", failures);
    abm::test::expect(simulationResult.stepDetails().size() == config.timeSteps,
                      "no-trade runs should still record one diagnostic row per step", failures);

    for (const abm::StepDetails& step : simulationResult.stepDetails()) {
        abm::test::expect(step.submittedOrders == 0,
                          "inactive agents should submit no orders in the no-trade regression",
                          failures);
        abm::test::expect(abm::test::nearlyEqual(step.notionalImbalance, 0.0, 1e-12),
                          "inactive agents should produce zero notional order imbalance", failures);
    }

    const std::vector<double>& prices = simulationResult.marketPriceHistory();
    const std::size_t firstSimulationPriceIndex = config.warmupSteps + 1;
    for (std::size_t priceIndex = firstSimulationPriceIndex; priceIndex < prices.size();
         ++priceIndex) {
        abm::test::expect(abm::test::nearlyEqual(prices[priceIndex], preTradingMarketPrice, 1e-12),
                          "market price should remain unchanged in no-trade steps", failures);
    }

    for (const abm::StepDetails& step : simulationResult.stepDetails()) {
        abm::test::expect(abm::test::nearlyEqual(step.asset.tradedVolume, 0.0),
                          "one-sided submitted orders should not clear any traded volume",
                          failures);
        abm::test::expect(abm::test::nearlyEqual(step.asset.marketPrice, step.asset.referencePrice, 1e-12),
                          "no-trade steps should carry forward the last realised price", failures);
        abm::test::expect(abm::test::nearlyEqual(step.asset.rawReturn, 0.0, 1e-12),
                          "no-trade steps should not realise a price return", failures);
        abm::test::expect(abm::test::nearlyEqual(step.asset.logReturn, 0.0, 1e-12),
                          "no-trade steps should not realise a log return", failures);
        abm::test::expect(abm::test::nearlyEqual(step.randomShock, 0.0, 1e-12),
                          "price noise should not be applied without an executed trade", failures);
        abm::test::expect(abm::test::nearlyEqual(step.wealthGiniCoefficient, 0.0, 1e-12),
                          "homogeneous no-trade runs should keep zero wealth inequality", failures);
    }
}

void testSocialDisabledBaselineStillTrades(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.social.enabled = false;
    config.timeSteps = 40;
    config.numFundamentalists = 40;
    config.numChartists = 60;

    abm::SimulationEngine simulation(config);
    const abm::SimulationRunResult simulationResult = simulation.run();

    double submittedOrders = 0.0;
    for (const abm::StepDetails& step : simulationResult.stepDetails()) {
        submittedOrders += static_cast<double>(step.submittedOrders);
    }

    abm::test::expect(submittedOrders > 0.0,
                      "social-disabled baseline should still submit valuation-based orders",
                      failures);
    abm::test::expect(simulationResult.stats().totalTradedVolume > 0.0,
                      "social-disabled baseline should still execute trades", failures);
}

void testInitialStrategyAssignmentDoesNotFollowIdBlocks(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 1;
    config.numFundamentalists = 40;
    config.numChartists = 40;
    config.numBuyAndHoldAgents = 20;
    config.seed = 20260508U;

    abm::SimulationEngine simulation(config);
    const abm::SimulationRunResult simulationResult = simulation.run();

    const std::vector<abm::AgentSnapshot>& snapshots = simulationResult.agentSnapshots();
    abm::test::expect(snapshots.size() == config.numFundamentalists + config.numChartists +
                                              config.numNoiseTraders + config.numBuyAndHoldAgents,
                      "agent snapshots should include the full unified population", failures);

    bool foundChartistInFormerFundamentalistIdBlock = false;
    bool foundFundamentalistAfterFormerIdBlock = false;
    bool foundBuyAndHold = false;
    for (const abm::AgentSnapshot& snapshot : snapshots) {
        if (snapshot.agentId <= config.numFundamentalists &&
            snapshot.initialStrategyType.rfind("chartist_", 0) == 0) {
            foundChartistInFormerFundamentalistIdBlock = true;
        }
        if (snapshot.agentId > config.numFundamentalists &&
            snapshot.initialStrategyType == "fundamentalist") {
            foundFundamentalistAfterFormerIdBlock = true;
        }
        foundBuyAndHold = foundBuyAndHold || snapshot.initialStrategyType == "buy_and_hold";
        abm::test::expect(snapshot.initialStrategyType == snapshot.currentStrategyType,
                          "strategy labels should remain unchanged before switching rules exist",
                          failures);
    }

    abm::test::expect(
        foundChartistInFormerFundamentalistIdBlock,
        "agent IDs should not reserve the first num_fundamentalists IDs for fundamentalists",
        failures);
    abm::test::expect(foundFundamentalistAfterFormerIdBlock,
                      "agent IDs should not reserve the final IDs for chartists", failures);
    abm::test::expect(foundBuyAndHold,
                      "initial strategy assignment should include buy-and-hold agents", failures);
}

void testBreakoutModeAndRandomChartistAssignment(int& failures) {
    abm::SimulationConfig breakoutConfig = abm::test::deterministicSmokeConfig();
    breakoutConfig.timeSteps = 1;
    breakoutConfig.numFundamentalists = 0;
    breakoutConfig.numChartists = 12;
    breakoutConfig.chartist.strategyMode = abm::ChartistStrategyMode::Breakout;

    abm::SimulationEngine breakoutSimulation(breakoutConfig);
    const abm::SimulationRunResult breakoutResult = breakoutSimulation.run();
    for (const abm::AgentSnapshot& snapshot : breakoutResult.agentSnapshots()) {
        abm::test::expect(snapshot.initialStrategyType == "chartist_breakout",
                          "explicit breakout mode should assign breakout chartist labels",
                          failures);
    }

    abm::SimulationConfig randomConfig = abm::test::deterministicSmokeConfig();
    randomConfig.timeSteps = 1;
    randomConfig.numFundamentalists = 0;
    randomConfig.numChartists = 60;
    randomConfig.chartist.strategyMode = abm::ChartistStrategyMode::Random;

    abm::SimulationEngine randomSimulation(randomConfig);
    const abm::SimulationRunResult randomResult = randomSimulation.run();
    bool foundRandomBreakout = false;
    for (const abm::AgentSnapshot& snapshot : randomResult.agentSnapshots()) {
        foundRandomBreakout =
            foundRandomBreakout || snapshot.initialStrategyType == "chartist_breakout";
    }
    abm::test::expect(foundRandomBreakout,
                      "random chartist mode should be able to sample breakout strategies",
                      failures);
}

void testAgentIdsRemainStableAcrossSimulationOutputs(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.timeSteps = 20;
    config.numFundamentalists = 10;
    config.numChartists = 10;
    config.initialCash = 5000.0;
    abm::test::soleAsset(config).initialStock = 10.0;

    abm::SimulationEngine simulation(config);
    const abm::SimulationRunResult simulationResult = simulation.run({}, true);

    const std::size_t expectedPopulation = config.numFundamentalists + config.numChartists +
                                           config.numNoiseTraders + config.numBuyAndHoldAgents;
    std::vector<bool> snapshotIds(expectedPopulation + 1, false);
    for (const abm::AgentSnapshot& snapshot : simulationResult.agentSnapshots()) {
        const bool idInRange = snapshot.agentId >= 1 && snapshot.agentId <= expectedPopulation;
        abm::test::expect(
            idInRange, "snapshot agent IDs should stay inside the configured population", failures);
        if (idInRange) {
            abm::test::expect(!snapshotIds[snapshot.agentId],
                              "each persistent agent ID should appear once in snapshots", failures);
            snapshotIds[snapshot.agentId] = true;
        }
        abm::test::expect(!snapshot.initialStrategyType.empty() &&
                              !snapshot.currentStrategyType.empty(),
                          "snapshot should expose initial and current strategy labels", failures);
    }

    for (std::size_t agentId = 1; agentId <= expectedPopulation; ++agentId) {
        abm::test::expect(snapshotIds[agentId],
                          "every persistent agent ID should be exported in final snapshots",
                          failures);
    }

    for (const abm::ExternalTradeLedgerRecord& record : simulationResult.externalTradeLedger()) {
        abm::test::expect(record.agentId >= 1 && record.agentId <= expectedPopulation,
                          "trade ledger agent IDs should refer to persistent agents", failures);
        if (record.counterpartyAgentId != 0U) {
            abm::test::expect(
                record.counterpartyAgentId >= 1 && record.counterpartyAgentId <= expectedPopulation,
                "trade ledger counterparty IDs should refer to persistent agents", failures);
        }
    }
}

void testProspectTheoryRunExportsAgentSpecificReferencePoints(int& failures) {
    abm::SimulationConfig config = abm::test::deterministicSmokeConfig();
    config.control.prospectTheoryEnabled = true;
    config.control.referencePointMode = abm::ProspectReferencePointMode::AveragePurchasePrice;
    config.timeSteps = 30;
    config.initialCash = 5000.0;
    abm::test::soleAsset(config).initialStock = 5.0;

    abm::SimulationEngine simulation(config);
    const abm::SimulationRunResult simulationResult = simulation.run();

    bool foundResolvedReference = false;
    for (const abm::AgentSnapshot& snapshot : simulationResult.agentSnapshots()) {
        foundResolvedReference =
            foundResolvedReference || (std::isfinite(snapshot.lastProspectReferencePoint) &&
                                       snapshot.lastProspectReferencePoint > 0.0);
        abm::test::expect(
            std::isfinite(snapshot.recentPeakWealth) && snapshot.recentPeakWealth > 0.0,
            "Prospect Theory snapshots should expose each agent's peak wealth reference state",
            failures);
    }

    abm::test::expect(foundResolvedReference,
                      "Prospect Theory run should resolve at least one agent-specific reference "
                      "point during trading",
                      failures);
}

void testLimitOrderBookExecutionRespectsPortfolioConstraints(int& failures) {
    abm::SimulationConfig noShortConfig = abm::test::deterministicSmokeConfig();
    noShortConfig.timeSteps = 35;
    noShortConfig.numFundamentalists = 20;
    noShortConfig.numChartists = 20;
    noShortConfig.initialCash = 400.0;
    abm::test::soleAsset(noShortConfig).initialStock = 3.0;
    noShortConfig.shortSellingEnabled = false;
    noShortConfig.agentActivityRate = 1.0;

    abm::SimulationEngine noShortSimulation(noShortConfig);
    const abm::SimulationRunResult noShortResult = noShortSimulation.run();
    for (const abm::AgentSnapshot& snapshot : noShortResult.agentSnapshots()) {
        abm::test::expect(snapshot.finalCash >= -1e-8,
                          "LOB execution should not spend more cash than the buyer has", failures);
        abm::test::expect(snapshot.finalStock >= -1e-8,
                          "LOB execution should not create short inventory when shorts are off",
                          failures);
    }

    abm::SimulationConfig shortConfig = abm::test::deterministicSmokeConfig();
    shortConfig.timeSteps = 35;
    shortConfig.numFundamentalists = 20;
    shortConfig.numChartists = 20;
    shortConfig.initialCash = 2500.0;
    abm::test::soleAsset(shortConfig).initialStock = 5.0;
    shortConfig.shortSellingEnabled = true;
    shortConfig.shortSale.borrowableSupplyRatio = 0.10;
    shortConfig.agentActivityRate = 1.0;

    abm::SimulationEngine shortSimulation(shortConfig);
    const abm::SimulationRunResult shortResult = shortSimulation.run();

    double aggregateShortInterest = 0.0;
    for (const abm::AgentSnapshot& snapshot : shortResult.agentSnapshots()) {
        aggregateShortInterest += std::max(0.0, -snapshot.finalStock);
        abm::test::expect(snapshot.finalCash >= -1e-8,
                          "short-enabled LOB execution should not create negative cash balances",
                          failures);
    }

    const double borrowableSupply =
        static_cast<double>(shortConfig.numFundamentalists + shortConfig.numChartists +
                            shortConfig.numNoiseTraders + shortConfig.numBuyAndHoldAgents) *
        shortConfig.initialStock() * shortConfig.shortSale.borrowableSupplyRatio;
    abm::test::expect(aggregateShortInterest <= borrowableSupply + 1e-8,
                      "LOB short execution should respect the aggregate borrowable supply cap",
                      failures);
}

} // namespace

namespace abm::test {

void runSimulationIntegrationTests(int& failures) {
    testTwoAssetRunProducesIndependentPerAssetOutput(failures);
    testTwoAssetRunConservesCashAndShares(failures);
    testMultiAssetDeclarationPreservesLegacyTrajectory(failures);
    testSimulationIsSeedReproducible(failures);
    testDifferentSeedsProduceDivergentPricePaths(failures);
    testTradeLedgerToggleDoesNotChangeAggregateSimulation(failures);
    testNoiseTraderRunIsSeedReproducible(failures);
    testMarketPriceOnlyChangesAfterExecutedTrades(failures);
    testSocialDisabledBaselineStillTrades(failures);
    testInitialStrategyAssignmentDoesNotFollowIdBlocks(failures);
    testBreakoutModeAndRandomChartistAssignment(failures);
    testAgentIdsRemainStableAcrossSimulationOutputs(failures);
    testProspectTheoryRunExportsAgentSpecificReferencePoints(failures);
    testLimitOrderBookExecutionRespectsPortfolioConstraints(failures);
}

} // namespace abm::test
