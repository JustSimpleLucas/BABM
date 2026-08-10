// ConfigInspection.cpp

#include "Application/ConfigInspection.h"

#include "ControlParameters/ConfigKeyRegistry.h"

#include <algorithm>
#include <iomanip>
#include <ostream>
#include <vector>

namespace abm {
namespace {

using config_io_detail::ConfigKeyStatus;
using config_io_detail::ConfigSection;

constexpr char kPerAssetKeyPrefix[] = "asset.";
constexpr int kKeyColumnWidth = 44;

/** Sections in the order the reference and the resolved report present them. */
[[nodiscard]] const std::vector<ConfigSection>& reportedSections() {
    static const std::vector<ConfigSection> sections{
        ConfigSection::Assets,         ConfigSection::Population,   ConfigSection::RunControl,
        ConfigSection::Behavioural,    ConfigSection::Social,       ConfigSection::Microstructure,
        ConfigSection::Strategy,       ConfigSection::RiskAndCosts, ConfigSection::Output,
        ConfigSection::PostProcessing,
    };
    return sections;
}

[[nodiscard]] bool isPerAssetKey(const std::string& key) {
    return key.rfind(kPerAssetKeyPrefix, 0) == 0;
}

/** Per-asset assignments in file order, so they read as they were written. */
[[nodiscard]] std::vector<std::pair<std::string, std::string>>
perAssetAssignments(const ConfigProvenance& provenance) {
    std::vector<std::pair<std::size_t, std::pair<std::string, std::string>>> ordered;
    for (const auto& [key, assignment] : provenance) {
        if (isPerAssetKey(key)) {
            ordered.push_back({assignment.location.lineNumber, {key, assignment.value}});
        }
    }
    std::sort(ordered.begin(), ordered.end(),
              [](const auto& left, const auto& right) { return left.first < right.first; });

    std::vector<std::pair<std::string, std::string>> assignments;
    assignments.reserve(ordered.size());
    for (auto& entry : ordered) {
        assignments.push_back(std::move(entry.second));
    }
    return assignments;
}

void printAssignment(std::ostream& output, const std::string& key, const std::string& value) {
    output << "  " << std::left << std::setw(kKeyColumnWidth) << key << " = " << value << '\n';
}

/** Escapes the pipe characters that would otherwise break a markdown table cell. */
[[nodiscard]] std::string escapeTableCell(std::string_view text) {
    std::string escaped;
    escaped.reserve(text.size());
    for (const char character : text) {
        if (character == '|') {
            escaped += "\\|";
            continue;
        }
        escaped += character;
    }
    return escaped;
}

} // namespace

void printResolvedConfiguration(std::ostream& output, const RuntimeConfig& runtimeConfig) {
    output << "Configuration: " << runtimeConfig.sourcePath << "\n\n";

    const ConfigProvenance& provenance = runtimeConfig.provenance;
    const std::vector<std::pair<std::string, std::string>> assetAssignments =
        perAssetAssignments(provenance);

    for (const ConfigSection section : reportedSections()) {
        std::vector<std::pair<std::string, std::string>> rows;
        for (const auto& descriptor : config_io_detail::configKeyRegistry()) {
            if (descriptor.section != section) {
                continue;
            }
            const auto found = provenance.find(std::string(descriptor.key));
            if (found != provenance.end()) {
                rows.emplace_back(std::string(descriptor.key), found->second.value);
            }
        }
        if (section == ConfigSection::Assets) {
            rows.insert(rows.end(), assetAssignments.begin(), assetAssignments.end());
        }
        if (rows.empty()) {
            continue;
        }

        output << config_io_detail::configSectionName(section) << '\n';
        for (const auto& [key, value] : rows) {
            printAssignment(output, key, value);
        }
        output << '\n';
    }
}

void printDefaultedConfigKeys(std::ostream& output, const std::vector<std::string>& defaultedKeys) {
    if (defaultedKeys.empty()) {
        output << "Every configuration key was set explicitly.\n";
        return;
    }

    output << defaultedKeys.size()
           << (defaultedKeys.size() == 1 ? " setting was" : " settings were")
           << " absent from the file and used the built-in default:\n";
    for (const std::string& key : defaultedKeys) {
        output << "  " << key << '\n';
    }
    output << "The effective values are recorded in the run's config.json.\n";
}

void printConfigKeyReference(std::ostream& output) {
    output << "# Configuration key reference\n\n"
           << "Generated from the compiled-in key registry by `simulate --config-reference`.\n"
           << "Do not edit by hand: a CTest regenerates this file and fails on any difference.\n\n"
           << "`config/simulation.cfg` is read as plain `key = value` lines. Unknown keys are\n"
           << "rejected, and `assets = ...` must appear before any `asset.<name>.*` key because\n"
           << "per-asset settings are resolved against an already-declared universe.\n\n"
           << "Check a file without running anything:\n\n"
           << "```bash\n"
           << "build/debug/simulate --validate --config config/simulation.cfg\n"
           << "```\n";

    for (const ConfigSection section : reportedSections()) {
        std::vector<const config_io_detail::ConfigKeyDescriptor*> sectionKeys;
        for (const auto& descriptor : config_io_detail::configKeyRegistry()) {
            if (descriptor.section == section && descriptor.status == ConfigKeyStatus::Canonical) {
                sectionKeys.push_back(&descriptor);
            }
        }
        if (sectionKeys.empty()) {
            continue;
        }

        output << "\n## " << config_io_detail::configSectionName(section) << "\n\n"
               << "| Key | Units | Valid range | Description |\n"
               << "| --- | --- | --- | --- |\n";
        for (const auto* descriptor : sectionKeys) {
            output << "| `" << descriptor->key << "` | " << escapeTableCell(descriptor->units)
                   << " | " << escapeTableCell(descriptor->validRange) << " | "
                   << escapeTableCell(descriptor->documentation) << " |\n";
        }

        if (section == ConfigSection::Assets) {
            output << "\nEach declared asset is configured with `asset.<name>.<field>`:\n\n"
                   << "| Field | Units | Valid range | Description |\n"
                   << "| --- | --- | --- | --- |\n";
            for (const auto& field : config_io_detail::perAssetFieldRegistry()) {
                output << "| `" << field.field << "` | " << escapeTableCell(field.units) << " | "
                       << escapeTableCell(field.validRange) << " | "
                       << escapeTableCell(field.documentation) << " |\n";
            }
        }
    }

    std::vector<const config_io_detail::ConfigKeyDescriptor*> legacyKeys;
    for (const auto& descriptor : config_io_detail::configKeyRegistry()) {
        if (descriptor.status == ConfigKeyStatus::LegacyScalar) {
            legacyKeys.push_back(&descriptor);
        }
    }
    if (!legacyKeys.empty()) {
        output << "\n## Legacy single-asset spellings\n\n"
               << "Retained so studies that predate the multi-asset universe still load. They\n"
               << "configure the single implicit asset and cannot be combined with an\n"
               << "`assets = ...` declaration.\n\n"
               << "| Key | Units | Valid range | Description |\n"
               << "| --- | --- | --- | --- |\n";
        for (const auto* descriptor : legacyKeys) {
            output << "| `" << descriptor->key << "` | " << escapeTableCell(descriptor->units)
                   << " | " << escapeTableCell(descriptor->validRange) << " | "
                   << escapeTableCell(descriptor->documentation) << " |\n";
        }
    }
}

} // namespace abm
