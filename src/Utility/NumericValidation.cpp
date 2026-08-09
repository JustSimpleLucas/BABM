// NumericValidation.cpp

#include "Utility/NumericValidation.h"

#include <cmath>
#include <stdexcept>
#include <string>

namespace abm {

void requireFinite(double value, const char* name) {
    if (!std::isfinite(value)) {
        throw std::invalid_argument(std::string(name) + " must be finite.");
    }
}

void requireStrictlyPositive(double value, const char* name) {
    requireFinite(value, name);
    if (value <= 0.0) {
        throw std::invalid_argument(std::string(name) + " must be strictly positive.");
    }
}

void requireNonNegative(double value, const char* name) {
    requireFinite(value, name);
    if (value < 0.0) {
        throw std::invalid_argument(std::string(name) + " cannot be negative.");
    }
}

void requireInClosedUnitInterval(double value, const char* name) {
    requireFinite(value, name);
    if (value < 0.0 || value > 1.0) {
        throw std::invalid_argument(std::string(name) + " must be in [0, 1].");
    }
}

void requireInHalfOpenUnitInterval(double value, const char* name) {
    requireFinite(value, name);
    if (value < 0.0 || value >= 1.0) {
        throw std::invalid_argument(std::string(name) + " must be in [0, 1).");
    }
}

void requireProbability(double probability, const char* name) {
    requireInClosedUnitInterval(probability, name);
}

void requirePositiveSize(std::size_t value, const char* name) {
    if (value == 0) {
        throw std::invalid_argument(std::string(name) + " must be greater than 0.");
    }
}

} // namespace abm
