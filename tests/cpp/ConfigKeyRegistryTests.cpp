// ConfigKeyRegistryTests.cpp
//
// The registry is the single definition of the accepted configuration key set.
// These tests hold it to that claim from both sides: every registered key must
// be applied by the applier it names, and the shipped configuration must
// describe exactly the canonical keys the registry knows about.

#include "tests/cpp/TestSupport.h"

#include "Application/ConfigInspection.h"
#include "Config/ConfigDiagnostics.h"
#include "Config/ConfigKeyRegistry.h"
#include "Config/SimulationConfigIO.h"
#include "Config/SimulationConfigParsing.h"
#include "Config/SimulationConfigValidation.h"

#include <algorithm>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace {

using abm::config_io_detail::ConfigKeyStatus;
using abm::config_io_detail::ConfigSetting;

/** Keys assigned in a `key = value` config file, in file order. */
[[nodiscard]] std::vector<std::string> readAssignedKeys(const std::filesystem::path& configPath) {
    std::vector<std::string> keys;
    std::ifstream input(configPath);
    std::string line;
    while (std::getline(input, line)) {
        const std::string trimmed = abm::config_parsing::trim(line);
        if (trimmed.empty() || trimmed.front() == '#' || trimmed.front() == ';') {
            continue;
        }
        const std::size_t separator = trimmed.find('=');
        if (separator == std::string::npos) {
            continue;
        }
        keys.push_back(abm::config_parsing::trim(trimmed.substr(0, separator)));
    }
    return keys;
}

/**
 * Reports whether an applier claimed a key, regardless of the value parsing.
 *
 * A throwing applier has still claimed the key: it reached its own value parser
 * and rejected the placeholder. Only a false return means the applier does not
 * handle the key at all, which is the disagreement this test exists to catch.
 */
[[nodiscard]] bool applierClaimsKey(const abm::config_io_detail::ConfigKeyDescriptor& descriptor) {
    abm::RuntimeConfig config;
    const ConfigSetting setting{std::string(descriptor.key), "1", "registry_probe.cfg", 1};
    try {
        return descriptor.apply(config, setting);
    } catch (const std::exception&) {
        return true;
    }
}

void testEveryRegisteredKeyIsAppliedByItsOwnApplier(int& failures) {
    for (const auto& descriptor : abm::config_io_detail::configKeyRegistry()) {
        abm::test::expect(applierClaimsKey(descriptor),
                          "Registry key '" + std::string(descriptor.key) +
                              "' is not handled by the applier it is registered against.",
                          failures);
    }
}

void testShippedConfigCoversExactlyTheCanonicalKeys(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::path(ABM_PROJECT_ROOT) / "config" / "simulation.cfg";
    abm::test::expect(std::filesystem::exists(configPath),
                      "Shipped configuration is missing at " + configPath.string(), failures);
    if (!std::filesystem::exists(configPath)) {
        return;
    }

    std::set<std::string> canonicalRegistryKeys;
    for (const auto& descriptor : abm::config_io_detail::configKeyRegistry()) {
        if (descriptor.status == ConfigKeyStatus::Canonical) {
            canonicalRegistryKeys.insert(std::string(descriptor.key));
        }
    }

    std::set<std::string> perAssetFields;
    for (const auto& descriptor : abm::config_io_detail::perAssetFieldRegistry()) {
        perAssetFields.insert(std::string(descriptor.field));
    }

    std::set<std::string> configuredKeys;
    for (const std::string& key : readAssignedKeys(configPath)) {
        if (key.rfind("asset.", 0) == 0) {
            const std::size_t fieldSeparator = key.find('.', std::string("asset.").size());
            const std::string field = fieldSeparator == std::string::npos
                                          ? std::string{}
                                          : key.substr(fieldSeparator + 1);
            abm::test::expect(perAssetFields.count(field) == 1,
                              "Shipped configuration sets per-asset field '" + field +
                                  "' which the per-asset registry does not describe.",
                              failures);
            continue;
        }
        configuredKeys.insert(key);
    }

    for (const std::string& key : configuredKeys) {
        abm::test::expect(canonicalRegistryKeys.count(key) == 1,
                          "Shipped configuration sets '" + key +
                              "' which is not a canonical registry key.",
                          failures);
    }
    for (const std::string& key : canonicalRegistryKeys) {
        abm::test::expect(configuredKeys.count(key) == 1,
                          "Canonical registry key '" + key +
                              "' is absent from config/simulation.cfg, so a user copying the "
                              "shipped file would silently inherit its built-in default.",
                          failures);
    }
}

