// PortfolioOptimizer.h

#ifndef ABM_AGENT_STRATEGY_PORTFOLIO_OPTIMIZER_H
#define ABM_AGENT_STRATEGY_PORTFOLIO_OPTIMIZER_H

#include <vector>

#include "Utility/CholeskyFactorization.h"

namespace abm {

/** Per-asset portfolio-weight interval applied after the unconstrained solve. */
struct AssetWeightBounds {
    double minWeight{0.0};
    double maxWeight{1.0};
};

/** Inputs for one myopic mean-variance portfolio optimisation. */
struct PortfolioInputs {
    /** Expected excess log returns (mu_j - r_f), one per asset. */
    const std::vector<double>* expectedExcessReturns{nullptr};

    /** Log-return covariance matrix; regularized internally before the solve. */
    const SymmetricMatrix* covariance{nullptr};

    /** Positive coefficient of risk aversion. */
    double riskAversion{3.0};

    /** Per-asset weight intervals; one entry per asset. */
    const std::vector<AssetWeightBounds>* bounds{nullptr};

    /** Cap on the gross exposure sum_j |w_j|; non-positive disables the cap. */
    double maxGrossExposure{1.0};
};

/**
 * Solves the full Markowitz problem w* = (1/rho) * Sigma^{-1} (mu - r_f 1).
 *
 * The covariance copy is regularized (variance floor plus escalating diagonal
 * loading) until the Cholesky factorization succeeds; if it still fails the
 * rule degrades gracefully to the diagonal solve w_j = mu_j / (rho sigma_j^2),
 * which for one asset is exactly the historical scalar mean-variance rule.
 *
 * Projection policy: weights are clamped to the per-asset intervals first;
 * when gross exposure sum_j |w_j| then exceeds the cap, all weights are scaled
 * proportionally and clamped once more. The residual 1 - sum_j w_j is held at
 * the risk-free rate implicitly, as in the single-asset model.
 */
[[nodiscard]] std::vector<double> optimalRiskyWeights(const PortfolioInputs& inputs);

} // namespace abm

#endif // ABM_AGENT_STRATEGY_PORTFOLIO_OPTIMIZER_H
