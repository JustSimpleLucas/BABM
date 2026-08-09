// StylisedFactCsvWriter.cpp

#include "Output/StylisedFactCsvWriter.h"

#include "Output/CsvSchema.h"
#include "Output/OutputSerialization.h"

#include <algorithm>
#include <fstream>
#include <iomanip>

namespace abm::output_detail {
namespace {

/** One screening diagnostic for one asset. */
struct Row {
    const std::string& assetName;
    const char* stylisedFact;
    const char* diagnostic;
    double metricValue;
    const char* screeningRule;
    const std::string& conclusion;
};

constexpr CsvColumn<Row> kColumns[] = {
    {"asset", [](std::ostream& out, const Row& r) { out << csvEscape(r.assetName); }},
    {"stylised_fact", [](std::ostream& out, const Row& r) { out << r.stylisedFact; }},
    {"diagnostic", [](std::ostream& out, const Row& r) { out << r.diagnostic; }},
    {"metric_value", [](std::ostream& out, const Row& r) { out << r.metricValue; }},
    {"screening_rule", [](std::ostream& out, const Row& r) { out << csvEscape(r.screeningRule); }},
    {"conclusion", [](std::ostream& out, const Row& r) { out << csvEscape(r.conclusion); }},
};

} // namespace

bool exportStylisedFactsCsv(const std::string& outputPath,
                            const std::vector<AssetRunMetrics>& assetMetrics, std::string& error) {
    if (!ensureParentDirectoryExists(outputPath, error)) {
        return false;
    }

    std::ofstream out(outputPath);
    if (!out.is_open()) {
        error = "Unable to open stylised-facts file: " + outputPath;
        return false;
    }

    /*
     * These rows are lightweight screening diagnostics. The Python analysis
     * workflow remains the stronger inferential layer because it runs
     * Ljung-Box, Jarque-Bera, ARCH LM, and optional GARCH tests before
     * thesis-level interpretation.
     */
    writeCsvHeader(out, kColumns);
    out << std::fixed << std::setprecision(10);

    for (const AssetRunMetrics& assetMetric : assetMetrics) {
        const RunMetrics& metrics = assetMetric.metrics;

        writeCsvRow(out, kColumns,
                    Row{assetMetric.assetName, "Absence of autocorrelation",
                        "Lag-1 raw log-return autocorrelation", metrics.lag1ReturnAutocorrelation,
                        "Absolute value below 0.10 is treated as weak linear dependence",
                        metrics.autocorrelationConclusion});

        writeCsvRow(out, kColumns,
                    Row{assetMetric.assetName, "Fat tails",
                        "Excess kurtosis of simulated log returns", metrics.excessKurtosis,
                        "Positive excess kurtosis is the screening signal",
                        metrics.fatTailsConclusion});

        writeCsvRow(out, kColumns,
                    Row{assetMetric.assetName, "Volatility clustering",
                        "Lag-1 absolute and squared-return autocorrelation",
                        std::max(metrics.lag1AbsoluteReturnAutocorrelation,
                                 metrics.lag1SquaredReturnAutocorrelation),
                        "Lag-1 absolute or squared-return autocorrelation above 0.05 is the "
                        "screening signal",
                        metrics.volatilityClusteringConclusion});
    }

    out.flush();
    if (!out.good()) {
        error = "Failed while writing stylised-facts file: " + outputPath;
        return false;
    }
    return true;
}

} // namespace abm::output_detail
