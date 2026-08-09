// SimulationConfigParsing.cpp

#include "ControlParameters/SimulationConfigParsing.h"

#include <algorithm>
#include <sstream>
#include <stdexcept>

namespace abm::config_parsing {
namespace {

std::string normalizeString(const std::string& value) {
    std::string normalized = stripQuotes(trim(value));
    std::transform(normalized.begin(), normalized.end(), normalized.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return normalized;
}

} // namespace

std::string trim(const std::string& value) {
    const auto begin = std::find_if_not(value.begin(), value.end(),
                                        [](unsigned char c) { return std::isspace(c) != 0; });
    if (begin == value.end()) {
        return {};
    }

    const auto end = std::find_if_not(value.rbegin(), value.rend(), [](unsigned char c) {
                         return std::isspace(c) != 0;
                     }).base();
    return {begin, end};
}

std::string stripQuotes(const std::string& value) {
    if (value.size() >= 2) {
        const char first = value.front();
        const char last = value.back();
        if ((first == '"' && last == '"') || (first == '\'' && last == '\'')) {
            return value.substr(1, value.size() - 2);
        }
    }
    return value;
}

std::string describeLocation(const std::filesystem::path& path, std::size_t lineNumber) {
    std::ostringstream out;
    out << path.string() << ':' << lineNumber;
    return out.str();
}

double parseDouble(const std::string& rawValue, const ConfigValueContext& context) {
    const std::string value = stripQuotes(trim(rawValue));
    try {
        std::size_t parsedCharacters = 0;
        const double parsed = std::stod(value, &parsedCharacters);
        if (parsedCharacters != value.size()) {
            throw std::invalid_argument("extra characters");
        }
        return parsed;
    } catch (const std::exception&) {
        throw std::invalid_argument("Invalid numeric value for key '" + context.key + "' at " +
                                    describeLocation(context.path, context.lineNumber) + ": " +
                                    value);
    }
}

std::size_t parseSize(const std::string& rawValue, const ConfigValueContext& context) {
    const std::string value = stripQuotes(trim(rawValue));
    try {
        std::size_t parsedCharacters = 0;
        const unsigned long long parsed = std::stoull(value, &parsedCharacters);
        if (parsedCharacters != value.size()) {
            throw std::invalid_argument("extra characters");
        }
        return static_cast<std::size_t>(parsed);
    } catch (const std::exception&) {
        throw std::invalid_argument("Invalid integer value for key '" + context.key + "' at " +
                                    describeLocation(context.path, context.lineNumber) + ": " +
                                    value);
    }
}

std::uint64_t parseSeed(const std::string& rawValue, const ConfigValueContext& context) {
    const std::string value = stripQuotes(trim(rawValue));
    try {
        std::size_t parsedCharacters = 0;
        const unsigned long long parsed = std::stoull(value, &parsedCharacters);
        if (parsedCharacters != value.size()) {
            throw std::invalid_argument("extra characters");
        }
        return static_cast<std::uint64_t>(parsed);
    } catch (const std::exception&) {
        throw std::invalid_argument("Invalid integer value for key '" + context.key + "' at " +
                                    describeLocation(context.path, context.lineNumber) + ": " +
                                    value);
    }
}

std::string parseString(const std::string& rawValue) {
    return stripQuotes(trim(rawValue));
}

bool parseBool(const std::string& rawValue, const ConfigValueContext& context) {
    const std::string value = normalizeString(rawValue);
    if (value == "true" || value == "1" || value == "yes" || value == "on") {
        return true;
    }
    if (value == "false" || value == "0" || value == "no" || value == "off") {
        return false;
    }

    throw std::invalid_argument("Invalid boolean value for key '" + context.key + "' at " +
                                describeLocation(context.path, context.lineNumber) + ": " +
                                stripQuotes(trim(rawValue)));
}

ChartistStrategyMode parseChartistStrategyMode(const std::string& rawValue,
                                               const std::filesystem::path& path,
                                               std::size_t lineNumber) {
    const std::string value = normalizeString(rawValue);
    if (value == "random") {
        return ChartistStrategyMode::Random;
    }
    if (value == "momentum") {
        return ChartistStrategyMode::Momentum;
    }
    if (value == "mean_reversion" || value == "mean-reversion" || value == "meanreversion") {
        return ChartistStrategyMode::MeanReversion;
    }
    if (value == "relative_strength_index" || value == "relative-strength-index" ||
        value == "rsi") {
        return ChartistStrategyMode::RelativeStrengthIndex;
    }
    if (value == "breakout" || value == "donchian" || value == "price_channel" ||
        value == "price-channel") {
        return ChartistStrategyMode::Breakout;
    }

    throw std::invalid_argument("Invalid chartist_strategy_mode at " +
                                describeLocation(path, lineNumber) +
                                ". Expected one of: random, momentum, mean_reversion, rsi, "
                                "breakout.");
}

ProspectReferencePointMode parseProspectReferencePointMode(const std::string& rawValue,
                                                           const std::filesystem::path& path,
                                                           std::size_t lineNumber) {
    const std::string value = normalizeString(rawValue);
    if (value == "configured" || value == "fixed" || value == "fixed_reference_point") {
        return ProspectReferencePointMode::Configured;
    }
    if (value == "average_purchase_price" || value == "average-purchase-price" ||
        value == "average_entry_price" || value == "purchase_price") {
        return ProspectReferencePointMode::AveragePurchasePrice;
    }
    if (value == "recent_peak_wealth" || value == "recent-peak-wealth" || value == "peak_wealth") {
        return ProspectReferencePointMode::RecentPeakWealth;
    }
    if (value == "moving_average_price" || value == "moving-average-price" ||
        value == "market_moving_average") {
        return ProspectReferencePointMode::MovingAveragePrice;
    }
    if (value == "initial_wealth" || value == "initial-wealth") {
        return ProspectReferencePointMode::InitialWealth;
    }

    throw std::invalid_argument(
        "Invalid control_reference_point_mode at " + describeLocation(path, lineNumber) +
        ". Expected one of: configured, average_purchase_price, recent_peak_wealth, "
        "moving_average_price, initial_wealth.");
}

std::string prospectReferencePointModeName(ProspectReferencePointMode mode) {
    switch (mode) {
    case ProspectReferencePointMode::Configured:
        return "configured";
    case ProspectReferencePointMode::AveragePurchasePrice:
        return "average_purchase_price";
    case ProspectReferencePointMode::RecentPeakWealth:
        return "recent_peak_wealth";
    case ProspectReferencePointMode::MovingAveragePrice:
        return "moving_average_price";
    case ProspectReferencePointMode::InitialWealth:
        return "initial_wealth";
    }

    return "unknown";
}

FundamentalProcessType parseFundamentalProcessType(const std::string& rawValue,
                                                   const std::filesystem::path& path,
                                                   std::size_t lineNumber) {
    const std::string value = normalizeString(rawValue);
    if (value == "random_walk" || value == "arithmetic_random_walk" || value == "additive" ||
        value == "arithmetic") {
        return FundamentalProcessType::ArithmeticRandomWalk;
    }
    if (value == "gbm" || value == "geometric_brownian_motion" || value == "geometric" ||
        value == "lognormal") {
        return FundamentalProcessType::GeometricBrownianMotion;
    }

    throw std::invalid_argument("Invalid fundamental_process at " +
                                describeLocation(path, lineNumber) +
                                ". Expected random_walk or gbm.");
}

std::string fundamentalProcessTypeName(FundamentalProcessType processType) {
    switch (processType) {
    case FundamentalProcessType::ArithmeticRandomWalk:
        return "random_walk";
    case FundamentalProcessType::GeometricBrownianMotion:
        return "gbm";
    }

    return "unknown";
}

MarketMicrostructureMode parseMarketMicrostructureMode(const std::string& rawValue,
                                                       const std::filesystem::path& path,
                                                       std::size_t lineNumber) {
    const std::string value = normalizeString(rawValue);
    if (value == "continuous_lob" || value == "continuous-limit-order-book" ||
        value == "continuous_limit_order_book" || value == "limit_order_book" || value == "lob") {
        return MarketMicrostructureMode::ContinuousLimitOrderBook;
    }

    throw std::invalid_argument("Invalid market_microstructure at " +
                                describeLocation(path, lineNumber) + ". Expected continuous_lob.");
}

std::string marketMicrostructureModeName(MarketMicrostructureMode mode) {
    switch (mode) {
    case MarketMicrostructureMode::ContinuousLimitOrderBook:
        return "continuous_lob";
    }

    return "unknown";
}

std::string resolvePathValue(const std::filesystem::path& configPath, const std::string& rawValue) {
    const std::filesystem::path candidate = parseString(rawValue);
    if (candidate.is_absolute()) {
        return candidate.lexically_normal().string();
    }
    return (configPath.parent_path() / candidate).lexically_normal().string();
}

} // namespace abm::config_parsing
