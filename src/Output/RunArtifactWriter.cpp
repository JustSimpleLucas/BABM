// RunArtifactWriter.cpp

#include "Output/RunArtifactWriter.h"

#include "Output/AgentSnapshotCsvWriter.h"
#include "Output/AssetTimeseriesCsvWriter.h"
#include "Output/ExperimentManifestWriter.h"
#include "Output/OutputSerialization.h"
#include "Output/ProtagonistTimeseriesCsvWriter.h"
#include "Output/RunMetadataWriters.h"
#include "Output/RunSummaryCsvWriter.h"
#include "Output/StepTimeseriesCsvWriter.h"
#include "Output/StylisedFactCsvWriter.h"
#include "Output/TradeLedgerCsvWriter.h"
#include "Results/SimulationRunResult.h"

namespace abm {

bool RunArtifactWriter::writeCompletedRun(const RuntimeConfig& runtimeConfig,
                                          const SimulationRunResult& simulationResult,
                                          const RunMetrics& metrics, RunArtifactWriteResult& result,
                                          std::string& error) {
    const std::string normalizedConfigJson =
        output_detail::buildNormalizedConfigJson(simulationResult.config());
    result.configHash = output_detail::stableConfigHash(normalizedConfigJson);

    if (!output_detail::exportSimulationDetailsCsv(runtimeConfig.output.simulationCsvPath,
                                                   simulationResult, error)) {
        error = "CSV export failed: " + error;
        return false;
    }
    if (!output_detail::exportAgentDetailsCsv(runtimeConfig.output.agentCsvPath, simulationResult,
                                              error)) {
        error = "Agent CSV export failed: " + error;
        return false;
    }
    if (runtimeConfig.output.assetTimeseriesEnabled) {
        if (!output_detail::exportAssetTimeseriesCsv(runtimeConfig.output.assetTimeseriesCsvPath,
                                                     simulationResult, error)) {
            error = "Asset timeseries CSV export failed: " + error;
            return false;
        }
    }
    /*
     * Gated on the protagonist rather than on an output switch of its own: the
     * series has no meaning without him, so a separate enable key could only
     * ever be set to a value the model already implies.
     */
    if (simulationResult.config().protagonist.enabled) {
        if (!output_detail::exportProtagonistTimeseriesCsv(
                runtimeConfig.output.protagonistTimeseriesCsvPath, simulationResult, error)) {
            error = "Protagonist timeseries CSV export failed: " + error;
            return false;
        }
    }
    if (runtimeConfig.output.tradeLedgerEnabled) {
        if (!output_detail::exportTradeLedgerCsv(runtimeConfig.output.tradeLedgerCsvPath,
                                                 simulationResult, error)) {
            error = "Trade ledger CSV export failed: " + error;
            return false;
        }
    }
    if (!output_detail::exportSummaryMetricsCsv(runtimeConfig.output.summaryMetricsCsvPath,
                                                runtimeConfig, simulationResult, metrics,
                                                result.configHash, error)) {
        error = "Summary metrics CSV export failed: " + error;
        return false;
    }
    /*
     * The run-level `metrics` argument screens the primary asset and feeds the
     * single-row summary artefacts. The stylised-facts artefact instead screens
     * every asset on identical terms, so it derives its own per-asset metrics.
     */
    if (!output_detail::exportStylisedFactsCsv(runtimeConfig.output.stylisedFactsCsvPath,
                                               calculateAssetRunMetrics(simulationResult), error)) {
        error = "Stylised-facts CSV export failed: " + error;
        return false;
    }
    if (!output_detail::exportConfigJson(
            output_detail::ConfigJsonExportRequest{runtimeConfig.output.configJsonPath,
                                                   normalizedConfigJson},
            error)) {
        error = "Config JSON export failed: " + error;
        return false;
    }
    if (!output_detail::exportMetadataJson(runtimeConfig.output.metadataJsonPath, runtimeConfig,
                                           simulationResult, metrics, result.configHash, error)) {
        error = "Metadata JSON export failed: " + error;
        return false;
    }
    if (!output_detail::exportRunLog(runtimeConfig.output.runLogPath, runtimeConfig,
                                     simulationResult, metrics, result.configHash, error)) {
        error = "Run log export failed: " + error;
        return false;
    }
    if (!appendExperimentManifest(runtimeConfig, simulationResult, metrics, result.configHash,
                                  error)) {
        error = "Experiment manifest export failed: " + error;
        return false;
    }

    return true;
}

} // namespace abm
