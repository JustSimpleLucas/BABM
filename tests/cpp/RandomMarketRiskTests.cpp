// RandomMarketRiskTests.cpp

#include "tests/cpp/TestSupport.h"

#include "AgentStrategy/AssetAllocationLine.h"
#include "Market/FundamentalValueProcess.h"
#include "Market/Market.h"
#include "RandomGenerator/RandomGenerator.h"
#include "RiskManagement/ShortSaleRiskControls.h"

#include <cmath>
#include <string>

namespace {

void testRandomEngineIsSeedReproducible(int& failures) {
    abm::RandomEngine first(1234U);
    abm::RandomEngine second(1234U);

    abm::test::expect(abm::test::nearlyEqual(first.generateUniformDist(0.0, 1.0),
                                             second.generateUniformDist(0.0, 1.0)),
                      "uniform draws with the same seed should match", failures);
    abm::test::expect(first.generateUniformIntDist(1, 10) == second.generateUniformIntDist(1, 10),
                      "integer draws with the same seed should match", failures);
    abm::test::expect(abm::test::nearlyEqual(first.generateNormalDist(0.0, 1.0),
                                             second.generateNormalDist(0.0, 1.0)),
                      "normal draws with the same seed should match", failures);
}

void testAllocationBounds(int& failures) {
    const abm::AssetAllocationLine allocation(3.0, -0.25, 0.75);

    abm::test::expect(abm::test::nearlyEqual(allocation.optimalRiskyWeight(0.20, 0.0, 0.10), 0.75),
                      "positive expected returns should be clipped at the maximum risky weight",
                      failures);
    abm::test::expect(
        abm::test::nearlyEqual(allocation.optimalRiskyWeight(-0.20, 0.0, 0.10), -0.25),
        "negative expected returns should be clipped at the minimum risky weight", failures);
}

void testMarketLogReturnVolatility(int& failures) {
    abm::Market market;
    market.configureAssets({"test_asset"});

    double price = 100.0;
    market.storeMarketValue(0, price);
    for (const double logReturn : {0.01, -0.03, 0.02}) {
        price *= std::exp(logReturn);
        market.storeMarketValue(0, price);
    }

    const double expectedPopulationStdDev = std::sqrt((0.0001 + 0.0009 + 0.0004) / 3.0);
    abm::test::expect(abm::test::nearlyEqual(market.calculateLogReturnStandardDeviation(0, 3),
                                             expectedPopulationStdDev, 1e-12),
                      "market volatility should be calculated from log returns, not price levels",
                      failures);
}

void testGenerateTrueValuesUsesNamedGenerationParameters(int& failures) {
    abm::Market market;
    abm::FundamentalValueProcess fundamentalProcess(1234U);
    market.configureAssets({"fundamental_asset"});

    abm::TrueValueGenerationParameters parameters;
    parameters.timeSteps = 3;
    parameters.initialValue = 125.0;
    parameters.shockStdDev = 0.0;

    const auto generatedValues = fundamentalProcess.generateTrueValues(market, 0, parameters);
    const auto& storedValues = market.getTrueValues(0);

    abm::test::expect(generatedValues.size() == parameters.timeSteps,
                      "fundamental path generation should return the requested number of values",
                      failures);
    abm::test::expect(storedValues.size() == parameters.timeSteps,
                      "fundamental path generation should store the requested number of values",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(generatedValues.front(), parameters.initialValue),
                      "zero-shock fundamental path should start from the configured initial value",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(generatedValues.back(), parameters.initialValue),
                      "zero-shock fundamental path should remain at the configured initial value",
                      failures);
}

void testFundamentalPathAppliesDeterministicDrift(int& failures) {
    abm::Market market;
    abm::FundamentalValueProcess fundamentalProcess(1234U);
    market.configureAssets({"drift_asset"});

    abm::TrueValueGenerationParameters parameters;
    parameters.timeSteps = 3;
    parameters.initialValue = 100.0;
    parameters.driftPerStep = 0.25;
    parameters.shockStdDev = 0.0;

    const auto generatedValues = fundamentalProcess.generateTrueValues(market, 0, parameters);

    abm::test::expect(abm::test::nearlyEqual(generatedValues.at(0), 100.25),
                      "positive drift should increase the first generated fundamental value",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(generatedValues.at(2), 100.75),
                      "positive drift should accumulate over the generated fundamental path",
                      failures);
}

void testFundamentalPathAppliesMinimumValueFloor(int& failures) {
    abm::Market market;
    abm::FundamentalValueProcess fundamentalProcess(1234U);
    market.configureAssets({"floored_asset"});
    market.storeTrueValue(0, 10.0);

    abm::FundamentalValueProcessParameters parameters;
    parameters.driftPerStep = -20.0;
    parameters.shockStdDev = 0.0;
    parameters.minimumValue = 2.5;

    const double nextFundamental =
        fundamentalProcess.generateFundamentalValue(market, 0, parameters);

    abm::test::expect(abm::test::nearlyEqual(nextFundamental, parameters.minimumValue),
                      "fundamental value generation should apply the configured lower bound",
                      failures);
}

void testShortSaleConstraintsLimitExposureAndBorrowSupply(int& failures) {
    const double requestedSellQuantity = 100.0;
    const double currentStock = 10.0;
    const double cash = 1000.0;
    const double price = 100.0;
    const double currentShortInterest = 0.0;
    const double reservedNewShortShares = 0.0;
    const double totalShareSupply = 200.0;
    const double initialMarginRequirement = 0.50;
    const double borrowableSupplyRatio = 0.20;

    const double permittedSellQuantity =
        abm::constrainSellQuantityByShortSaleRules(abm::ShortSaleSellConstraintRequest{
            requestedSellQuantity, currentStock, cash, price, currentShortInterest,
            reservedNewShortShares, totalShareSupply, initialMarginRequirement,
            borrowableSupplyRatio});

    abm::test::expect(
        abm::test::nearlyEqual(permittedSellQuantity, 50.0),
        "short-sale filter should permit long-share sales plus constrained new shorts", failures);
}

void testMaintenanceMarginCalculatesForcedBuyIn(int& failures) {
    const double cash = 3000.0;
    const double stock = -20.0;
    const double price = 140.0;
    const double initialMarginRequirement = 0.50;
    const double maintenanceMarginRequirement = 0.30;

    const double requiredCoverQuantity =
        abm::requiredBuyToCoverQuantity(abm::ShortSaleMarginCallRequest{
            cash, stock, price, initialMarginRequirement, maintenanceMarginRequirement});

    abm::test::expect(abm::test::nearlyEqual(requiredCoverQuantity, 17.142857142857142, 1e-9),
                      "maintenance breach should calculate cover quantity restoring initial margin",
                      failures);

    const double postCoverCash = cash - (requiredCoverQuantity * price);
    const double postCoverStock = stock + requiredCoverQuantity;
    abm::test::expect(
        abm::test::nearlyEqual(abm::shortMarginRatio(postCoverCash, postCoverStock, price),
                               initialMarginRequirement, 1e-9),
        "forced buy-in should restore the initial margin ratio when cash is sufficient", failures);
}

} // namespace

namespace abm::test {

void runRandomMarketRiskTests(int& failures) {
    testRandomEngineIsSeedReproducible(failures);
    testAllocationBounds(failures);
    testMarketLogReturnVolatility(failures);
    testGenerateTrueValuesUsesNamedGenerationParameters(failures);
    testFundamentalPathAppliesDeterministicDrift(failures);
    testFundamentalPathAppliesMinimumValueFloor(failures);
    testShortSaleConstraintsLimitExposureAndBorrowSupply(failures);
    testMaintenanceMarginCalculatesForcedBuyIn(failures);
}

} // namespace abm::test
