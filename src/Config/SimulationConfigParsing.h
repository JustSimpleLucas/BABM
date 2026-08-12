// SimulationConfigParsing.h

#ifndef ABM_CONFIG_SIMULATION_CONFIG_PARSING_H
#define ABM_CONFIG_SIMULATION_CONFIG_PARSING_H

#include <cstddef>
#include <filesystem>
#include <string>

#include "Config/SimulationConfig.h"

namespace abm::config_parsing {

/**
 * Identifies the configuration value currently being parsed.
 *
 * Keeping the key and source location together makes parser calls less error
 * prone than passing several adjacent string-like arguments.
 */
struct ConfigValueContext {
    std::string key;
    std::filesystem::path path;
    std::size_t lineNumber;
};

[[nodiscard]] std::string trim(const std::string& value);

[[nodiscard]] std::string stripQuotes(const std::string& value);

[[nodiscard]] std::string describeLocation(const std::filesystem::path& path,
                                           std::size_t lineNumber);

[[nodiscard]] double parseDouble(const std::string& rawValue, const ConfigValueContext& context);

[[nodiscard]] std::size_t parseSize(const std::string& rawValue, const ConfigValueContext& context);

[[nodiscard]] std::uint64_t parseSeed(const std::string& rawValue,
                                      const ConfigValueContext& context);

[[nodiscard]] std::string parseString(const std::string& rawValue);

[[nodiscard]] bool parseBool(const std::string& rawValue, const ConfigValueContext& context);

[[nodiscard]] ChartistStrategyMode parseChartistStrategyMode(const std::string& rawValue,
                                                             const std::filesystem::path& path,
                                                             std::size_t lineNumber);

[[nodiscard]] ProspectReferencePointMode
parseProspectReferencePointMode(const std::string& rawValue, const std::filesystem::path& path,
                                std::size_t lineNumber);

[[nodiscard]] std::string prospectReferencePointModeName(ProspectReferencePointMode mode);

[[nodiscard]] MarketMicrostructureMode
parseMarketMicrostructureMode(const std::string& rawValue, const std::filesystem::path& path,
                              std::size_t lineNumber);

[[nodiscard]] std::string marketMicrostructureModeName(MarketMicrostructureMode mode);

/** Parses an asset's fundamental-process selector; accepts random_walk or gbm. */
[[nodiscard]] FundamentalProcessType parseFundamentalProcessType(const std::string& rawValue,
                                                                 const std::filesystem::path& path,
                                                                 std::size_t lineNumber);

/** Returns the canonical config token for a fundamental-process selector. */
[[nodiscard]] std::string fundamentalProcessTypeName(FundamentalProcessType processType);

[[nodiscard]] std::string resolvePathValue(const std::filesystem::path& configPath,
                                           const std::string& rawValue);

} // namespace abm::config_parsing

#endif // ABM_CONFIG_SIMULATION_CONFIG_PARSING_H
