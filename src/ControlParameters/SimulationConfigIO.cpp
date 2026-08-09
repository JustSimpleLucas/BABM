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

RuntimeConfig loadRuntimeConfig(const std::string& configPath) {
    namespace fs = std::filesystem;

    const fs::path resolvedPath = fs::absolute(fs::path(configPath)).lexically_normal();
    std::ifstream input(resolvedPath);
    if (!input.is_open()) {
        throw std::runtime_error("Unable to open config file: " + resolvedPath.string());
    }

    RuntimeConfig config;
    config.sourcePath = resolvedPath.string();

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
            throw std::invalid_argument("Expected key=value format at " +
                                        config_parsing::describeLocation(resolvedPath, lineNumber) +
                                        '.');
        }

        const std::string key = config_parsing::trim(trimmed.substr(0, separator));
        const std::string value = config_parsing::trim(trimmed.substr(separator + 1));
        if (key.empty()) {
            throw std::invalid_argument("Missing key before '=' at " +
                                        config_parsing::describeLocation(resolvedPath, lineNumber) +
                                        '.');
        }
        if (value.empty()) {
            throw std::invalid_argument("Missing value for key '" + key + "' at " +
                                        config_parsing::describeLocation(resolvedPath, lineNumber) +
                                        '.');
        }

        config_io_detail::applyRuntimeConfigSetting(
            config, config_io_detail::ConfigSetting{key, value, resolvedPath, lineNumber});
    }

    return config;
}

} // namespace abm
