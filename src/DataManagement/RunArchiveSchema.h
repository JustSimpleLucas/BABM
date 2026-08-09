// RunArchiveSchema.h

#ifndef DATA_MANAGEMENT_RUN_ARCHIVE_SCHEMA_H
#define DATA_MANAGEMENT_RUN_ARCHIVE_SCHEMA_H

#include <string>
#include <vector>

#include "ControlParameters/SimulationConfig.h"

namespace abm {

/** Describes one file destination required by the run archive contract. */
struct RunArchivePathRequirement {
    std::string label{};
    std::string path{};
};

/**
 * Returns the durable artifact paths expected for one completed simulation run.
 *
 * The trade ledger is included only when explicitly enabled because it is an
 * audit artifact rather than a core stylised-fact output. Keeping this rule in
 * one place prevents the application layer, tests, and documentation from
 * drifting apart as the archive format evolves.
 */
[[nodiscard]] std::vector<RunArchivePathRequirement>
requiredRunArtifactPaths(const OutputConfig& output);

/**
 * Validates the file-based archive contract after output layout preparation.
 *
 * This check deliberately validates structure only. It does not inspect model
 * state, market-clearing behaviour, or econometric diagnostics; those remain in
 * the simulation and analysis layers. The data-management boundary is therefore
 * limited to reproducible storage concerns: run identity, manifest destination,
 * and artifact paths.
 */
[[nodiscard]] bool validatePreparedRunArchive(const RuntimeConfig& runtimeConfig,
                                              std::string& error);

} // namespace abm

#endif // DATA_MANAGEMENT_RUN_ARCHIVE_SCHEMA_H
