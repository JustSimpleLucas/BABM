// NumericValidation.h

#ifndef ABM_UTILITY_NUMERIC_VALIDATION_H
#define ABM_UTILITY_NUMERIC_VALIDATION_H

#include <cstddef>

namespace abm {

/**
 * Requires a simulation parameter or state variable to be finite.
 *
 * Non-finite values are rejected at module boundaries because NaN and infinity
 * can silently propagate through prices, wealth, utility scores, and behavioural
 * parameters, making simulation output difficult to reproduce and interpret.
 *
 * @param value Numeric value to validate.
 * @param name Human-readable parameter or state name used in the exception.
 * @throws std::invalid_argument if value is NaN or infinite.
 */
void requireFinite(double value, const char* name);

/**
 * Requires a finite value to be strictly greater than zero.
 *
 * This is used for prices, volatility scales, and behavioural parameters where
 * zero would invalidate a model equation or remove the economic interpretation
 * of the parameter.
 *
 * @param value Numeric value to validate.
 * @param name Human-readable parameter or state name used in the exception.
 * @throws std::invalid_argument if value is non-finite or not positive.
 */
void requireStrictlyPositive(double value, const char* name);

/**
 * Requires a finite value to be greater than or equal to zero.
 *
 * Non-negative constraints are common for standard deviations, distances,
 * tolerances, and other model magnitudes that cannot be economically negative.
 *
 * @param value Numeric value to validate.
 * @param name Human-readable parameter or state name used in the exception.
 * @throws std::invalid_argument if value is non-finite or negative.
 */
void requireNonNegative(double value, const char* name);

/**
 * Requires a finite value to lie in the closed unit interval [0, 1].
 *
 * @param value Numeric value to validate.
 * @param name Human-readable parameter or state name used in the exception.
 * @throws std::invalid_argument if value is non-finite or outside [0, 1].
 */
void requireInClosedUnitInterval(double value, const char* name);

/**
 * Requires a finite value to lie in the half-open unit interval [0, 1).
 *
 * @param value Numeric value to validate.
 * @param name Human-readable parameter or state name used in the exception.
 * @throws std::invalid_argument if value is non-finite or outside [0, 1).
 */
void requireInHalfOpenUnitInterval(double value, const char* name);

/**
 * Requires a finite probability to lie in [0, 1].
 *
 * @param probability Probability value to validate.
 * @param name Human-readable probability name used in the exception.
 * @throws std::invalid_argument if probability is non-finite or outside [0, 1].
 */
void requireProbability(double probability, const char* name = "Probability");

/**
 * Requires a count, period, or rolling-window length to be greater than zero.
 *
 * @param value Count-like value to validate.
 * @param name Human-readable parameter name used in the exception.
 * @throws std::invalid_argument if value is zero.
 */
void requirePositiveSize(std::size_t value, const char* name);

} // namespace abm

#endif // ABM_UTILITY_NUMERIC_VALIDATION_H