void testUnknownKeysAreRejectedWithASuggestion(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_registry_suggestion_test.cfg";
    {
        std::ofstream out(configPath);
        out << "social_hold_tolerence = 0.01\n";
    }

    std::string message;
    try {
        const abm::RuntimeConfig parsed = abm::loadRuntimeConfig(configPath.string());
        static_cast<void>(parsed);
    } catch (const std::exception& error) {
        message = error.what();
    }
    std::filesystem::remove(configPath);

    abm::test::expect(message.find("social_hold_tolerence") != std::string::npos,
                      "Unknown-key error should name the offending key.", failures);
    abm::test::expect(message.find("Did you mean 'social_hold_tolerance'?") != std::string::npos,
                      "Unknown-key error should suggest the nearest registry key, got: " + message,
                      failures);
}

void testUnrelatedKeysAttractNoSuggestion(int& failures) {
    const std::vector<std::string> suggestions =
        abm::config_io_detail::nearestConfigKeys("completely_unrelated_setting_name");
    abm::test::expect(suggestions.empty(),
                      "An unrelated key should not attract a misleading suggestion.", failures);
}

void testUnknownPerAssetFieldsAreRejectedWithASuggestion(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_registry_asset_field_test.cfg";
    {
        std::ofstream out(configPath);
        out << "assets = alpha\n";
        out << "asset.alpha.inital_price = 100.0\n";
    }

    std::string message;
    try {
        const abm::RuntimeConfig parsed = abm::loadRuntimeConfig(configPath.string());
        static_cast<void>(parsed);
    } catch (const std::exception& error) {
        message = error.what();
    }
    std::filesystem::remove(configPath);

    abm::test::expect(message.find("Did you mean 'initial_price'?") != std::string::npos,
                      "Unknown per-asset field should suggest the nearest field, got: " + message,
                      failures);
}

/** Writes a config file, reads it collecting diagnostics, and cleans up. */
[[nodiscard]] std::vector<abm::ConfigDiagnostic> diagnoseConfigText(const std::string& fileName,
                                                                    const std::string& text) {
    const std::filesystem::path configPath = std::filesystem::temp_directory_path() / fileName;
    {
        std::ofstream out(configPath);
        out << text;
    }

    std::vector<abm::ConfigDiagnostic> diagnostics;
    const abm::RuntimeConfig config = abm::readRuntimeConfig(configPath.string(), diagnostics);
    abm::collectSimulationConfigDiagnostics(config.simulation, config.provenance, diagnostics);
    std::filesystem::remove(configPath);
    return diagnostics;
}

void testOnePassReportsEveryMistake(int& failures) {
    /*
     * A malformed line, an unknown key, a single-field bound failure and a
     * cross-field constraint failure, all in one file. Before diagnostics were
     * collected this took four runs to discover.
     */
    const std::vector<abm::ConfigDiagnostic> diagnostics =
        diagnoseConfigText("abm_multi_error_test.cfg", "assets = alpha\n"
                                                       "primary_asset = alpha\n"
                                                       "num_noise_traders = 10\n"
                                                       "time_steps = 50\n"
                                                       "this_line_has_no_separator\n"
                                                       "social_hold_tolerence = 0.01\n"
                                                       "transaction_cost_rate = 1.5\n"
                                                       "chartist_short_window = 40\n"
                                                       "chartist_long_window = 20\n");

    abm::test::expect(abm::countConfigErrors(diagnostics) >= 4,
                      "one pass should report the malformed line, the unknown key, the "
                      "out-of-range rate and the window ordering together, got " +
                          std::to_string(abm::countConfigErrors(diagnostics)),
                      failures);

    const std::string report = abm::renderConfigDiagnostics(diagnostics);
    abm::test::expect(report.find("key = value") != std::string::npos,
                      "report should name the malformed line", failures);
    abm::test::expect(report.find("social_hold_tolerence") != std::string::npos,
                      "report should name the unknown key", failures);
    abm::test::expect(report.find("transaction_cost_rate") != std::string::npos,
                      "report should name the out-of-range transaction cost rate", failures);
    abm::test::expect(report.find("chartist_short_window") != std::string::npos,
                      "report should name the offending chartist window keys", failures);
}

void testDiagnosticsCarryTheOffendingLineAndValue(int& failures) {
    const std::vector<abm::ConfigDiagnostic> diagnostics =
        diagnoseConfigText("abm_provenance_test.cfg", "assets = alpha\n"
                                                      "primary_asset = alpha\n"
                                                      "num_noise_traders = 10\n"
                                                      "time_steps = 50\n"
                                                      "chartist_short_window = 40\n"
                                                      "chartist_long_window = 20\n");

    const std::string report = abm::renderConfigDiagnostics(diagnostics);
    abm::test::expect(report.find(":5:") != std::string::npos,
                      "a cross-field failure should point at the line that set the key, got: " +
                          report,
                      failures);
    abm::test::expect(
        report.find("= 40") != std::string::npos && report.find("= 20") != std::string::npos,
        "a cross-field failure should quote both offending values, got: " + report, failures);
}

