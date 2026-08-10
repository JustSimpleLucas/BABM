// SimulationConfigSettingAppliers.h

#ifndef ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_SETTING_APPLIERS_H
#define ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_SETTING_APPLIERS_H

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>

#include "ControlParameters/SimulationConfig.h"
#include "ControlParameters/SimulationConfigParsing.h"

namespace abm::config_io_detail {

/** One parsed key-value setting with source location for reproducible diagnostics. */
struct ConfigSetting {
    std::string key;
    std::string value;
    std::filesystem::path path;
    std::size_t lineNumber;
};

inline config_parsing::ConfigValueContext parseContext(const ConfigSetting& setting) {
    return {setting.key, setting.path, setting.lineNumber};
}

inline double parseDoubleValue(const ConfigSetting& setting) {
    return config_parsing::parseDouble(setting.value, parseContext(setting));
}

inline std::size_t parseSizeValue(const ConfigSetting& setting) {
    return config_parsing::parseSize(setting.value, parseContext(setting));
}

inline std::uint64_t parseSeedValue(const ConfigSetting& setting) {
    return config_parsing::parseSeed(setting.value, parseContext(setting));
}

inline bool parseBoolValue(const ConfigSetting& setting) {
    return config_parsing::parseBool(setting.value, parseContext(setting));
}

inline FundamentalProcessType parseFundamentalProcessType(const ConfigSetting& setting) {
    return config_parsing::parseFundamentalProcessType(setting.value, setting.path,
                                                       setting.lineNumber);
}

void rejectRetiredSetting(const ConfigSetting& setting);

bool applyAssetSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyCoreSimulationSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyShortSaleSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyTransactionCostSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyWarmupPriceSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyMicrostructureSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyControlSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyFundamentalistSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyChartistSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyNoiseTraderSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyBuyAndHoldSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applySocialSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyExperimentOutputSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyPythonOutputSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyDatabaseOutputSetting(RuntimeConfig& config, const ConfigSetting& setting);
bool applyArtifactOutputSetting(RuntimeConfig& config, const ConfigSetting& setting);

void applyRuntimeConfigSetting(RuntimeConfig& config, const ConfigSetting& setting);

} // namespace abm::config_io_detail

#endif // ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_SETTING_APPLIERS_H
