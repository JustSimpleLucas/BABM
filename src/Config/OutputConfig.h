// OutputConfig.h

#ifndef ABM_CONFIG_OUTPUT_CONFIG_H
#define ABM_CONFIG_OUTPUT_CONFIG_H

#include <cstddef>
#include <string>

#include "Config/ConfigDiagnostics.h"
#include "Config/ModelConfig.h"

namespace abm {

/** Output paths for reproducible simulation artefacts. */
struct OutputConfig {
    /** Enables one-folder-per-run experiment archiving when true. */
    bool experimentOutputEnabled{false};

    /** Root directory where experiment folders are stored. */
    std::string experimentRootPath{"data/experiments"};

    /** Human-readable experiment family, for example prospect_theory_sweep. */
    std::string experimentName{"default_experiment"};

    /** Human-readable label for the current run, for example baseline. */
    std::string runLabel{"baseline"};

    /** Local timestamp recorded when the run archive is prepared. */
    std::string createdAtLocal;

    /** Machine-readable identifier assigned when experiment archiving is enabled. */
    std::string runId;

    /** Directory containing all artefacts for the current run. */
    std::string runDirectoryPath;

    /** Experiment-level manifest used to compare all runs in one table. */
    std::string experimentManifestCsvPath;

    /** Per-step market, fundamental-value, order-flow, and return diagnostics. */
    std::string simulationCsvPath{"data/latest/step_timeseries.csv"};

    /** Enables the long-format per-asset time series artefact when true. */
    bool assetTimeseriesEnabled{true};

    /** Long-format per-(step, asset) diagnostics path. */
    std::string assetTimeseriesCsvPath{"data/latest/asset_timeseries.csv"};

    /** Final cross-sectional state of all agents after the simulation run. */
    std::string agentCsvPath{"data/latest/agents_final.csv"};

    /**
     * Enables the detailed trade ledger when true.
     *
     * The ledger is an audit and microstructure diagnostic artefact, not a
     * behavioural model input. It is disabled by default because large
     * calibration sweeps can generate many trade rows that are unnecessary for
     * stylised-fact screening and consume substantial memory.
     */
    bool tradeLedgerEnabled{false};

    /** Agent-facing trade-ledger path used only when tradeLedgerEnabled is true. */
    std::string tradeLedgerCsvPath{"data/latest/trade_ledger.csv"};

    /** One-row CSV of run-level statistics useful for parameter sweeps. */
    std::string summaryMetricsCsvPath{"data/latest/summary_metrics.csv"};

    /** Compact stylised-fact screening diagnostics generated from log returns. */
    std::string stylisedFactsCsvPath{"data/latest/stylised_facts.csv"};

    /** Normalised JSON snapshot of all model parameters used for the run. */
    std::string configJsonPath{"data/latest/config.json"};

    /** Machine-readable provenance record for the run. */
    std::string metadataJsonPath{"data/latest/metadata.json"};

    /** Human-readable run transcript, stored under logs/ like archived runs. */
    std::string runLogPath{"data/latest/logs/run.log"};

    /** Enables PostgreSQL import after the simulator writes staging artefacts. */
    bool databaseOutputEnabled{false};

    /** Environment variable containing the PostgreSQL connection URL. */
    std::string databaseUrlEnvironmentVariable{"ABM_DATABASE_URL"};

    /** Deletes CSV/JSON/log staging artefacts after a successful PostgreSQL import. */
    bool databasePruneAfterImport{false};

    /** Runs the Python Plotly analysis automatically after C++ artefacts finish writing. */
    bool pythonAnalysisEnabled{true};

    /** Python interpreter used for post-run visualisation, usually the project virtualenv. */
    std::string pythonAnalysisPythonPath{"python3"};

    /** Refreshes an experiment-level comparison report after each archived run. */
    bool pythonAnalysisComparisonEnabled{true};

    /** Maximum number of runs shown in dense automatic comparison report panels. */
    std::size_t pythonAnalysisMaxComparisonRuns{8};
};

/** Runtime configuration plus provenance of the file used to create it. */
struct RuntimeConfig {
    SimulationConfig simulation{};
    OutputConfig output{};
    std::string sourcePath;

    /**
     * Line each key was assigned on, so constraint failures can name the line to
     * edit and so absent keys can be reported as having taken their defaults.
     */
    ConfigProvenance provenance{};
};

} // namespace abm

#endif // ABM_CONFIG_OUTPUT_CONFIG_H
