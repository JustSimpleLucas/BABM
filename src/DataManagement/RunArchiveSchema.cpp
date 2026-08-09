// RunArchiveSchema.cpp

#include "DataManagement/RunArchiveSchema.h"

#include <algorithm>
#include <cctype>

namespace abm {
namespace {

bool isBlank(const std::string& value) {
    return std::all_of(value.cbegin(), value.cend(), [](const unsigned char character) {
        return std::isspace(character) != 0;
    });
}

bool requireText(const RunArchivePathRequirement& requirement, std::string& error) {
    if (!isBlank(requirement.path)) {
        return true;
    }
    error = "Prepared run archive is missing " + requirement.label + ".";
    return false;
}

} // namespace

std::vector<RunArchivePathRequirement> requiredRunArtifactPaths(const OutputConfig& output) {
    std::vector<RunArchivePathRequirement> requirements{
        {"step-timeseries CSV path", output.simulationCsvPath},
        {"agent-final-state CSV path", output.agentCsvPath},
        {"summary-metrics CSV path", output.summaryMetricsCsvPath},
        {"stylised-facts CSV path", output.stylisedFactsCsvPath},
        {"normalised config JSON path", output.configJsonPath},
        {"run metadata JSON path", output.metadataJsonPath},
        {"run log path", output.runLogPath},
    };

    if (output.tradeLedgerEnabled) {
        requirements.push_back({"trade-ledger CSV path", output.tradeLedgerCsvPath});
    }
    if (output.assetTimeseriesEnabled) {
        requirements.push_back({"asset-timeseries CSV path", output.assetTimeseriesCsvPath});
    }

    return requirements;
}

bool validatePreparedRunArchive(const RuntimeConfig& runtimeConfig, std::string& error) {
    const OutputConfig& output = runtimeConfig.output;

    if (output.experimentOutputEnabled) {
        if (!requireText({"run identifier", output.runId}, error)) {
            return false;
        }
        if (!requireText({"run directory path", output.runDirectoryPath}, error)) {
            return false;
        }
        if (!requireText({"experiment manifest CSV path", output.experimentManifestCsvPath},
                         error)) {
            return false;
        }
    }

    for (const RunArchivePathRequirement& requirement : requiredRunArtifactPaths(output)) {
        if (!requireText(requirement, error)) {
            return false;
        }
    }

    return true;
}

} // namespace abm
