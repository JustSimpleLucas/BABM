// StylisedFactCsvWriter.h

#ifndef OUTPUT_STYLISED_FACT_CSV_WRITER_H
#define OUTPUT_STYLISED_FACT_CSV_WRITER_H

#include <string>
#include <vector>

#include "Analysis/StylisedFactMetrics.h"

namespace abm::output_detail {

/**
 * Writes one screening block per traded asset to the stylised-facts artefact.
 *
 * Rows carry the asset they describe, so a multi-asset run reports an
 * independent verdict for every market instead of only the nominated primary.
 */
[[nodiscard]] bool exportStylisedFactsCsv(const std::string& outputPath,
                                          const std::vector<AssetRunMetrics>& assetMetrics,
                                          std::string& error);

} // namespace abm::output_detail

#endif // OUTPUT_STYLISED_FACT_CSV_WRITER_H
