// ProcessMemoryUsage.cpp

#include "Utility/ProcessMemoryUsage.h"

#include <cstdint>
#include <limits>

#if defined(__APPLE__) || defined(__linux__)
#include <sys/resource.h>
#endif

#if defined(__APPLE__)
#include <mach/mach.h>
#elif defined(__linux__)
#include <fstream>
#include <unistd.h>
#endif

namespace abm {
namespace {

#if defined(__linux__)
[[nodiscard]] std::optional<std::size_t> multiplyToSize(std::uint64_t value,
                                                        std::uint64_t multiplier) {
    if (multiplier != 0U && value > std::numeric_limits<std::size_t>::max() / multiplier) {
        return std::nullopt;
    }
    return static_cast<std::size_t>(value * multiplier);
}
#endif

[[nodiscard]] std::optional<std::size_t> currentResidentSetBytes() {
#if defined(__APPLE__)
    mach_task_basic_info_data_t info{};
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    const kern_return_t status = task_info(mach_task_self(), MACH_TASK_BASIC_INFO,
                                           reinterpret_cast<task_info_t>(&info), &count);
    if (status != KERN_SUCCESS) {
        return std::nullopt;
    }
    return static_cast<std::size_t>(info.resident_size);
#elif defined(__linux__)
    std::ifstream statm("/proc/self/statm");
    std::uint64_t totalPages = 0U;
    std::uint64_t residentPages = 0U;
    if (!(statm >> totalPages >> residentPages)) {
        return std::nullopt;
    }
    static_cast<void>(totalPages);

    const long pageSize = sysconf(_SC_PAGESIZE);
    if (pageSize <= 0) {
        return std::nullopt;
    }
    return multiplyToSize(residentPages, static_cast<std::uint64_t>(pageSize));
#else
    return std::nullopt;
#endif
}

[[nodiscard]] std::optional<std::size_t> peakResidentSetBytes() {
#if defined(__APPLE__) || defined(__linux__)
    rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage) != 0) {
        return std::nullopt;
    }
#if defined(__APPLE__)
    return static_cast<std::size_t>(usage.ru_maxrss);
#else
    return multiplyToSize(static_cast<std::uint64_t>(usage.ru_maxrss), 1024U);
#endif
#else
    return std::nullopt;
#endif
}

} // namespace

ProcessMemoryUsage sampleProcessMemoryUsage() {
    return ProcessMemoryUsage{currentResidentSetBytes(), peakResidentSetBytes()};
}

} // namespace abm
