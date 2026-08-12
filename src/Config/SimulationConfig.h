// SimulationConfig.h

#ifndef ABM_CONFIG_SIMULATION_CONFIG_H
#define ABM_CONFIG_SIMULATION_CONFIG_H

/*
 * Stable configuration facade.
 *
 * Domain-specific configuration records live in smaller headers so modelling
 * assumptions remain easier to navigate as the ABM grows. Existing code may
 * keep including this file; new code can include the narrower domain header
 * that matches its responsibility.
 */
#include "Config/BehaviouralConfig.h"
#include "Config/MarketConfig.h"
#include "Config/ModelConfig.h"
#include "Config/OutputConfig.h"
#include "Config/StrategyConfig.h"

#endif // ABM_CONFIG_SIMULATION_CONFIG_H
