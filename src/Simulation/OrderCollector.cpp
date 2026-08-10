// OrderCollector.cpp

#include "Simulation/OrderCollector.h"

#include "AgentStrategy/TradingStrategy.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>
#include <optional>

namespace abm {

void OrderCollector::resetForRun() {
    nextOrderId_ = 1;
}

std::vector<Order> OrderCollector::collectOrders(
    std::size_t timeStep, const std::vector<std::size_t>& activeAgentIndices,
    SimulationPopulation& population, const Market& market, const SimulationConfig& config,
    RandomEngine& random, const SymmetricMatrix& covariance) {
    std::vector<Order> orders;
    orders.reserve(activeAgentIndices.size());

    /*
     * Agents should keep submitting valuation-based limit prices even in a
     * no-social baseline. The social toggle only controls neighbour opinion
     * formation; when it is disabled, opinions are neutral and agents quote
     * from their own fundamental or technical valuation.
     */
    std::vector<double> latestPrices;
    latestPrices.reserve(config.assets.size());
    for (std::size_t assetIndex = 0; assetIndex < config.assets.size(); ++assetIndex) {
        latestPrices.push_back(market.getMarketValues(assetIndex).back());
    }
    const int integerTimeStep = static_cast<int>(timeStep);

    /*
     * The shared market view routes per-asset prices and the step covariance
     * into every strategy. It is built once per step and passed by reference,
     * so no strategy can observe a partially populated view.
     */
    const MarketStepView marketView{latestPrices, covariance, config.assets};

    for (const std::size_t scheduledAgentIndex : activeAgentIndices) {
        if (scheduledAgentIndex >= population.records.size()) {
            continue;
        }

        AgentRecord& record = population.records.at(scheduledAgentIndex);
        if (record.currentStrategy == nullptr) {
            continue;
        }

        Agent& agent = record.agent;
        const bool useValuationLimitPrices = true;
        TradingOrderContext orderContext{useValuationLimitPrices,
                                         agent.getCurrentOpinion(),
                                         config.social.opinionKappa,
                                         config.social.holdTolerance,
                                         config.priceTickSize(),
                                         config.transactionCosts.rate,
                                         config.transactionCosts.affectsDecisions};
        std::vector<Order> generatedOrders = record.currentStrategy->generateOrders(
            agent, market, integerTimeStep, orderContext, marketView);

        for (Order& scheduledOrder : generatedOrders) {
            scheduledOrder.orderId = nextOrderId_++;
            const double latestPrice = scheduledOrder.assetIndex < latestPrices.size()
                                           ? latestPrices[scheduledOrder.assetIndex]
                                           : latestPrices.front();
            const double logGap =
                std::abs(std::log(scheduledOrder.price / std::max(latestPrice, kMinimumPrice)));
            const bool thresholdMarketOrder =
                logGap >= config.microstructure.marketOrderLogGapThreshold;
            const bool randomMarketOrder =
                random.generateUniformDist(0.0, 1.0) < config.microstructure.marketOrderProbability;

            scheduledOrder.style =
                thresholdMarketOrder || randomMarketOrder ? OrderStyle::MARKET : OrderStyle::LIMIT;
            scheduledOrder.remainingQuantity = scheduledOrder.quantity;
            scheduledOrder.timeStep = integerTimeStep;
            scheduledOrder.creationTimeStep = timeStep;
            scheduledOrder.expiryTimeStep =
                scheduledOrder.creationTimeStep + config.microstructure.orderExpirySteps;
            orders.push_back(scheduledOrder);
        }
    }

    return orders;
}

} // namespace abm
