// SimulationConfigIO.cpp

#include "ControlParameters/SimulationConfigIO.h"

#include "ControlParameters/SimulationConfigParsing.h"
#include "ControlParameters/SimulationConfigSettingAppliers.h"

#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace abm {
namespace {

constexpr char kPerAssetKeyPrefix[] = "asset.";

/*
 * Text every per-asset failure carries when the asset universe was never
 * successfully declared. One mistake in the `assets` line makes every
 * asset.<name>.* key fail for the same reason, so the report keeps the first
 * occurrence and counts the rest rather than repeating itself sixteen times.
 */
constexpr char kUndeclaredAssetMarker[] = "Declare it first with 'assets = ...'";

[[nodiscard]] bool isPerAssetKey(const std::string& key) {
    return key.rfind(kPerAssetKeyPrefix, 0) == 0;
}

/**
 * Removes the source location an applier embedded in its own message.
 *
 * Applier exceptions are self-describing so that code catching one directly
 * still learns where the problem is. A collected diagnostic already carries the
 * location and prints it as a prefix, so the embedded copy would be printed
 * twice. The removed text is reconstructed from the same path and line the
 * message was built with, so this only ever strikes the exact phrase the
 * applier added.
 */
[[nodiscard]] std::string withoutEmbeddedLocation(std::string message,
                                                  const std::filesystem::path& path,
                                                  std::size_t lineNumber) {
    const std::string embedded = " at " + config_parsing::describeLocation(path, lineNumber);
    const std::size_t position = message.find(embedded);
    if (position != std::string::npos) {
        message.erase(position, embedded.size());
    }
    return message;
}

} // namespace

std::string findDefaultRuntimeConfigPath(const std::string& executablePath) {
    namespace fs = std::filesystem;

    std::vector<fs::path> candidates;
    candidates.push_back(fs::current_path() / "config" / "simulation.cfg");

    if (!executablePath.empty()) {
        const fs::path executable = fs::absolute(fs::path(executablePath));
        const fs::path executableDir = executable.parent_path();
        if (!executableDir.empty()) {
            candidates.push_back(executableDir / "config" / "simulation.cfg");
            if (!executableDir.parent_path().empty()) {
                candidates.push_back(executableDir.parent_path() / "config" / "simulation.cfg");
            }
        }
    }

    for (const fs::path& candidate : candidates) {
        if (fs::exists(candidate)) {
            return candidate.lexically_normal().string();
        }
    }

    std::ostringstream error;
    error << "Could not find config/simulation.cfg. Checked:";
    for (const fs::path& candidate : candidates) {
        error << ' ' << candidate.lexically_normal().string();
    }
    throw std::runtime_error(error.str());
}

RuntimeConfig readRuntimeConfig(const std::string& configPath,
                                std::vector<ConfigDiagnostic>& diagnostics) {
    namespace fs = std::filesystem;

    const fs::path resolvedPath = fs::absolute(fs::path(configPath)).lexically_normal();
    std::ifstream input(resolvedPath);
    if (!input.is_open()) {
        // An unreadable file leaves nothing to diagnose, so this stays fatal.
        throw std::runtime_error("Unable to open config file: " + resolvedPath.string());
    }

    RuntimeConfig config;
    config.sourcePath = resolvedPath.string();

    const auto reportError = [&diagnostics, &resolvedPath](std::string message,
                                                           std::size_t lineNumber) {
        diagnostics.push_back(ConfigDiagnostic{ConfigDiagnosticSeverity::Error, std::move(message),
                                               ConfigSourceLocation{resolvedPath, lineNumber}});
    };

    std::size_t suppressedPerAssetFailures = 0;
    bool reportedUndeclaredAssets = false;

    std::string line;
    std::size_t lineNumber = 0;
    while (std::getline(input, line)) {
        ++lineNumber;

        const std::string trimmed = config_parsing::trim(line);
        if (trimmed.empty() || trimmed.front() == '#' || trimmed.front() == ';') {
            continue;
        }

        const std::size_t separator = trimmed.find('=');
        if (separator == std::string::npos) {
            reportError("expected key = value format.", lineNumber);
            continue;
        }

        const std::string key = config_parsing::trim(trimmed.substr(0, separator));
        const std::string value = config_parsing::trim(trimmed.substr(separator + 1));
        if (key.empty()) {
            reportError("missing key before '='.", lineNumber);
            continue;
        }
        if (value.empty()) {
            reportError("missing value for key '" + key + "'.", lineNumber);
            continue;
        }

        config.provenance[key] =
            ConfigAssignment{ConfigSourceLocation{resolvedPath, lineNumber}, value};

        try {
            config_io_detail::applyRuntimeConfigSetting(
                config, config_io_detail::ConfigSetting{key, value, resolvedPath, lineNumber});
        } catch (const std::exception& error) {
            std::string message = withoutEmbeddedLocation(error.what(), resolvedPath, lineNumber);
            const bool cascadesFromUndeclaredAssets =
                isPerAssetKey(key) && message.find(kUndeclaredAssetMarker) != std::string::npos;

            if (cascadesFromUndeclaredAssets && reportedUndeclaredAssets) {
                ++suppressedPerAssetFailures;
                continue;
            }
            if (cascadesFromUndeclaredAssets) {
                reportedUndeclaredAssets = true;
            }
            reportError(std::move(message), lineNumber);
        }
    }

    if (suppressedPerAssetFailures != 0) {
        diagnostics.push_back(ConfigDiagnostic{
            ConfigDiagnosticSeverity::Error,
            std::to_string(suppressedPerAssetFailures) +
                " further per-asset settings could not be applied for the same reason. Fix the "
                "'assets = ...' declaration first.",
            ConfigSourceLocation{resolvedPath, 0}});
    }

    return config;
}

RuntimeConfig loadRuntimeConfig(const std::string& configPath) {
    std::vector<ConfigDiagnostic> diagnostics;
    RuntimeConfig config = readRuntimeConfig(configPath, diagnostics);
    if (countConfigErrors(diagnostics) != 0) {
        throw std::invalid_argument(renderConfigDiagnostics(std::move(diagnostics)));
    }
    return config;
}

} // namespace abm
