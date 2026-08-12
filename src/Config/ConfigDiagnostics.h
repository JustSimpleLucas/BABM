// ConfigDiagnostics.h

#ifndef ABM_CONFIG_CONFIG_DIAGNOSTICS_H
#define ABM_CONFIG_CONFIG_DIAGNOSTICS_H

#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace abm {

/** Where a configuration key was assigned. */
struct ConfigSourceLocation {
    std::filesystem::path path;
    std::size_t lineNumber{0};
};

/** One key as it was written in the configuration file. */
struct ConfigAssignment {
    ConfigSourceLocation location;
    std::string value;
};

/**
 * Records where and how each key was assigned.
 *
 * Validation runs on the resolved configuration, long after the file has been
 * read, so without this the constraint failures could name a parameter but not
 * the line a reader has to edit. It also identifies which keys the file did not
 * set, which is what makes silently defaulted settings reportable. Keeping
 * provenance on RuntimeConfig rather than SimulationConfig keeps it out of the
 * archived config.json and its hash, so run comparability is unaffected.
 */
using ConfigProvenance = std::map<std::string, ConfigAssignment>;

enum class ConfigDiagnosticSeverity { Error, Warning };

/** One problem found while reading or validating a configuration. */
struct ConfigDiagnostic {
    ConfigDiagnosticSeverity severity{ConfigDiagnosticSeverity::Error};
    std::string message;
    ConfigSourceLocation location{};
};

/** Returns how many diagnostics are errors rather than warnings. */
[[nodiscard]] std::size_t countConfigErrors(const std::vector<ConfigDiagnostic>& diagnostics);

/**
 * Renders every diagnostic as one report ordered by source line.
 *
 * Reporting the whole set at once is what turns configuration editing from a
 * fix-one-rerun loop into a single pass, which matters most for the long runs
 * this model is used for.
 */
[[nodiscard]] std::string renderConfigDiagnostics(std::vector<ConfigDiagnostic> diagnostics);

/**
 * Finds the source location for a validation message by the config key it names.
 *
 * Validation messages name their parameter in parentheses, for example
 * "... (chartist_short_window) ...". Only names that are real registry keys are
 * matched, so ordinary prose can never be mistaken for a key.
 */
[[nodiscard]] ConfigSourceLocation locateMessageKey(const std::string& message,
                                                    const ConfigProvenance& provenance);

} // namespace abm

#endif // ABM_CONFIG_CONFIG_DIAGNOSTICS_H
