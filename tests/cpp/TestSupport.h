// TestSupport.h

#ifndef ABM_TESTS_TEST_SUPPORT_H
#define ABM_TESTS_TEST_SUPPORT_H

#include <string>

#include "Config/SimulationConfig.h"

namespace abm::test {

bool nearlyEqual(double lhs, double rhs, double tolerance = 1e-10);

void expect(bool condition, const std::string& message, int& failures);

void expectInvalidConfigContaining(const SimulationConfig& config,
                                   const std::string& expectedMessageFragment,
                                   const std::string& message, int& failures);

SimulationConfig deterministicSmokeConfig();

/**
 * Returns the single asset of a config that has no `assets = ...` declaration.
 *
 * Fixtures configure the market through this rather than through scalar fields
 * on SimulationConfig, which are now read-only projections of the primary
 * asset. Throws when the config has already declared an asset list, so a
 * fixture that mixes the two spellings fails loudly instead of writing into an
 * asset it did not mean to touch.
 */
AssetDefinition& soleAsset(SimulationConfig& config);

/**
 * Builds an AssetDefinition from its generating parameters.
 *
 * Tests use this rather than aggregate initialisation so that adding a field to
 * AssetDefinition does not silently shift positional arguments into the wrong
 * members.
 *
 * The process type deliberately defaults to the arithmetic random walk, unlike
 * AssetDefinition itself, which defaults to geometric Brownian motion. Test
 * fixtures are written with price-unit shock and drift parameters, so keeping
 * the arithmetic walk here preserves their intended magnitudes; tests that
 * exercise the geometric process pass it explicitly.
 */
AssetDefinition makeAssetDefinition(
    const std::string& name, double initialPrice, double initialStock, double priceTickSize,
    double fundamentalShockStdDev, double fundamentalDriftPerStep, double minimumFundamentalValue,
    FundamentalProcessType fundamentalProcess = FundamentalProcessType::ArithmeticRandomWalk,
    bool enabled = true);

void runRandomMarketRiskTests(int& failures);
void runPortfolioOptimizerTests(int& failures);
void runProspectTheoryTests(int& failures);
void runChartistStrategyTests(int& failures);
void runBuyAndHoldStrategyTests(int& failures);
void runNoiseTraderStrategyTests(int& failures);
void runLimitOrderBookTests(int& failures);
void runSimulationComponentTests(int& failures);
void runSimulationIntegrationTests(int& failures);
void runConfigParsingTests(int& failures);
void runConfigKeyRegistryTests(int& failures);
void runArchiveWorkflowTests(int& failures);
void runConfigValidationTests(int& failures);
void runRunArtifactWriterTests(int& failures);

} // namespace abm::test

#endif // ABM_TESTS_TEST_SUPPORT_H