void testUndeclaredAssetFailuresAreNotRepeated(int& failures) {
    /*
     * Every per-asset key fails for the same reason when the universe was never
     * declared. The report keeps the first and counts the rest so one mistake
     * does not bury the others.
     */
    const std::vector<abm::ConfigDiagnostic> diagnostics =
        diagnoseConfigText("abm_cascade_test.cfg", "asset.alpha.enabled = 1\n"
                                                   "asset.alpha.initial_price = 100.0\n"
                                                   "asset.alpha.initial_stock = 100\n"
                                                   "asset.alpha.price_tick_size = 0.01\n");

    const std::string report = abm::renderConfigDiagnostics(diagnostics);
    abm::test::expect(report.find("3 further per-asset settings") != std::string::npos,
                      "repeated per-asset failures should be summarised once, got: " + report,
                      failures);
}

void testValidConfigProducesNoDiagnostics(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::path(ABM_PROJECT_ROOT) / "config" / "simulation.cfg";
    if (!std::filesystem::exists(configPath)) {
        return;
    }

    std::vector<abm::ConfigDiagnostic> diagnostics;
    const abm::RuntimeConfig config = abm::readRuntimeConfig(configPath.string(), diagnostics);
    abm::collectSimulationConfigDiagnostics(config.simulation, config.provenance, diagnostics);

    abm::test::expect(diagnostics.empty(),
                      "the shipped configuration should produce no diagnostics, got: " +
                          abm::renderConfigDiagnostics(diagnostics),
                      failures);
}

void testAbsentKeysAreReportedAsDefaulted(int& failures) {
    const std::filesystem::path configPath =
        std::filesystem::temp_directory_path() / "abm_defaulted_test.cfg";
    {
        std::ofstream out(configPath);
        out << "assets = alpha\n"
            << "primary_asset = alpha\n"
            << "num_noise_traders = 10\n"
            << "time_steps = 50\n";
    }

    std::vector<abm::ConfigDiagnostic> diagnostics;
    const abm::RuntimeConfig config = abm::readRuntimeConfig(configPath.string(), diagnostics);
    std::filesystem::remove(configPath);

    const std::vector<std::string> defaulted = abm::findDefaultedConfigKeys(config);
    const auto contains = [&defaulted](const std::string& key) {
        return std::find(defaulted.begin(), defaulted.end(), key) != defaulted.end();
    };

    abm::test::expect(contains("seed"), "a key the file never sets should be reported as defaulted",
                      failures);
    abm::test::expect(!contains("time_steps"),
                      "a key the file sets should not be reported as defaulted", failures);
    abm::test::expect(!contains("initial_price"),
                      "legacy single-asset spellings should never count as defaulted, because "
                      "their absence is the expected state of a modern configuration",
                      failures);
}

void testGeneratedReferenceMatchesTheCommittedFile(int& failures) {
    /*
     * The committed reference is generated from the same registry the parser
     * uses. Regenerating it here and comparing means documentation cannot drift
     * from the accepted key set: adding a key without regenerating fails the
     * build, exactly as the CSV schema-sync test does across the C++/Python
     * boundary.
     */
    const std::filesystem::path referencePath =
        std::filesystem::path(ABM_PROJECT_ROOT) / "docs" / "config_reference.md";
    abm::test::expect(std::filesystem::exists(referencePath),
                      "docs/config_reference.md should be committed", failures);
    if (!std::filesystem::exists(referencePath)) {
        return;
    }

    std::ostringstream regenerated;
    abm::printConfigKeyReference(regenerated);

    std::ifstream committedInput(referencePath);
    const std::string committed((std::istreambuf_iterator<char>(committedInput)),
                                std::istreambuf_iterator<char>());

    abm::test::expect(regenerated.str() == committed,
                      "docs/config_reference.md is out of date. Regenerate it with: "
                      "build/debug/simulate --config-reference > docs/config_reference.md",
                      failures);
}

} // namespace

namespace abm::test {

void runConfigKeyRegistryTests(int& failures) {
    testGeneratedReferenceMatchesTheCommittedFile(failures);
    testEveryRegisteredKeyIsAppliedByItsOwnApplier(failures);
    testShippedConfigCoversExactlyTheCanonicalKeys(failures);
    testUnknownKeysAreRejectedWithASuggestion(failures);
    testUnrelatedKeysAttractNoSuggestion(failures);
    testUnknownPerAssetFieldsAreRejectedWithASuggestion(failures);
    testOnePassReportsEveryMistake(failures);
    testDiagnosticsCarryTheOffendingLineAndValue(failures);
    testUndeclaredAssetFailuresAreNotRepeated(failures);
    testValidConfigProducesNoDiagnostics(failures);
    testAbsentKeysAreReportedAsDefaulted(failures);
}

} // namespace abm::test
