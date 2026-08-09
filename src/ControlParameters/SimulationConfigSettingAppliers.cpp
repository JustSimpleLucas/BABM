// SimulationConfigSettingAppliers.cpp

#include "ControlParameters/SimulationConfigSettingAppliers.h"

#include <array>
#include <stdexcept>

namespace abm::config_io_detail {

void applyRuntimeConfigSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    using SettingApplier = bool (*)(RuntimeConfig&, const ConfigSetting&);
    constexpr std::array<SettingApplier, 16> settingAppliers{{
        applyAssetSetting,
        applyCoreSimulationSetting,
        applyShortSaleSetting,
        applyTransactionCostSetting,
        applyWarmupPriceSetting,
        applyMicrostructureSetting,
        applyControlSetting,
        applyFundamentalistSetting,
        applyChartistSetting,
        applyNoiseTraderSetting,
        applyBuyAndHoldSetting,
        applySocialSetting,
        applyExperimentOutputSetting,
        applyPythonOutputSetting,
        applyDatabaseOutputSetting,
        applyArtifactOutputSetting,
    }};

    rejectRetiredSetting(setting);

    for (const SettingApplier apply : settingAppliers) {
        if (apply(config, setting)) {
            return;
        }
    }

    throw std::invalid_argument("Unknown config key '" + setting.key + "' at " +
                                config_parsing::describeLocation(setting.path, setting.lineNumber) +
                                '.');
}

} // namespace abm::config_io_detail
