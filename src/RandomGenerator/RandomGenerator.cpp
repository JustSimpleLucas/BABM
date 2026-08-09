// RandomGenerator.cpp

#include "RandomGenerator/RandomGenerator.h"

namespace abm {

RandomEngine::RandomEngine(std::uint64_t seed)
    : rng_(seed) {}

double RandomEngine::generateUniformDist(double minimum, double maximum) {
    std::uniform_real_distribution<double> dist(minimum, maximum);
    return dist(rng_);
}

int RandomEngine::generateUniformIntDist(int minimum, int maximum) {
    std::uniform_int_distribution<int> dist(minimum, maximum);
    return dist(rng_);
}

double RandomEngine::generateNormalDist(double mean, double stddev) {
    std::normal_distribution<double> dist(mean, stddev);
    return dist(rng_);
}

} // namespace abm
