// ConfigInspection.h

#ifndef ABM_APPLICATION_CONFIG_INSPECTION_H
#define ABM_APPLICATION_CONFIG_INSPECTION_H

#include "Config/SimulationConfig.h"

#include <cstddef>
#include <iosfwd>
#include <string>
#include <vector>

namespace abm {

/**
 * Prints every setting the configuration file assigned, grouped by section.
 *
 * Values are shown as written in the file rather than as parsed, so the report
 * can be compared directly against the file a reader is editing.
 */
void printResolvedConfiguration(std::ostream& output, const RuntimeConfig& runtimeConfig);

/** Prints the keys that fell back to their built-in defaults, if any. */
void printDefaultedConfigKeys(std::ostream& output, const std::vector<std::string>& defaultedKeys);

/**
 * Prints the configuration key reference as a markdown table.
 *
 * Generated from the compiled-in key registry so the documentation cannot drift
 * from the parser that accepts the keys.
 */
void printConfigKeyReference(std::ostream& output);

} // namespace abm

#endif // ABM_APPLICATION_CONFIG_INSPECTION_H
