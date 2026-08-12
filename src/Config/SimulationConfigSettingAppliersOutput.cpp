// SimulationConfigSettingAppliersOutput.cpp

#include "Config/SimulationConfigSettingAppliers.h"

namespace abm::config_io_detail {

bool applyExperimentOutputSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    OutputConfig& output = config.output;

    if (key == "experiment_output_enabled") {
        output.experimentOutputEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "experiment_root") {
        output.experimentRootPath = config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "experiment_name") {
        output.experimentName = config_parsing::parseString(setting.value);
        return true;
    }
    if (key == "run_label") {
        output.runLabel = config_parsing::parseString(setting.value);
        return true;
    }

    return false;
}

bool applyPythonOutputSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    OutputConfig& output = config.output;

    if (key == "python_analysis_enabled") {
        output.pythonAnalysisEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "python_analysis_python") {
        const std::string pythonPath = config_parsing::parseString(setting.value);
        const bool looksLikePath =
            pythonPath.find('/') != std::string::npos || pythonPath.find('\\') != std::string::npos;
        output.pythonAnalysisPythonPath =
            looksLikePath ? config_parsing::resolvePathValue(setting.path, setting.value)
                          : pythonPath;
        return true;
    }
    if (key == "python_analysis_generate_comparison") {
        output.pythonAnalysisComparisonEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "python_analysis_max_comparison_runs") {
        output.pythonAnalysisMaxComparisonRuns = parseSizeValue(setting);
        return true;
    }

    return false;
}

bool applyDatabaseOutputSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    OutputConfig& output = config.output;

    if (key == "database_output_enabled") {
        output.databaseOutputEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "database_url_env") {
        output.databaseUrlEnvironmentVariable = config_parsing::parseString(setting.value);
        return true;
    }
    if (key == "database_prune_after_import") {
        output.databasePruneAfterImport = parseBoolValue(setting);
        return true;
    }

    return false;
}

bool applyArtifactOutputSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    OutputConfig& output = config.output;

    if (key == "simulation_csv_output") {
        output.simulationCsvPath = config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "asset_timeseries_enabled") {
        output.assetTimeseriesEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "asset_timeseries_csv_output") {
        output.assetTimeseriesCsvPath =
            config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "agent_csv_output") {
        output.agentCsvPath = config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "trade_ledger_enabled") {
        output.tradeLedgerEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "trade_ledger_csv_output") {
        output.tradeLedgerCsvPath = config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "summary_metrics_csv_output") {
        output.summaryMetricsCsvPath =
            config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "stylised_facts_csv_output") {
        output.stylisedFactsCsvPath = config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "config_json_output") {
        output.configJsonPath = config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "metadata_json_output") {
        output.metadataJsonPath = config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }
    if (key == "run_log_output") {
        output.runLogPath = config_parsing::resolvePathValue(setting.path, setting.value);
        return true;
    }

    return false;
}

} // namespace abm::config_io_detail
