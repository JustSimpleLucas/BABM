// ConfigDiagnostics.cpp

#include "ControlParameters/ConfigDiagnostics.h"

#include <algorithm>
#include <sstream>

namespace abm {
namespace {

[[nodiscard]] std::string severityLabel(ConfigDiagnosticSeverity severity) {
    return severity == ConfigDiagnosticSeverity::Error ? "error" : "warning";
}

/*
 * Diagnostics without a line are sorted last. They come from constraints that
 * span several keys or from the file as a whole, so they read better as a
 * closing remark than interleaved among the line-anchored findings.
 */
[[nodiscard]] bool sortsBefore(const ConfigDiagnostic& left, const ConfigDiagnostic& right) {
    const bool leftLocated = left.location.lineNumber != 0;
    const bool rightLocated = right.location.lineNumber != 0;
    if (leftLocated != rightLocated) {
        return leftLocated;
    }
    return left.location.lineNumber < right.location.lineNumber;
}

} // namespace

std::size_t countConfigErrors(const std::vector<ConfigDiagnostic>& diagnostics) {
    return static_cast<std::size_t>(
        std::count_if(diagnostics.begin(), diagnostics.end(), [](const ConfigDiagnostic& entry) {
            return entry.severity == ConfigDiagnosticSeverity::Error;
        }));
}

std::string renderConfigDiagnostics(std::vector<ConfigDiagnostic> diagnostics) {
    std::stable_sort(diagnostics.begin(), diagnostics.end(), sortsBefore);

    std::ostringstream report;
    for (const ConfigDiagnostic& diagnostic : diagnostics) {
        if (!diagnostic.location.path.empty()) {
            report << diagnostic.location.path.string();
            if (diagnostic.location.lineNumber != 0) {
                report << ':' << diagnostic.location.lineNumber;
            }
            report << ": ";
        }
        report << severityLabel(diagnostic.severity) << ": " << diagnostic.message << '\n';
    }

    const std::size_t errorCount = countConfigErrors(diagnostics);
    const std::size_t warningCount = diagnostics.size() - errorCount;
    if (errorCount != 0) {
        report << errorCount << (errorCount == 1 ? " error" : " errors");
        if (warningCount != 0) {
            report << " and " << warningCount << (warningCount == 1 ? " warning" : " warnings");
        }
        report << " found.";
    }

    return report.str();
}

ConfigSourceLocation locateMessageKey(const std::string& message,
                                      const ConfigProvenance& provenance) {
    /*
     * Only parenthesised names are considered, and only when the name is a key
     * the file actually assigned. Prose can therefore never be mistaken for a
     * key, and a key mentioned in a message but absent from the file correctly
     * yields no location rather than a misleading one.
     */
    std::size_t searchFrom = 0;
    while (true) {
        const std::size_t open = message.find('(', searchFrom);
        if (open == std::string::npos) {
            return {};
        }
        const std::size_t close = message.find(')', open + 1);
        if (close == std::string::npos) {
            return {};
        }

        const auto found = provenance.find(message.substr(open + 1, close - open - 1));
        if (found != provenance.end()) {
            return found->second.location;
        }
        searchFrom = close + 1;
    }
}

} // namespace abm
