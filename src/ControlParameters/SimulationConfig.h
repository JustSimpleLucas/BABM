// SimulationConfig.h

#ifndef ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_H
#define ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_H

/*
 * Stable configuration facade.
 *
 * Domain-specific configuration records live in smaller headers so modelling
 * assumptions remain easier to navigate as the ABM grows. Existing code may
 * keep including this file; new code can include the narrower domain header
 * that matches its responsibility.
 */
#include "ControlParameters/BehaviouralConfig.h"
#include "ControlParameters/MarketConfig.h"
#include "ControlParameters/ModelConfig.h"
#include "ControlParameters/OutputConfig.h"
#include "ControlParameters/StrategyConfig.h"

#endif // ABM_CONTROL_PARAMETERS_SIMULATION_CONFIG_H
