// ConfigKeyRegistry.h

#ifndef ABM_CONFIG_CONFIG_KEY_REGISTRY_H
#define ABM_CONFIG_CONFIG_KEY_REGISTRY_H

#include "Config/SimulationConfigSettingAppliers.h"

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace abm::config_io_detail {

/**
 * Research-facing grouping of configuration keys.
 *
 * The sections match the parameter groups a reader of the thesis would expect
 * (assets, population, behavioural preferences, and so on) rather than the C++
 * struct layout, because the registry drives user-facing output: the resolved
 * configuration printed by --validate and the generated key reference.
 */
enum class ConfigSection {
    Assets,
    Population,
    Protagonist,
    RunControl,
    Behavioural,
    Social,
    Microstructure,
    Strategy,
    RiskAndCosts,
    Output,
    PostProcessing,
};

/**
 * Whether a key is part of the current schema or a retained legacy spelling.
 *
 * Legacy scalar keys configure the single implicit asset and are mutually
 * exclusive with an `assets = ...` declaration. They are absent from the shipped
 * configuration on purpose, so the defaulted-key report must not treat their
 * absence as an omission.
 */
enum class ConfigKeyStatus {
    Canonical,
    LegacyScalar,
};

/**
 * One configuration key: how it is applied, and how it is described to a reader.
 *
 * `validRange` documents the constraint that validateSimulationConfig enforces
 * for this key. The validator remains authoritative; this text exists so the
 * generated reference and the --validate output can state the constraint
 * without a reader having to open the C++ source.
 */
struct ConfigKeyDescriptor {
    std::string_view key;
    ConfigSection section;
    ConfigKeyStatus status;
    std::string_view units;
    std::string_view validRange;
    std::string_view documentation;
    bool (*apply)(RuntimeConfig&, const ConfigSetting&);
};

/** One field of the `asset.<name>.<field>` key family. */
struct PerAssetFieldDescriptor {
    std::string_view field;
    std::string_view units;
    std::string_view validRange;
    std::string_view documentation;
};

[[nodiscard]] std::string_view configSectionName(ConfigSection section);

/**
 * Every exact configuration key the parser accepts, in reference order.
 *
 * This is the single gate used by applyRuntimeConfigSetting: a key absent from
 * this table is rejected, so the domain applier functions cannot accept a key
 * the registry does not describe.
 */
[[nodiscard]] const std::vector<ConfigKeyDescriptor>& configKeyRegistry();

/** Every field accepted after an `asset.<name>.` prefix. */
[[nodiscard]] const std::vector<PerAssetFieldDescriptor>& perAssetFieldRegistry();

/** Returns the descriptor for an exact key, or nullptr when the key is unknown. */
[[nodiscard]] const ConfigKeyDescriptor* findConfigKey(std::string_view key);

/**
 * Suggests the closest known keys for a misspelling.
 *
 * Uses Levenshtein distance with a cutoff, so an unrelated key never produces a
 * misleading suggestion. Returns an empty vector when nothing is close enough.
 */
[[nodiscard]] std::vector<std::string> nearestConfigKeys(const std::string& key,
                                                         std::size_t maximumSuggestions = 2);

/** Suggests the closest known per-asset field names for a misspelling. */
[[nodiscard]] std::vector<std::string> nearestPerAssetFields(const std::string& field,
                                                             std::size_t maximumSuggestions = 2);

/**
 * Renders one or more suggestions as a trailing sentence.
 *
 * Returns an empty string when there is nothing close enough to suggest, so
 * callers can append the result unconditionally.
 */
[[nodiscard]] std::string describeSuggestions(const std::vector<std::string>& suggestions);

} // namespace abm::config_io_detail

namespace abm {

/**
 * Canonical keys the configuration file did not set, in reference order.
 *
 * A key absent from the file silently takes its built-in default. For a thesis
 * that is a reproducibility gap rather than a convenience, so the absences are
 * reported rather than left implicit. Legacy single-asset spellings are excluded
 * because their absence is the expected state of a modern configuration.
 */
[[nodiscard]] std::vector<std::string> findDefaultedConfigKeys(const RuntimeConfig& runtimeConfig);

} // namespace abm

#endif // ABM_CONFIG_CONFIG_KEY_REGISTRY_H
