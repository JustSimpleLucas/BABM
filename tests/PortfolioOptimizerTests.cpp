// PortfolioOptimizerTests.cpp

#include "tests/TestSupport.h"

#include "Agent/Agent.h"
#include "AgentStrategy/MeanVarianceUtility.h"
#include "AgentStrategy/PortfolioOptimizer.h"
#include "AgentStrategy/StrategyMarketHelpers.h"
#include "BehaviouralFinance/ProspectTheory.h"
#include "Market/CovarianceEstimator.h"
#include "Market/Market.h"
#include "Utility/CholeskyFactorization.h"

#include <cmath>
#include <vector>

namespace {

void testCholeskySolvesHandComputedSystems(int& failures) {
    /*
     * A = [[4, 2], [2, 3]], b = [8, 7]  =>  x = [1.25, 1.5].
     */
    abm::SymmetricMatrix twoByTwo(2);
    twoByTwo.at(0, 0) = 4.0;
    twoByTwo.at(0, 1) = 2.0;
    twoByTwo.at(1, 0) = 2.0;
    twoByTwo.at(1, 1) = 3.0;
    abm::test::expect(abm::choleskyFactorize(twoByTwo),
                      "a positive-definite 2x2 matrix should factorize", failures);
    const std::vector<double> twoSolution = abm::choleskySolve(twoByTwo, {8.0, 7.0});
    abm::test::expect(abm::test::nearlyEqual(twoSolution[0], 1.25, 1e-12) &&
                          abm::test::nearlyEqual(twoSolution[1], 1.5, 1e-12),
                      "Cholesky solve should reproduce the hand-computed 2x2 solution", failures);

    /*
     * A = [[6, 2, 1], [2, 5, 2], [1, 2, 4]], x_true = [1, -1, 2]
     * => b = A x_true = [6, 1, 7].
     */
    abm::SymmetricMatrix threeByThree(3);
    const double entries[3][3] = {{6.0, 2.0, 1.0}, {2.0, 5.0, 2.0}, {1.0, 2.0, 4.0}};
    for (std::size_t row = 0; row < 3; ++row) {
        for (std::size_t column = 0; column < 3; ++column) {
            threeByThree.at(row, column) = entries[row][column];
        }
    }
    abm::test::expect(abm::choleskyFactorize(threeByThree),
                      "a positive-definite 3x3 matrix should factorize", failures);
    const std::vector<double> threeSolution = abm::choleskySolve(threeByThree, {6.0, 1.0, 7.0});
    abm::test::expect(abm::test::nearlyEqual(threeSolution[0], 1.0, 1e-12) &&
                          abm::test::nearlyEqual(threeSolution[1], -1.0, 1e-12) &&
                          abm::test::nearlyEqual(threeSolution[2], 2.0, 1e-12),
                      "Cholesky solve should reproduce the hand-computed 3x3 solution", failures);
}

void testCholeskyRejectsIndefiniteMatrix(int& failures) {
    abm::SymmetricMatrix indefinite(2);
    indefinite.at(0, 0) = 1.0;
    indefinite.at(0, 1) = 2.0;
    indefinite.at(1, 0) = 2.0;
    indefinite.at(1, 1) = 1.0;
    abm::test::expect(!abm::choleskyFactorize(indefinite),
                      "an indefinite matrix should be rejected by the factorization", failures);
}

void testOptimizerReducesToScalarRuleForOneAsset(int& failures) {
    const double expectedExcessReturn = 0.004;
    const double sigma = 0.02;
    const double riskAversion = 3.0;

    const std::vector<double> excessReturns{expectedExcessReturn};
    abm::SymmetricMatrix covariance(1);
    covariance.at(0, 0) = sigma * sigma;
    const std::vector<abm::AssetWeightBounds> bounds{{0.0, 1.0}};
    const std::vector<double> weights = abm::optimalRiskyWeights(
        abm::PortfolioInputs{&excessReturns, &covariance, riskAversion, &bounds, 0.0});

    const double scalarWeight = abm::optimalRiskyWeight(
        abm::MeanVarianceInputs{expectedExcessReturn, 0.0, sigma, riskAversion}, 0.0, 1.0);

    abm::test::expect(
        weights.size() == 1 && abm::test::nearlyEqual(weights[0], scalarWeight, 1e-12),
        "the one-asset Markowitz solve should equal the scalar rule exactly", failures);
}

void testOptimizerAccountsForCrossAssetCovariance(int& failures) {
    /*
     * Two identical assets with strong positive correlation must each receive
     * a smaller weight than two independent assets with the same variance.
     */
    const std::vector<double> excessReturns{0.002, 0.002};
    const double variance = 0.0004;

    abm::SymmetricMatrix independent(2);
    independent.at(0, 0) = variance;
    independent.at(1, 1) = variance;

    abm::SymmetricMatrix correlated = independent;
    correlated.at(0, 1) = 0.9 * variance;
    correlated.at(1, 0) = 0.9 * variance;

    const std::vector<abm::AssetWeightBounds> bounds{{-10.0, 10.0}, {-10.0, 10.0}};
    const std::vector<double> independentWeights = abm::optimalRiskyWeights(
        abm::PortfolioInputs{&excessReturns, &independent, 3.0, &bounds, 0.0});
    const std::vector<double> correlatedWeights = abm::optimalRiskyWeights(
        abm::PortfolioInputs{&excessReturns, &correlated, 3.0, &bounds, 0.0});

    abm::test::expect(correlatedWeights[0] < independentWeights[0] &&
                          correlatedWeights[1] < independentWeights[1],
                      "correlated assets should receive smaller joint weights than independent "
                      "assets",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(correlatedWeights[0],
                                             excessReturns[0] / (3.0 * variance * 1.9), 1e-9),
                      "the correlated two-asset solve should match the closed-form solution",
                      failures);
}

void testOptimizerAppliesBoundsAndGrossExposureCap(int& failures) {
    const std::vector<double> excessReturns{0.05, -0.05};
    abm::SymmetricMatrix covariance(2);
    covariance.at(0, 0) = 0.0001;
    covariance.at(1, 1) = 0.0001;

    const std::vector<abm::AssetWeightBounds> bounds{{-0.5, 1.0}, {-0.5, 1.0}};
    const std::vector<double> weights = abm::optimalRiskyWeights(
        abm::PortfolioInputs{&excessReturns, &covariance, 3.0, &bounds, 1.0});

    /*
     * The unconstrained solve saturates both bounds (1.0 and -0.5); the gross
     * cap of 1.0 then scales both by 1/1.5.
     */
    abm::test::expect(abm::test::nearlyEqual(weights[0], 1.0 / 1.5, 1e-9) &&
                          abm::test::nearlyEqual(weights[1], -0.5 / 1.5, 1e-9),
                      "bounds and the gross-exposure cap should shape the final weights", failures);
}

void testOptimizerFallsBackToDiagonalOnDegenerateCovariance(int& failures) {
    /*
     * A rank-deficient covariance (perfectly correlated assets) must still
     * produce finite weights through regularization or the diagonal fallback.
     */
    const std::vector<double> excessReturns{0.002, 0.001};
    abm::SymmetricMatrix degenerate(2);
    degenerate.at(0, 0) = 0.0004;
    degenerate.at(0, 1) = 0.0004;
    degenerate.at(1, 0) = 0.0004;
    degenerate.at(1, 1) = 0.0004;

    const std::vector<abm::AssetWeightBounds> bounds{{-1.0, 1.0}, {-1.0, 1.0}};
    const std::vector<double> weights = abm::optimalRiskyWeights(
        abm::PortfolioInputs{&excessReturns, &degenerate, 3.0, &bounds, 0.0});

    abm::test::expect(weights.size() == 2 && std::isfinite(weights[0]) && std::isfinite(weights[1]),
                      "degenerate covariance should still yield finite bounded weights", failures);
}

void testCovarianceEstimatorMatchesHandComputation(int& failures) {
    abm::Market market;
    market.configureAssets({"alpha", "beta"});

    /*
     * alpha log returns: log(110/100), log(99/110), log(105/99)
     * beta  log returns: log(50/55),  log(60/50),  log(57/60)
     */
    for (const double price : {100.0, 110.0, 99.0, 105.0}) {
        market.storeMarketValue(0, price);
    }
    for (const double price : {55.0, 50.0, 60.0, 57.0}) {
        market.storeMarketValue(1, price);
    }

    const abm::SymmetricMatrix covariance = abm::estimateLogReturnCovariance(market, 3);

    const std::vector<double> alphaReturns{std::log(110.0 / 100.0), std::log(99.0 / 110.0),
                                           std::log(105.0 / 99.0)};
    const std::vector<double> betaReturns{std::log(50.0 / 55.0), std::log(60.0 / 50.0),
                                          std::log(57.0 / 60.0)};
    const auto sampleCovariance = [](const std::vector<double>& lhs,
                                     const std::vector<double>& rhs) {
        double lhsMean = 0.0;
        double rhsMean = 0.0;
        for (std::size_t index = 0; index < lhs.size(); ++index) {
            lhsMean += lhs[index];
            rhsMean += rhs[index];
        }
        lhsMean /= static_cast<double>(lhs.size());
        rhsMean /= static_cast<double>(rhs.size());
        double sum = 0.0;
        for (std::size_t index = 0; index < lhs.size(); ++index) {
            sum += (lhs[index] - lhsMean) * (rhs[index] - rhsMean);
        }
        return sum / static_cast<double>(lhs.size() - 1);
    };

    abm::test::expect(
        abm::test::nearlyEqual(covariance.at(0, 0), sampleCovariance(alphaReturns, alphaReturns),
                               1e-12) &&
            abm::test::nearlyEqual(covariance.at(1, 1), sampleCovariance(betaReturns, betaReturns),
                                   1e-12) &&
            abm::test::nearlyEqual(covariance.at(0, 1), sampleCovariance(alphaReturns, betaReturns),
                                   1e-12) &&
            abm::test::nearlyEqual(covariance.at(0, 1), covariance.at(1, 0), 1e-15),
        "the covariance estimator should match the hand-computed sample covariance", failures);
}

void testProspectAdjustmentIsScaleInvariant(int& failures) {
    /*
     * Two agents with identical forecasts but price levels 100x apart must get
     * identical behavioural adjustments once anchors live in return space.
     */
    abm::Market lowPriceMarket;
    lowPriceMarket.configureAssets({"asset"});
    lowPriceMarket.storeMarketValue(0, 10.0);
    abm::Market highPriceMarket;
    highPriceMarket.configureAssets({"asset"});
    highPriceMarket.storeMarketValue(0, 1000.0);

    abm::Agent lowPriceAgent(1U, abm::AgentEndowment{1000.0, {5.0}});
    abm::Agent highPriceAgent(2U, abm::AgentEndowment{100000.0, {5.0}});
    // Entry prices 5% below the current price in both markets.
    lowPriceAgent.recordExecutedTrade(0, abm::ExecutedTrade{abm::OrderType::BUY, 9.5, 5.0});
    highPriceAgent.recordExecutedTrade(0, abm::ExecutedTrade{abm::OrderType::BUY, 950.0, 5.0});

    const double lowReference = abm::strategy_detail::resolveProspectReferenceReturn(
        lowPriceAgent, lowPriceMarket, 0, abm::ProspectReferencePointMode::AveragePurchasePrice, 20,
        10.0);
    const double highReference = abm::strategy_detail::resolveProspectReferenceReturn(
        highPriceAgent, highPriceMarket, 0, abm::ProspectReferencePointMode::AveragePurchasePrice,
        20, 1000.0);

    abm::test::expect(abm::test::nearlyEqual(lowReference, highReference, 1e-12),
                      "reference log returns should be identical across price scales", failures);

    const abm::ProspectTheory prospectTheory{};
    const double lowAdjusted = prospectTheory.prospectAdjustedReturn(
        abm::ProspectReturnForecast{0.01, 0.02, lowReference});
    const double highAdjusted = prospectTheory.prospectAdjustedReturn(
        abm::ProspectReturnForecast{0.01, 0.02, highReference});
    abm::test::expect(abm::test::nearlyEqual(lowAdjusted, highAdjusted, 1e-12),
                      "CPT-adjusted returns should be invariant to the asset's price level",
                      failures);
}

} // namespace

namespace abm::test {

void runPortfolioOptimizerTests(int& failures) {
    testCholeskySolvesHandComputedSystems(failures);
    testCholeskyRejectsIndefiniteMatrix(failures);
    testOptimizerReducesToScalarRuleForOneAsset(failures);
    testOptimizerAccountsForCrossAssetCovariance(failures);
    testOptimizerAppliesBoundsAndGrossExposureCap(failures);
    testOptimizerFallsBackToDiagonalOnDegenerateCovariance(failures);
    testCovarianceEstimatorMatchesHandComputation(failures);
    testProspectAdjustmentIsScaleInvariant(failures);
}

} // namespace abm::test
