#include "tests/cpp/TestSupport.h"

#include "Application/CliOptions.h"
#include "Config/SimulationConfigIO.h"
#include "Config/SimulationConfigValidation.h"

#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void testRuntimeConfigParsesProspectTheoryToggle(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_toggle_test.cfg";

    {
        std::ofstream out(configPath);
        out << "control_prospect_theory_enabled = 0\n";
        out << "control_prospect_theory_agent_fraction = 0.40\n";
        out << "control_prospect_heterogeneity_enabled = 1\n";
        out << "control_loss_aversion_std_dev = 0.25\n";
        out << "control_curvature_for_gain_std_dev = 0.05\n";
        out << "control_curvature_for_loss_std_dev = 0.05\n";
        out << "control_probability_distortion_min = 0.65\n";
        out << "control_probability_distortion_max = 0.85\n";
        out << "control_reference_point_mode = moving_average_price\n";
        out << "control_reference_moving_average_window = 17\n";
        out << "control_prospect_scenario_count = 5\n";
        out << "market_microstructure = continuous_lob\n";
        out << "order_expiry_steps = 9\n";
        out << "cancellation_base_probability = 0.03\n";
        out << "cancellation_mispricing_sensitivity = 1.50\n";
        out << "market_order_probability = 0.07\n";
        out << "market_order_log_gap_threshold = 0.04\n";
        out << "book_depth_levels = 7\n";
        out << "transaction_cost_rate = 0.0025\n";
        out << "transaction_cost_affects_decisions = 0\n";
        out << "transaction_cost_apply_to_forced_buy_ins = 1\n";
        out << "fundamental_drift_per_step = 0.012\n";
        out << "minimum_fundamental_value = 2.50\n";
        out << "warmup_price_noise_std_dev = 0.004\n";
        out << "warmup_fundamental_pull_strength = 0.06\n";
        out << "chartist_momentum_signal_threshold = 0.015\n";
        out << "chartist_breakout_window = 13\n";
        out << "chartist_strategy_mode = breakout\n";
        out << "num_noise_traders = 7\n";
        out << "num_buy_and_hold_agents = 3\n";
        out << "noise_trader_belief_shock_std_dev = 0.031\n";
        out << "noise_trader_order_size_fraction = 0.075\n";
        out << "noise_trader_max_short_weight = 0.18\n";
        out << "buy_hold_target_risky_weight = 0.60\n";
        out << "simulation_csv_output = simulation.csv\n";
        out << "agent_csv_output = agents.csv\n";
        out << "trade_ledger_enabled = 1\n";
        out << "trade_ledger_csv_output = trades.csv\n";
        out << "summary_metrics_csv_output = summary_metrics.csv\n";
        out << "stylised_facts_csv_output = stylised_facts.csv\n";
        out << "config_json_output = config.json\n";
        out << "metadata_json_output = metadata.json\n";
        out << "run_log_output = run.log\n";
        out << "database_output_enabled = 1\n";
        out << "database_url_env = ABM_TEST_DATABASE_URL\n";
        out << "database_prune_after_import = 1\n";
        out << "python_analysis_python = python3\n";
    }

    try {
        const abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        abm::test::expect(!runtimeConfig.simulation.control.prospectTheoryEnabled,
                          "config parser should read control_prospect_theory_enabled = 0",
                          failures);
        abm::test::expect(abm::test::nearlyEqual(
                              runtimeConfig.simulation.control.prospectTheoryAgentFraction, 0.40),
                          "config parser should read control_prospect_theory_agent_fraction",
                          failures);
        abm::test::expect(runtimeConfig.simulation.control.prospectParameterHeterogeneityEnabled,
                          "config parser should read control_prospect_heterogeneity_enabled = 1",
                          failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.control.lossAversionStdDev, 0.25),
            "config parser should read heterogeneous loss-aversion spread", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.control.probabilityDistortionMin, 0.65),
            "config parser should read heterogeneous gamma minimum", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.control.probabilityDistortionMax, 0.85),
            "config parser should read heterogeneous gamma maximum", failures);
        abm::test::expect(runtimeConfig.simulation.control.prospectScenarioCount == 5,
                          "config parser should read the CPT scenario count", failures);
        abm::test::expect(runtimeConfig.simulation.control.referencePointMode ==
                              abm::ProspectReferencePointMode::MovingAveragePrice,
                          "config parser should read the CPT reference-point mode", failures);
        abm::test::expect(runtimeConfig.simulation.control.referenceMovingAverageWindow == 17,
                          "config parser should read the CPT moving-average reference window",
                          failures);
        abm::test::expect(runtimeConfig.simulation.microstructure.mode ==
                              abm::MarketMicrostructureMode::ContinuousLimitOrderBook,
                          "config parser should read continuous LOB market microstructure",
                          failures);
        abm::test::expect(runtimeConfig.simulation.microstructure.orderExpirySteps == 9,
                          "config parser should read LOB order expiry steps", failures);
        abm::test::expect(
            abm::test::nearlyEqual(
                runtimeConfig.simulation.microstructure.cancellationBaseProbability, 0.03),
            "config parser should read the cancellation base probability", failures);
        abm::test::expect(
            abm::test::nearlyEqual(
                runtimeConfig.simulation.microstructure.cancellationMispricingSensitivity, 1.50),
            "config parser should read the stale-order mispricing sensitivity", failures);
        abm::test::expect(abm::test::nearlyEqual(
                              runtimeConfig.simulation.microstructure.marketOrderProbability, 0.07),
                          "config parser should read the random market-order probability",
                          failures);
        abm::test::expect(
            abm::test::nearlyEqual(
                runtimeConfig.simulation.microstructure.marketOrderLogGapThreshold, 0.04),
            "config parser should read the market-order log-gap threshold", failures);
        abm::test::expect(runtimeConfig.simulation.microstructure.bookDepthLevels == 7,
                          "config parser should read the exported book depth levels", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.transactionCosts.rate, 0.0025),
            "config parser should read the proportional transaction-cost rate", failures);
        abm::test::expect(!runtimeConfig.simulation.transactionCosts.affectsDecisions,
                          "config parser should read transaction-cost decision toggle", failures);
        abm::test::expect(runtimeConfig.simulation.transactionCosts.applyToForcedBuyIns,
                          "config parser should read transaction-cost forced-buy-in toggle",
                          failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.fundamentalDriftPerStep(), 0.012),
            "config parser should read the fundamental drift per step", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.minimumFundamentalValue(), 2.50),
            "config parser should read the minimum fundamental value", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.warmupPriceProcess.noiseStdDev, 0.004),
            "config parser should read warm-up price noise as warm-up-only", failures);
        abm::test::expect(
            abm::test::nearlyEqual(
                runtimeConfig.simulation.warmupPriceProcess.fundamentalPullStrength, 0.06),
            "config parser should read warm-up fundamental pull as warm-up-only", failures);
        abm::test::expect(abm::test::nearlyEqual(
                              runtimeConfig.simulation.chartist.momentumSignalThreshold, 0.015),
                          "config parser should read the chartist momentum signal threshold",
                          failures);
        abm::test::expect(runtimeConfig.simulation.chartist.breakoutWindow == 13,
                          "config parser should read the chartist breakout window", failures);
        abm::test::expect(
            runtimeConfig.simulation.chartist.strategyMode == abm::ChartistStrategyMode::Breakout,
            "config parser should read the breakout chartist strategy mode", failures);
        abm::test::expect(runtimeConfig.simulation.numNoiseTraders == 7,
                          "config parser should read the noise-trader population count", failures);
        abm::test::expect(runtimeConfig.simulation.numBuyAndHoldAgents == 3,
                          "config parser should read the buy-and-hold population count", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.noiseTrader.beliefShockStdDev, 0.031),
            "config parser should read the noise-trader belief-shock scale", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.noiseTrader.orderSizeFraction, 0.075),
            "config parser should read the noise-trader order-size fraction", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.noiseTrader.maxShortWeight, 0.18),
            "config parser should read the noise-trader short-exposure cap", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.buyAndHold.targetRiskyWeight, 0.60),
            "config parser should read the buy-and-hold target risky weight", failures);
        abm::test::expect(
            std::filesystem::path(runtimeConfig.output.summaryMetricsCsvPath).filename() ==
                "summary_metrics.csv",
            "config parser should read the summary metrics output path", failures);
        abm::test::expect(
            std::filesystem::path(runtimeConfig.output.stylisedFactsCsvPath).filename() ==
                "stylised_facts.csv",
            "config parser should read the stylised-facts output path", failures);
        abm::test::expect(runtimeConfig.output.tradeLedgerEnabled,
                          "config parser should read trade_ledger_enabled = 1", failures);
        abm::test::expect(
            std::filesystem::path(runtimeConfig.output.configJsonPath).filename() == "config.json",
            "config parser should read the normalised config JSON output path", failures);
        abm::test::expect(std::filesystem::path(runtimeConfig.output.metadataJsonPath).filename() ==
                              "metadata.json",
                          "config parser should read the metadata JSON output path", failures);
        abm::test::expect(std::filesystem::path(runtimeConfig.output.runLogPath).filename() ==
                              "run.log",
                          "config parser should read the run-log output path", failures);
        abm::test::expect(runtimeConfig.output.databaseOutputEnabled,
                          "config parser should read database_output_enabled = 1", failures);
        abm::test::expect(
            runtimeConfig.output.databaseUrlEnvironmentVariable == "ABM_TEST_DATABASE_URL",
            "config parser should read the database URL environment variable", failures);
        abm::test::expect(runtimeConfig.output.databasePruneAfterImport,
                          "config parser should read database_prune_after_import = 1", failures);
        abm::test::expect(runtimeConfig.output.pythonAnalysisPythonPath == "python3",
                          "config parser should read the Python analysis interpreter", failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: config parser should accept control_prospect_theory_enabled: "
                  << error.what() << '\n';
        ++failures;
    }

    std::filesystem::remove(configPath);
}

