// SimulationConfigSettingAppliers.cpp

#include "Config/SimulationConfigSettingAppliers.h"

#include "Config/ConfigKeyRegistry.h"

#include <stdexcept>

namespace abm::config_io_detail {

/**
 * Applies one parsed setting, using the key registry as the sole gate.
 *
 * Dispatching through the registry rather than trying each domain applier in
 * turn means the accepted key set has exactly one definition. An applier cannot
 * quietly accept a key the registry does not describe, so the generated key
 * reference, the "did you mean" suggestions, and the defaulted-key report all
 * stay in step with the parser by construction.
 */
void applyRuntimeConfigSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    rejectRetiredSetting(setting);

    if (const ConfigKeyDescriptor* descriptor = findConfigKey(setting.key)) {
        if (descriptor->apply(config, setting)) {
            return;
        }
        /*
         * The registry named an applier that then refused the key. That is a
         * programming error in the registry table, not a user configuration
         * error, so it is reported separately from the unknown-key path.
         */
        throw std::logic_error("Config key '" + setting.key +
                               "' is registered against an applier that does not handle it.");
    }

    // The asset.<name>.<field> family is matched by prefix rather than exact key.
    if (applyAssetSetting(config, setting)) {
        return;
    }

    throw std::invalid_argument("Unknown config key '" + setting.key + "' at " +
                                config_parsing::describeLocation(setting.path, setting.lineNumber) +
                                '.' + describeSuggestions(nearestConfigKeys(setting.key)));
}

} // namespace abm::config_io_detail
