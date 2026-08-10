// OutputSerialization.h

#ifndef ABM_OUTPUT_OUTPUT_SERIALIZATION_H
#define ABM_OUTPUT_OUTPUT_SERIALIZATION_H

#include <string>

#include "ControlParameters/SimulationConfig.h"
#include "OrderBook/Order.h"

namespace abm::output_detail {

[[nodiscard]] int boolToFlag(bool value);

[[nodiscard]] const char* orderSideLabel(OrderType side);

[[nodiscard]] std::string csvEscape(const std::string& value);

[[nodiscard]] std::string formatFixedDouble(double value, int precision = 10);

[[nodiscard]] std::string jsonEscape(const std::string& value);

[[nodiscard]] std::string chartistStrategyModeLabel(ChartistStrategyMode mode);

[[nodiscard]] std::string jsonBool(bool value);

[[nodiscard]] std::string buildNormalizedConfigJson(const SimulationConfig& config);

[[nodiscard]] std::string stableConfigHash(const std::string& normalizedConfigJson);

[[nodiscard]] bool ensureParentDirectoryExists(const std::string& outputPath, std::string& error);

} // namespace abm::output_detail

#endif // ABM_OUTPUT_OUTPUT_SERIALIZATION_H