void testRuntimeConfigRejectsInvalidReferencePointMode(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_bad_reference_mode_test.cfg";

    {
        std::ofstream out(configPath);
        out << "control_reference_point_mode = unsupported_anchor\n";
    }

    try {
        const abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        static_cast<void>(runtimeConfig);
        abm::test::expect(false, "config parser should reject invalid CPT reference-point modes",
                          failures);
    } catch (const std::invalid_argument& error) {
        abm::test::expect(
            std::string(error.what()).find("control_reference_point_mode") != std::string::npos,
            "invalid CPT reference-point mode error should name the bad key", failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: invalid CPT reference-point mode should throw invalid_argument: "
                  << error.what() << '\n';
        ++failures;
    }

    std::filesystem::remove(configPath);
}

void testRuntimeConfigRejectsInvalidMarketMicrostructure(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_bad_microstructure_test.cfg";

    {
        std::ofstream out(configPath);
        out << "market_microstructure = batch_auction\n";
    }

    try {
        const abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        static_cast<void>(runtimeConfig);
        abm::test::expect(false, "config parser should reject unsupported microstructure modes",
                          failures);
    } catch (const std::invalid_argument& error) {
        abm::test::expect(std::string(error.what()).find("market_microstructure") !=
                              std::string::npos,
                          "invalid market microstructure error should name the bad key", failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: invalid microstructure mode should throw invalid_argument: "
                  << error.what() << '\n';
        ++failures;
    }

    std::filesystem::remove(configPath);
}

void testRuntimeConfigRejectsRetiredPriceImpactControls(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_retired_price_impact_test.cfg";

    {
        std::ofstream out(configPath);
        out << "price_noise_std_dev = 0.005\n";
    }

    try {
        const abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        static_cast<void>(runtimeConfig);
        abm::test::expect(false, "config parser should reject legacy active-looking price noise",
                          failures);
    } catch (const std::invalid_argument& error) {
        abm::test::expect(
            std::string(error.what()).find("warmup_price_noise_std_dev") != std::string::npos,
            "legacy price noise error should point to the warm-up-only replacement", failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: legacy price noise should throw invalid_argument: " << error.what()
                  << '\n';
        ++failures;
    }

    {
        std::ofstream out(configPath);
        out << "order_imbalance_impact = 0.05\n";
    }

    try {
        const abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        static_cast<void>(runtimeConfig);
        abm::test::expect(false, "config parser should reject removed order-impact controls",
                          failures);
    } catch (const std::invalid_argument& error) {
        abm::test::expect(
            std::string(error.what()).find("realised transaction prices") != std::string::npos,
            "removed order-impact error should explain continuous LOB price formation", failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: removed order-impact control should throw invalid_argument: "
                  << error.what() << '\n';
        ++failures;
    }

    std::filesystem::remove(configPath);
}

void testRuntimeConfigParsesShortSaleConstraints(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_short_sale_test.cfg";

    {
        std::ofstream out(configPath);
        out << "short_selling_enabled = 1\n";
        out << "short_sale_initial_margin_requirement = 0.55\n";
        out << "short_sale_maintenance_margin_requirement = 0.35\n";
        out << "short_sale_borrowable_supply_ratio = 0.25\n";
        out << "simulation_csv_output = simulation.csv\n";
        out << "agent_csv_output = agents.csv\n";
        out << "trade_ledger_csv_output = trades.csv\n";
    }

    try {
        const abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        abm::test::expect(runtimeConfig.simulation.shortSellingEnabled,
                          "config parser should read short_selling_enabled = 1", failures);
        abm::test::expect(abm::test::nearlyEqual(
                              runtimeConfig.simulation.shortSale.initialMarginRequirement, 0.55),
                          "config parser should read short-sale initial margin", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.shortSale.maintenanceMarginRequirement,
                                   0.35),
            "config parser should read short-sale maintenance margin", failures);
        abm::test::expect(
            abm::test::nearlyEqual(runtimeConfig.simulation.shortSale.borrowableSupplyRatio, 0.25),
            "config parser should read short-sale borrowable supply ratio", failures);
        abm::test::expect(!runtimeConfig.output.tradeLedgerEnabled,
                          "trade ledger recording should default to disabled", failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: config parser should accept short-sale constraints: " << error.what()
                  << '\n';
        ++failures;
    }

    std::filesystem::remove(configPath);
}

void testCommandLineAcceptsOnlyConfigForms(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_cli_config_test.cfg";

    {
        std::ofstream out(configPath);
        out << "time_steps = 17\n";
        out << "simulation_csv_output = cli_step_timeseries.csv\n";
        out << "agent_csv_output = cli_agents_final.csv\n";
        out << "trade_ledger_csv_output = cli_trade_ledger.csv\n";
    }

    try {
        std::string programName = "simulate";
        std::string configFlag = "--config";
        std::string configPathText = configPath.string();
        char* explicitConfigArgv[] = {
            programName.data(),
            configFlag.data(),
            configPathText.data(),
        };

        const abm::CliParseResult explicitConfigResult =
            abm::parseSimulationCommandLine(3, explicitConfigArgv);
        abm::test::expect(!explicitConfigResult.shouldExit,
                          "CLI should accept --config <config_file>", failures);
        abm::test::expect(explicitConfigResult.runtimeConfig.simulation.timeSteps == 17,
                          "CLI --config form should load the requested config file", failures);

        std::string directProgramName = "simulate";
        std::string directConfigPathText = configPath.string();
        char* directConfigArgv[] = {
            directProgramName.data(),
            directConfigPathText.data(),
        };

        const abm::CliParseResult directConfigResult =
            abm::parseSimulationCommandLine(2, directConfigArgv);
        abm::test::expect(!directConfigResult.shouldExit,
                          "CLI should accept a single config-file argument", failures);
        abm::test::expect(directConfigResult.runtimeConfig.simulation.timeSteps == 17,
                          "CLI direct config form should load the requested config file", failures);

        std::string legacyProgramName = "simulate";
        std::string legacyTimeSteps = "17";
        std::string legacyFundamentalists = "4";
        std::string legacyChartists = "5";
        std::string legacySeed = "123";
        char* legacyArgv[] = {
            legacyProgramName.data(), legacyTimeSteps.data(), legacyFundamentalists.data(),
            legacyChartists.data(),   legacySeed.data(),
        };

        // Both streams are captured: the usage block goes to stdout and the
        // reason for the rejection goes to stderr.
        std::ostringstream capturedUsage;
        std::ostringstream capturedReason;
        std::streambuf* originalCoutBuffer = std::cout.rdbuf(capturedUsage.rdbuf());
        std::streambuf* originalCerrBuffer = std::cerr.rdbuf(capturedReason.rdbuf());
        const abm::CliParseResult legacyResult = abm::parseSimulationCommandLine(5, legacyArgv);
        std::cout.rdbuf(originalCoutBuffer);
        std::cerr.rdbuf(originalCerrBuffer);
        abm::test::expect(legacyResult.shouldExit && legacyResult.exitCode == 1,
                          "CLI should reject the removed positional override form", failures);

        std::string validateProgramName = "simulate";
        std::string validateFlag = "--validate";
        std::string quietFlag = "--quiet-progress";
        std::string validateConfigFlag = "--config";
        std::string validateConfigPathText = configPath.string();
        char* validateArgv[] = {
            validateProgramName.data(), validateFlag.data(),           quietFlag.data(),
            validateConfigFlag.data(),  validateConfigPathText.data(),
        };

        const abm::CliParseResult validateResult = abm::parseSimulationCommandLine(5, validateArgv);
        abm::test::expect(!validateResult.shouldExit &&
                              validateResult.mode == abm::SimulationRunMode::Validate,
                          "CLI should accept --validate alongside a config file", failures);
        abm::test::expect(validateResult.quietProgress,
                          "CLI should accept --quiet-progress as a presentation flag", failures);
        abm::test::expect(validateResult.runtimeConfig.simulation.timeSteps == 17,
                          "--validate should still load the requested config file", failures);
        abm::test::expect(validateResult.diagnostics.empty(),
                          "a valid config should validate without diagnostics", failures);

        std::string unknownProgramName = "simulate";
        std::string unknownFlag = "--not-a-real-option";
        char* unknownArgv[] = {unknownProgramName.data(), unknownFlag.data()};

        std::ostringstream discardedUsage;
        std::ostringstream discardedReason;
        originalCoutBuffer = std::cout.rdbuf(discardedUsage.rdbuf());
        originalCerrBuffer = std::cerr.rdbuf(discardedReason.rdbuf());
        const abm::CliParseResult unknownResult = abm::parseSimulationCommandLine(2, unknownArgv);
        std::cout.rdbuf(originalCoutBuffer);
        std::cerr.rdbuf(originalCerrBuffer);
        abm::test::expect(unknownResult.shouldExit && unknownResult.exitCode == 1,
                          "CLI should reject an unknown option", failures);
        abm::test::expect(discardedReason.str().find("--not-a-real-option") != std::string::npos,
                          "CLI should name the unknown option it rejected", failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: CLI config forms should parse cleanly: " << error.what() << '\n';
        ++failures;
    }

    std::filesystem::remove(configPath);
}

void testRuntimeConfigParsesMultiAssetDeclaration(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_multi_asset_test.cfg";

    {
        std::ofstream out(configPath);
        out << "assets = alpha, beta\n";
        out << "primary_asset = beta\n";
        out << "asset.alpha.initial_price = 105.0\n";
        out << "asset.alpha.initial_stock = 5.0\n";
        out << "asset.alpha.price_tick_size = 0.05\n";
        out << "asset.alpha.fundamental_shock_std_dev = 0.04\n";
        out << "asset.alpha.fundamental_drift_per_step = 0.002\n";
        out << "asset.alpha.minimum_fundamental_value = 2.0\n";
        out << "asset.beta.initial_price = 40.0\n";
        out << "asset.beta.initial_stock = 10.0\n";
    }

    try {
        abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        abm::SimulationConfig& simulation = runtimeConfig.simulation;

        abm::test::expect(simulation.assets.size() == 2 && simulation.assets[0].name == "alpha" &&
                              simulation.assets[1].name == "beta",
                          "assets declaration should create definitions in declared order",
                          failures);
        abm::test::expect(
            abm::test::nearlyEqual(simulation.assets[0].initialPrice, 105.0) &&
                abm::test::nearlyEqual(simulation.assets[0].initialStock, 5.0) &&
                abm::test::nearlyEqual(simulation.assets[0].priceTickSize, 0.05) &&
                abm::test::nearlyEqual(simulation.assets[0].fundamentalShockStdDev, 0.04) &&
                abm::test::nearlyEqual(simulation.assets[0].fundamentalDriftPerStep, 0.002) &&
                abm::test::nearlyEqual(simulation.assets[0].minimumFundamentalValue, 2.0),
            "per-asset keys should populate the named asset definition", failures);
        abm::test::expect(abm::test::nearlyEqual(simulation.assets[1].initialPrice, 40.0) &&
                              abm::test::nearlyEqual(simulation.assets[1].initialStock, 10.0),
                          "second asset should receive its own parameters", failures);

        abm::validateSimulationConfig(simulation);
        abm::normaliseSimulationConfig(simulation);
        abm::test::expect(simulation.assets.primaryIndex() == 1 &&
                              simulation.assetName() == "beta" &&
                              abm::test::nearlyEqual(simulation.initialPrice(), 40.0) &&
                              abm::test::nearlyEqual(simulation.initialStock(), 10.0),
                          "normalisation should resolve the primary asset and mirror its "
                          "parameters into the legacy scalars",
                          failures);
    } catch (const std::exception& error) {
        std::cerr << "Unexpected multi-asset parse failure: " << error.what() << '\n';
        abm::test::expect(false, "multi-asset declaration should parse and normalise", failures);
    }

    std::filesystem::remove(configPath);
}

void testRuntimeConfigRejectsMalformedAssetKeys(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_bad_asset_keys_test.cfg";

    const auto expectParseFailure = [&](const std::string& contents, const char* description) {
        {
            std::ofstream out(configPath);
            out << contents;
        }
        bool threw = false;
        try {
            const abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
            (void)runtimeConfig;
        } catch (const std::exception&) {
            threw = true;
        }
        abm::test::expect(threw, description, failures);
    };

    expectParseFailure("asset.alpha.initial_price = 100.0\n",
                       "per-asset keys should be rejected before an assets declaration");
    expectParseFailure("assets = alpha\nassets = beta\n",
                       "duplicate assets declarations should be rejected");
    expectParseFailure("assets = alpha, alpha\n",
                       "duplicate asset names in one declaration should be rejected");
    expectParseFailure("assets = alpha,\n", "empty asset names should be rejected");
    expectParseFailure("assets = alpha\nasset.alpha.unknown_parameter = 1.0\n",
                       "unknown per-asset parameters should be rejected");
    expectParseFailure("assets = alpha\nasset.beta.initial_price = 10.0\n",
                       "per-asset keys must reference a declared asset");

    std::filesystem::remove(configPath);
}

void testMultiAssetConfigRejectsLegacyScalarMixing(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_mixed_asset_test.cfg";

    {
        std::ofstream out(configPath);
        out << "assets = alpha\n";
        out << "initial_price = 100.0\n";
    }

    bool threw = false;
    try {
        abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        abm::validateSimulationConfig(runtimeConfig.simulation);
    } catch (const std::invalid_argument& error) {
        threw = std::string(error.what()).find("initial_price") != std::string::npos;
    }
    abm::test::expect(threw,
                      "validation should reject configs mixing an assets declaration with "
                      "legacy scalar asset keys and name the offending key",
                      failures);

    std::filesystem::remove(configPath);
}

} // namespace

namespace abm::test {

/**
 * Verifies the Asset B controls: process type, correlation, and enable toggle.
 *
 * The disabled asset must disappear from the tradable list while remaining
 * recorded in the universe's disabled list, so a run can collapse onto the single-asset
 * model without losing the provenance that Asset B was configured.
 */
void testRuntimeConfigParsesAssetProcessAndToggle(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_asset_process_test.cfg";

    {
        std::ofstream out(configPath);
        out << "assets = alpha, beta\n";
        out << "primary_asset = alpha\n";
        out << "asset_fundamental_correlation = 0.35\n";
        out << "asset.alpha.initial_price = 100.0\n";
        out << "asset.alpha.fundamental_process = random_walk\n";
        out << "asset.beta.initial_price = 40.0\n";
        out << "asset.beta.fundamental_process = gbm\n";
        out << "asset.beta.fundamental_shock_std_dev = 0.02\n";
        out << "asset.beta.fundamental_drift_per_step = 0.0005\n";
    }

    try {
        abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        abm::SimulationConfig& simulation = runtimeConfig.simulation;

        abm::test::expect(simulation.assets.size() == 2 &&
                              simulation.assets[0].fundamentalProcess ==
                                  abm::FundamentalProcessType::ArithmeticRandomWalk &&
                              simulation.assets[1].fundamentalProcess ==
                                  abm::FundamentalProcessType::GeometricBrownianMotion,
                          "per-asset fundamental_process should select the named process",
                          failures);
        abm::test::expect(abm::test::nearlyEqual(simulation.assetFundamentalCorrelation, 0.35),
                          "asset_fundamental_correlation should parse into the simulation config",
                          failures);

        abm::validateSimulationConfig(simulation);
        abm::normaliseSimulationConfig(simulation);
        abm::test::expect(simulation.assets.size() == 2 && simulation.assets.disabled().empty(),
                          "enabled assets should survive normalisation", failures);
    } catch (const std::exception& error) {
        std::cerr << "Unexpected asset-process parse failure: " << error.what() << '\n';
        abm::test::expect(false, "asset process configuration should parse", failures);
    }

    std::filesystem::remove(configPath);
}

/**
 * Geometric Brownian motion is the model's fundamental-value theory, so every
 * declared asset must adopt it without having to say so. The legacy scalar
 * keys are exempt: they are price-unit parameters written for the arithmetic
 * walk, and reading them as log returns would silently inflate the shock by
 * the price level.
 */
void testDeclaredAssetsDefaultToGeometricBrownianMotion(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_asset_default_process_test.cfg";

    {
        std::ofstream out(configPath);
        out << "assets = alpha, beta\n";
        out << "asset.alpha.initial_price = 100.0\n";
        out << "asset.beta.initial_price = 40.0\n";
    }

    try {
        abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        abm::test::expect(runtimeConfig.simulation.assets.size() == 2 &&
                              runtimeConfig.simulation.assets[0].fundamentalProcess ==
                                  abm::FundamentalProcessType::GeometricBrownianMotion &&
                              runtimeConfig.simulation.assets[1].fundamentalProcess ==
                                  abm::FundamentalProcessType::GeometricBrownianMotion,
                          "declared assets should default to geometric Brownian motion", failures);
    } catch (const std::exception& error) {
        std::cerr << "Unexpected default-process failure: " << error.what() << '\n';
        abm::test::expect(false, "default asset process configuration should parse", failures);
    }

    {
        std::ofstream out(configPath);
        out << "initial_price = 100.0\n";
        out << "fundamental_shock_std_dev = 0.03\n";
    }

    try {
        abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        abm::normaliseSimulationConfig(runtimeConfig.simulation);
        abm::test::expect(runtimeConfig.simulation.assets.size() == 1 &&
                              runtimeConfig.simulation.assets[0].fundamentalProcess ==
                                  abm::FundamentalProcessType::ArithmeticRandomWalk,
                          "legacy scalar configs should stay on the arithmetic random walk",
                          failures);
    } catch (const std::exception& error) {
        std::cerr << "Unexpected legacy-process failure: " << error.what() << '\n';
        abm::test::expect(false, "legacy scalar configuration should normalise", failures);
    }

    std::filesystem::remove(configPath);
}

void testDisabledAssetCollapsesToSingleAsset(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_asset_disabled_test.cfg";

    {
        std::ofstream out(configPath);
        out << "assets = alpha, beta\n";
        out << "primary_asset = alpha\n";
        out << "asset.alpha.initial_price = 100.0\n";
        out << "asset.beta.initial_price = 40.0\n";
        out << "asset.beta.enabled = 0\n";
    }

    try {
        abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
        abm::SimulationConfig& simulation = runtimeConfig.simulation;
        abm::validateSimulationConfig(simulation);
        abm::normaliseSimulationConfig(simulation);

        abm::test::expect(simulation.assets.size() == 1 && simulation.assets[0].name == "alpha",
                          "a disabled asset should be removed from the tradable asset list",
                          failures);
        abm::test::expect(simulation.assets.disabled().size() == 1 &&
                              simulation.assets.disabled()[0].name == "beta",
                          "a disabled asset should be retained for provenance", failures);
        abm::test::expect(simulation.assets.primaryIndex() == 0 &&
                              simulation.assetName() == "alpha",
                          "the primary asset should resolve against enabled assets only", failures);
    } catch (const std::exception& error) {
        std::cerr << "Unexpected disabled-asset failure: " << error.what() << '\n';
        abm::test::expect(false, "disabled asset configuration should normalise", failures);
    }

    std::filesystem::remove(configPath);
}

void testRuntimeConfigRejectsInvalidAssetProcessAndCorrelation(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_asset_process_bad_test.cfg";

    const auto expectFailure = [&](const std::string& contents, const char* description) {
        {
            std::ofstream out(configPath);
            out << contents;
        }
        bool threw = false;
        try {
            abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
            abm::validateSimulationConfig(runtimeConfig.simulation);
        } catch (const std::exception&) {
            threw = true;
        }
        abm::test::expect(threw, description, failures);
    };

    expectFailure("assets = alpha\nasset.alpha.fundamental_process = heston\n",
                  "an unknown fundamental_process should be rejected");
    expectFailure("assets = alpha, beta\nasset_fundamental_correlation = 1.4\n",
                  "a correlation outside [-1, 1] should be rejected");
    expectFailure("assets = alpha, beta\nasset.alpha.enabled = 0\nasset.beta.enabled = 0\n",
                  "disabling every asset should be rejected");
    expectFailure("assets = alpha, beta\nprimary_asset = beta\nasset.beta.enabled = 0\n",
                  "nominating a disabled asset as primary should be rejected");
    /*
     * Price-unit parameters copied onto a geometric asset are the most likely
     * units mistake, so they must fail loudly rather than run.
     */
    expectFailure("assets = alpha\nasset.alpha.fundamental_process = gbm\n"
                  "asset.alpha.fundamental_shock_std_dev = 3.0\n",
                  "a price-unit shock on a geometric asset should be rejected");

    std::filesystem::remove(configPath);
}

void testRuntimeConfigParsesProtagonistSettings(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_config_protagonist_test.cfg";

    {
        std::ofstream out(configPath);
        out << "protagonist_enabled = 1\n";
        out << "protagonist_name = Alex\n";
        out << "protagonist_strategy = chartist\n";
        out << "protagonist_chartist_rule = rsi\n";
        out << "protagonist_initial_cash = 25000.0\n";
        out << "protagonist_initial_stock = 42\n";
        out << "protagonist_prospect_theory_enabled = 1\n";
        out << "protagonist_loss_aversion = 3.75\n";
        out << "protagonist_timeseries_csv_output = protagonist.csv\n";
    }

    const abm::RuntimeConfig runtimeConfig = abm::loadRuntimeConfig(configPath.string());
    const abm::ProtagonistConfig& protagonist = runtimeConfig.simulation.protagonist;

    abm::test::expect(protagonist.enabled, "config parser should read protagonist_enabled = 1",
                      failures);
    abm::test::expect(protagonist.name == "Alex", "config parser should read the protagonist name",
                      failures);
    abm::test::expect(protagonist.strategy == abm::ProtagonistStrategyKind::Chartist,
                      "config parser should read the protagonist strategy", failures);
    abm::test::expect(protagonist.chartistRule == abm::ChartistStrategyMode::RelativeStrengthIndex,
                      "config parser should read the protagonist's explicit chartist rule",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(protagonist.initialCash, 25000.0),
                      "config parser should read the protagonist's cash endowment", failures);
    abm::test::expect(abm::test::nearlyEqual(protagonist.initialStock, 42.0),
                      "config parser should read the protagonist's share endowment", failures);
    abm::test::expect(protagonist.prospectTheoryEnabled,
                      "config parser should read the protagonist's CPT switch", failures);
    abm::test::expect(abm::test::nearlyEqual(protagonist.lossAversion, 3.75),
                      "config parser should read the protagonist's loss aversion", failures);

    /*
     * `random` is a legitimate value for the anonymous chartist population and a
     * rejected one for the protagonist. Sampling his rule would make it depend
     * on the seed, so it could not be stated in a write-up.
     */
    {
        std::ofstream out(configPath);
        out << "protagonist_chartist_rule = random\n";
    }

    try {
        const abm::RuntimeConfig sampledRule = abm::loadRuntimeConfig(configPath.string());
        static_cast<void>(sampledRule);
        abm::test::expect(false, "config parser should reject a sampled protagonist rule",
                          failures);
    } catch (const std::invalid_argument& error) {
        abm::test::expect(
            std::string(error.what()).find("protagonist_chartist_rule") != std::string::npos,
            "a sampled protagonist rule should be reported against its own key", failures);
    } catch (const std::exception& error) {
        std::cerr << "FAIL: sampled protagonist rule should throw invalid_argument: "
                  << error.what() << '\n';
        ++failures;
    }

    std::filesystem::remove(configPath);
}

void runConfigParsingTests(int& failures) {
    testRuntimeConfigParsesProtagonistSettings(failures);
    testRuntimeConfigParsesMultiAssetDeclaration(failures);
    testRuntimeConfigRejectsMalformedAssetKeys(failures);
    testMultiAssetConfigRejectsLegacyScalarMixing(failures);
    testRuntimeConfigParsesAssetProcessAndToggle(failures);
    testDeclaredAssetsDefaultToGeometricBrownianMotion(failures);
    testDisabledAssetCollapsesToSingleAsset(failures);
    testRuntimeConfigRejectsInvalidAssetProcessAndCorrelation(failures);
    testRuntimeConfigParsesProspectTheoryToggle(failures);
    testRuntimeConfigRejectsInvalidReferencePointMode(failures);
    testRuntimeConfigRejectsInvalidMarketMicrostructure(failures);
    testRuntimeConfigRejectsRetiredPriceImpactControls(failures);
    testRuntimeConfigParsesShortSaleConstraints(failures);
    testCommandLineAcceptsOnlyConfigForms(failures);
}

} // namespace abm::test
