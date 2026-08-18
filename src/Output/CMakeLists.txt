# Sources in this directory belong to the abm_output target.
target_sources(abm_output
    PRIVATE
        AgentSnapshotCsvWriter.cpp
        AssetTimeseriesCsvWriter.cpp
        ExperimentManifestWriter.cpp
        OutputSerialization.cpp
        ProtagonistTimeseriesCsvWriter.cpp
        RunArtifactWriter.cpp
        RunMetadataWriters.cpp
        RunSummaryCsvWriter.cpp
        StepTimeseriesCsvWriter.cpp
        StylisedFactCsvWriter.cpp
        TradeLedgerCsvWriter.cpp
)
