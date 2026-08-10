// ExperimentDataWorkflow.cpp

#include "DataManagement/ExperimentDataWorkflow.h"

#include "DataManagement/RunArchiveSchema.h"
#include "Experiment/ExperimentRunManager.h"

namespace abm {

bool ExperimentDataWorkflow::prepareRunArchive(RuntimeConfig& runtimeConfig, std::string& error) {
    if (!ExperimentRunManager::prepareOutputLayout(runtimeConfig, error)) {
        return false;
    }
    if (!validatePreparedRunArchive(runtimeConfig, error)) {
        return false;
    }
    return true;
}

bool ExperimentDataWorkflow::writeCompletedRun(const RuntimeConfig& runtimeConfig,
                                               const SimulationRunResult& simulationResult,
                                               const RunMetrics& metrics,
                                               RunArtifactWriteResult& result, std::string& error) {
    if (!validatePreparedRunArchive(runtimeConfig, error)) {
        return false;
    }

    return RunArtifactWriter::writeCompletedRun(runtimeConfig, simulationResult, metrics, result,
                                                error);
}

} // namespace abm
