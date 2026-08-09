// ProcessMemoryUsage.h

#ifndef UTILITY_PROCESS_MEMORY_USAGE_H
#define UTILITY_PROCESS_MEMORY_USAGE_H

#include <cstddef>
#include <optional>

namespace abm {

/**
 * Point-in-time process memory diagnostic for interactive terminal reporting.
 *
 * These values describe operating-system process memory, not model variables or
 * empirical outputs. Keeping the diagnostic outside the simulation state ensures
 * that reproducible runs and archived research artifacts remain unaffected.
 */
struct ProcessMemoryUsage {
    /** Current resident set size, measured in bytes when the platform exposes it. */
    std::optional<std::size_t> residentSetBytes;

    /** Peak resident set size observed for this process, measured in bytes. */
    std::optional<std::size_t> peakResidentSetBytes;
};

/**
 * Samples process resident memory using the best available platform API.
 *
 * Unsupported platforms return empty optionals rather than failing the
 * simulation, because memory reporting is a convenience diagnostic only.
 */
[[nodiscard]] ProcessMemoryUsage sampleProcessMemoryUsage();

} // namespace abm

#endif // UTILITY_PROCESS_MEMORY_USAGE_H
