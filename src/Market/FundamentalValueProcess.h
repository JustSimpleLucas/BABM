// Market/FundamentalValueProcess.h

#ifndef ABM_MARKET_FUNDAMENTAL_VALUE_PROCESS_H
#define ABM_MARKET_FUNDAMENTAL_VALUE_PROCESS_H

#include <cstddef>
#include <cstdint>
#include <vector>

#include "ControlParameters/MarketConfig.h"
#include "Market/Market.h"
#include "RandomGenerator/RandomGenerator.h"
#include "Utility/SimulationConstants.h"

namespace abm {

/**
 * Parameters controlling one-period latent fundamental-value evolution.
 *
 * The functional form is selected by `processType`:
 *   ArithmeticRandomWalk    F_{t+1} = max(F_min, F_t + mu + sigma * zeta)
 *   GeometricBrownianMotion F_{t+1} = max(F_min, F_t * exp((mu - sigma^2/2) + sigma * zeta))
 *
 * where zeta is a standard normal innovation. The units of `driftPerStep` and
 * `shockStdDev` follow the chosen process; see FundamentalProcessType.
 */
struct FundamentalValueProcessParameters {
    /** Stochastic process used to evolve the latent fundamental value. */
    FundamentalProcessType processType{FundamentalProcessType::ArithmeticRandomWalk};

    /** Deterministic drift applied to the latent fundamental value each period. */
    double driftPerStep{0.0};

    /** Scale of the Gaussian fundamental-value innovation. */
    double shockStdDev{0.01};

    /** Lower bound applied after drift and stochastic innovation are combined. */
    double minimumValue{kMinimumPrice};
};

/**
 * Parameters for pre-generating a latent fundamental-value path.
 *
 * Grouping these values avoids swappable adjacent numeric arguments and keeps
 * the experimental interpretation explicit at call sites.
 */
struct TrueValueGenerationParameters {
    /** Number of future fundamental values to draw and append. */
    std::size_t timeSteps{0};

    /**
     * Initial latent value used only when the asset has no stored fundamental
     * history.
     */
    double initialValue{0.0};

    /** Deterministic drift added to the latent fundamental value each period. */
    double driftPerStep{0.0};

    /** Standard deviation of the additive Gaussian fundamental-value shock. */
    double shockStdDev{0.01};

    /** Lower bound applied after drift and stochastic innovation are combined. */
    double minimumValue{kMinimumPrice};
};

/**
 * Evolves the latent fundamental values that back a market's assets.
 *
 * Purpose: the fundamental process is a research assumption, not a property of
 * the price record. Keeping it here means every stochastic draw that moves
 * intrinsic value is declared in one file, and Market stays a passive history
 * of what the process and the order book produced.
 *
 * Reproducibility: this class owns its own RandomEngine, deliberately separate
 * from the engine that drives agent activation, warm-up price noise, and
 * strategy behaviour. A run therefore has two independent streams, both derived
 * from the single configured seed, so changing the number of agent-side draws
 * cannot perturb the fundamental path (and vice versa). SimulationEngine seeds
 * this process with `config.seed` and the agent-side engine with
 * `config.seed + 1`.
 *
 * Every method appends to the market's fundamental history through
 * Market::storeTrueValue, so a generated value is validated on the same path as
 * any other stored value.
 */
class FundamentalValueProcess {
  public:
    /** Constructs a reproducible process with a documented default seed. */
    FundamentalValueProcess();

    /** Constructs a reproducible process with an experiment-supplied seed. */
    explicit FundamentalValueProcess(std::uint64_t seed);

    /**
     * Advances one asset's latent fundamental value by one period.
     *
     * The innovation is drawn independently of any other asset, so this
     * overload is appropriate only for single-asset evolution or for tests.
     * Multi-asset runs must use generateCorrelatedFundamentalValues so that
     * the cross-asset correlation structure is respected.
     */
    [[nodiscard]] double
    generateFundamentalValue(Market& market, std::size_t assetIndex,
                             const FundamentalValueProcessParameters& parameters);

    /**
     * Advances every configured asset by one period using correlated innovations.
     *
     * Purpose: fundamental values in a multi-asset market are not independent.
     * A common macroeconomic factor makes fundamentals co-move, and that
     * co-movement is what limits the diversification available to agents.
     *
     * Method: one standard normal z_j is drawn per asset in index order, then
     * mapped to correlated standard normals via the closed-form one-factor
     * square root of the equicorrelation matrix R (unit diagonal,
     * `pairwiseCorrelation` off-diagonal):
     *
     *   zeta_j = a * z_j + b * sum_k z_k,
     *   a = sqrt(1 - rho),
     *   b = (sqrt(1 + (n - 1) * rho) - a) / n.
     *
     * This is preferred over a generic Cholesky factorization because it stays
     * exact on the positive-semi-definite boundary (rho = 1, or the lower limit
     * rho = -1/(n-1)) where Cholesky would fail on a singular matrix. Each
     * asset then applies its own process to its own zeta_j.
     *
     * Reproducibility: with one asset, or with rho = 0, the map is exactly the
     * identity and is short-circuited, so the innovation sigma * z_j is
     * bit-identical to the independent single-asset draw of
     * generateFundamentalValue. The historical draw sequence is therefore
     * preserved exactly.
     *
     * @param market Market whose fundamental histories are read and extended.
     * @param parameters Per-asset process parameters, one per configured
     *        asset in index order.
     * @param pairwiseCorrelation Correlation applied to every distinct pair.
     * @return The new fundamental value for each asset, in index order.
     *
     * @throws std::invalid_argument when the parameter count does not match the
     *         market's asset count, when the correlation is outside [-1, 1],
     *         or when the implied correlation matrix is not positive
     *         semi-definite.
     */
    [[nodiscard]] std::vector<double> generateCorrelatedFundamentalValues(
        Market& market, const std::vector<FundamentalValueProcessParameters>& parameters,
        double pairwiseCorrelation);

    /**
     * Generates and stores a sequence of latent fundamental values.
     *
     * This helper is useful for reproducible experiments and tests where the
     * fundamental process should be generated before agent interaction begins.
     * It always applies the arithmetic random walk, regardless of the process
     * type an asset declares.
     */
    [[nodiscard]] std::vector<double>
    generateTrueValues(Market& market, std::size_t assetIndex,
                       const TrueValueGenerationParameters& parameters);

  private:
    RandomEngine randomEngine_;
};

} // namespace abm

#endif // ABM_MARKET_FUNDAMENTAL_VALUE_PROCESS_H
