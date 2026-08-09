// AgentSnapshotCsvWriter.h

#ifndef OUTPUT_AGENT_SNAPSHOT_CSV_WRITER_H
#define OUTPUT_AGENT_SNAPSHOT_CSV_WRITER_H

#include <string>

namespace abm {
class SimulationRunResult;

namespace output_detail {

[[nodiscard]] bool exportAgentDetailsCsv(const std::string& outputPath,
                                         const SimulationRunResult& result, std::string& error);

} // namespace output_detail
} // namespace abm

#endif // OUTPUT_AGENT_SNAPSHOT_CSV_WRITER_H
