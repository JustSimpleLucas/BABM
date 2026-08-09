// RandomGenerator.h

#ifndef RANDOM_GENERATOR_H
#define RANDOM_GENERATOR_H

#include <algorithm>
#include <cstdint>
#include <random>

namespace abm {

/**
 * Deterministic random-number engine used by the simulation.
 *
 * A single explicit seed drives each engine instance. Keeping stochastic draws
 * behind this wrapper makes simulation runs reproducible and makes future
 * experiment metadata easier to audit.
 */
class RandomEngine {
public:
    explicit RandomEngine(std::uint64_t seed);

    /** Draws a real value uniformly from the closed interval accepted by STL. */
    [[nodiscard]] double generateUniformDist(double minimum, double maximum);

    /** Draws an integer uniformly from [minimum, maximum]. */
    [[nodiscard]] int generateUniformIntDist(int minimum, int maximum);

    /** Draws from a normal distribution with the supplied mean and standard deviation. */
    [[nodiscard]] double generateNormalDist(double mean, double stddev);

    /**
     * Randomly permutes a scheduler range using the same deterministic engine.
     *
     * This is used when the model needs fair random activation while preserving
     * exact reproducibility for a fixed simulation seed.
     */
    template <typename RandomIt>
    void shuffle(RandomIt first, RandomIt last) {
        std::shuffle(first, last, rng_);
    }

private:
    std::mt19937_64 rng_;
};

} // namespace abm

#endif // RANDOM_GENERATOR_H
