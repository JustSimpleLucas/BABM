// CholeskyFactorization.cpp

#include "Utility/CholeskyFactorization.h"

#include <algorithm>
#include <cmath>

namespace abm {

bool choleskyFactorize(SymmetricMatrix& matrix) {
    const std::size_t n = matrix.size;
    for (std::size_t column = 0; column < n; ++column) {
        double diagonal = matrix.at(column, column);
        for (std::size_t k = 0; k < column; ++k) {
            diagonal -= matrix.at(column, k) * matrix.at(column, k);
        }
        if (!(diagonal > 0.0) || !std::isfinite(diagonal)) {
            return false;
        }
        const double factor = std::sqrt(diagonal);
        matrix.at(column, column) = factor;

        for (std::size_t row = column + 1; row < n; ++row) {
            double offDiagonal = matrix.at(row, column);
            for (std::size_t k = 0; k < column; ++k) {
                offDiagonal -= matrix.at(row, k) * matrix.at(column, k);
            }
            matrix.at(row, column) = offDiagonal / factor;
        }
    }

    for (std::size_t row = 0; row < n; ++row) {
        for (std::size_t column = row + 1; column < n; ++column) {
            matrix.at(row, column) = 0.0;
        }
    }
    return true;
}

std::vector<double> choleskySolve(const SymmetricMatrix& lowerFactor,
                                  const std::vector<double>& rhs) {
    const std::size_t n = lowerFactor.size;

    // Forward substitution: L y = rhs.
    std::vector<double> solution(rhs);
    for (std::size_t row = 0; row < n; ++row) {
        double value = solution[row];
        for (std::size_t k = 0; k < row; ++k) {
            value -= lowerFactor.at(row, k) * solution[k];
        }
        solution[row] = value / lowerFactor.at(row, row);
    }

    // Backward substitution: L^T x = y.
    for (std::size_t reverseRow = n; reverseRow > 0; --reverseRow) {
        const std::size_t row = reverseRow - 1;
        double value = solution[row];
        for (std::size_t k = row + 1; k < n; ++k) {
            value -= lowerFactor.at(k, row) * solution[k];
        }
        solution[row] = value / lowerFactor.at(row, row);
    }
    return solution;
}

void regularizeCovariance(SymmetricMatrix& covariance, double varianceFloor,
                          double diagonalLoading) {
    const std::size_t n = covariance.size;
    if (n == 0) {
        return;
    }

    double diagonalTotal = 0.0;
    for (std::size_t index = 0; index < n; ++index) {
        double& variance = covariance.at(index, index);
        if (!std::isfinite(variance) || variance < varianceFloor) {
            variance = varianceFloor;
        }
        diagonalTotal += variance;
    }

    if (diagonalLoading > 0.0) {
        const double loading = diagonalLoading * (diagonalTotal / static_cast<double>(n));
        for (std::size_t index = 0; index < n; ++index) {
            covariance.at(index, index) += loading;
        }
    }
}

} // namespace abm
