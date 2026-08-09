// CholeskyFactorization.h

#ifndef UTILITY_CHOLESKY_FACTORIZATION_H
#define UTILITY_CHOLESKY_FACTORIZATION_H

#include <cstddef>
#include <vector>

namespace abm {

/**
 * Dense symmetric matrix stored row-major.
 *
 * The struct is intentionally minimal: portfolio problems in this model have
 * at most a handful of assets, so clarity beats sparse or blocked storage.
 */
struct SymmetricMatrix {
    std::size_t size{0};
    std::vector<double> values;

    SymmetricMatrix() = default;

    /** Creates a size x size zero matrix. */
    explicit SymmetricMatrix(std::size_t matrixSize)
        : size(matrixSize), values(matrixSize * matrixSize, 0.0) {}

    [[nodiscard]] double& at(std::size_t row, std::size_t column) {
        return values[(row * size) + column];
    }

    [[nodiscard]] double at(std::size_t row, std::size_t column) const {
        return values[(row * size) + column];
    }
};

/**
 * Factorizes a symmetric positive-definite matrix in place into its lower
 * Cholesky factor L with A = L * L^T. The upper triangle is zeroed.
 *
 * @return false when the matrix is not numerically positive definite; the
 * matrix contents are then unspecified and the caller must regularize and
 * retry or fall back to a diagonal model.
 */
[[nodiscard]] bool choleskyFactorize(SymmetricMatrix& matrix);

/**
 * Solves A x = rhs given the lower Cholesky factor of A via forward and
 * backward substitution.
 */
[[nodiscard]] std::vector<double> choleskySolve(const SymmetricMatrix& lowerFactor,
                                                const std::vector<double>& rhs);

/**
 * Regularizes a covariance matrix so factorization succeeds with short
 * estimation windows and flat price histories.
 *
 * Each diagonal entry is floored at varianceFloor, then diagonalLoading times
 * the mean diagonal is added to every diagonal entry when diagonalLoading is
 * positive.
 */
void regularizeCovariance(SymmetricMatrix& covariance, double varianceFloor,
                          double diagonalLoading);

} // namespace abm

#endif // UTILITY_CHOLESKY_FACTORIZATION_H
