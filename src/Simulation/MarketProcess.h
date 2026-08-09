// MarketProcess.h

#ifndef SIMULATION_MARKET_PROCESS_H
#define SIMULATION_MARKET_PROCESS_H

#include <vector>

#include "ControlParameters/SimulationConfig.h"
#include "Market/Market.h"
#include "Simulation/SimulationState.h"

namespace abm {

class RandomEngine;

/** Final price state produced by initial market warm-up. */
struct MarketInitializationResult {
    double finalMarketPrice{0.0};
    double finalFundamentalPrice{0.0};
};

/**
 * Owns market-history evolution that is not itself order matching.
 *
 * This class isolates assumptions about fundamental-value dynamics, warm-up
 * prices, risk-free cash accrual, and the last-trade realised price rule.
 */
class MarketProcess {
  public:
    /** Seeds the market and warm-up histories before agent interaction begins. */
    [[nodiscard]] static MarketInitializationResult initializeMarket(Market& market,
                                                                     const SimulationConfig& config,
                                                                     RandomEngine& random);

    /** Applies one period of risk-free cash accrual to every agent. */
    static void accrueRiskFreeCash(SimulationPopulation& population, double riskFreeRate);

    /** Advances and stores every asset's latent fundamental value by one period. */
    [[nodiscard]] static std::vector<double> generateNextFundamentals(Market& market,
                                                                      const SimulationConfig& config);

    /** Converts clearing output into the realised next market price and returns. */
    [[nodiscard]] static PriceFormationResult resolvePriceAfterClearing(
        double referencePrice,
        const MicrostructureStepResult& result);

    /** Initialises each agent's first mark-to-market wealth from per-asset prices. */
    static void initializeAgentWealths(SimulationPopulation& population,
                                       const std::vector<double>& marketPrices);

    /** Refreshes each agent's current mark-to-market wealth from per-asset prices. */
    static void refreshAgentWealths(SimulationPopulation& population,
                                    const std::vector<double>& marketPrices);
};

} // namespace abm

#endif // SIMULATION_MARKET_PROCESS_H
