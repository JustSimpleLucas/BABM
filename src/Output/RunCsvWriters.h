// RunCsvWriters.h

#ifndef OUTPUT_RUN_CSV_WRITERS_H
#define OUTPUT_RUN_CSV_WRITERS_H

/*
 * Compatibility facade for the CSV writer family.
 *
 * New output code should include the artefact-specific writer header matching
 * the file it produces. This facade keeps older call sites valid while the
 * implementation is split by output responsibility.
 */
#include "Output/AgentSnapshotCsvWriter.h"
#include "Output/RunSummaryCsvWriter.h"
#include "Output/StepTimeseriesCsvWriter.h"
#include "Output/StylisedFactCsvWriter.h"
#include "Output/TradeLedgerCsvWriter.h"

#endif // OUTPUT_RUN_CSV_WRITERS_H
