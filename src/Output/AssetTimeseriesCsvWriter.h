// AssetTimeseriesCsvWriter.h

#ifndef ABM_OUTPUT_ASSET_TIMESERIES_CSV_WRITER_H
#define ABM_OUTPUT_ASSET_TIMESERIES_CSV_WRITER_H

#include <string>

namespace abm {
class SimulationRunResult;

namespace output_detail {

/**
 * Exports the long-format per-asset time series (one row per phase row and
 * asset). Row and phase semantics mirror step_timeseries.csv; the primary
 * asset's values there are a projection of this artefact.
 */
bool exportAssetTimeseriesCsv(const std::string& outputPath, const SimulationRunResult& result,
                              std::string& error);

} // namespace output_detail
} // namespace abm

#endif // ABM_OUTPUT_ASSET_TIMESERIES_CSV_WRITER_H
