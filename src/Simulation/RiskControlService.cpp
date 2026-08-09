// RiskControlService.cpp

#include "Simulation/RiskControlService.h"

#include "RiskManagement/ShortSaleRiskControls.h"
#include "Utility/SimulationConstants.h"
#include "Utility/TransactionCosts.h"

#include <algorithm>
#include <utility>

namespace abm {
namespace {

const std::string& assetNameForIndex(const SimulationConfig& config, std::size_t assetIndex) {
    return config.assets.at(assetIndex).name;
}

} // namespace

void RiskControlService::reset(const SimulationPopulation& population,
                               const SimulationConfig& config) {
    /*
     * Formula note:
     * X_0,j = N_agents * initial_stock_j.
     *
     * These cached per-asset supplies are the base used by the borrowable
     * supply constraint when short selling is enabled.
     */
    const double populationSize = static_cast<double>(population.records.size());
    cachedInitialShareSupplyByAsset_.clear();
    cachedInitialShareSupplyByAsset_.reserve(config.assets.size());
    for (const AssetDefinition& asset : config.assets) {
        cachedInitialShareSupplyByAsset_.push_back(populationSize *
                                                   std::max(0.0, asset.initialStock));
    }

    const std::size_t assetCount = cachedInitialShareSupplyByAsset_.size();
    cachedAggregateShortInterestByAsset_.assign(assetCount, 0.0);
    auto populationAgentIt = population.agentsById.cbegin();
    if (populationAgentIt != population.agentsById.cend()) {
        ++populationAgentIt;
    }
    for (; populationAgentIt != population.agentsById.cend(); ++populationAgentIt) {
        const Agent* agent = *populationAgentIt;
        if (agent == nullptr) {
            continue;
        }
        for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
            const double agentStock =
                assetIndex < agent->assetCount() ? agent->getStock(assetIndex) : 0.0;
            cachedAggregateShortInterestByAsset_[assetIndex] += shortPositionShares(agentStock);
        }
    }
}

double RiskControlService::initialShareSupply() const {
    return initialShareSupply(0);
}

double RiskControlService::initialShareSupply(std::size_t assetIndex) const {
    return cachedInitialShareSupplyByAsset_.at(assetIndex);
}

double RiskControlService::aggregateShortInterest() const {
    return aggregateShortInterest(0);
}

double RiskControlService::aggregateShortInterest(std::size_t assetIndex) const {
    return cachedAggregateShortInterestByAsset_.at(assetIndex);
}

void RiskControlService::updateAgentStockWithShortInterest(Agent& agent, double newStock) {
    updateAgentStockWithShortInterest(agent, 0, newStock);
}

void RiskControlService::updateAgentStockWithShortInterest(Agent& agent, std::size_t assetIndex,
                                                           double newStock) {
    const double previousShortPosition = shortPositionShares(agent.getStock(assetIndex));
    const double nextShortPosition = shortPositionShares(newStock);
    /*
     * Formula note:
     * SI'_j = max(0, SI_j - s_old^- + s_new^-).
     *
     * Updating the aggregate cache at the same time as the agent position keeps
     * later short-sale feasibility checks consistent with executed trades.
     */
    double& aggregateShortInterestForAsset = cachedAggregateShortInterestByAsset_.at(assetIndex);
    aggregateShortInterestForAsset =
        std::max(0.0, aggregateShortInterestForAsset - previousShortPosition + nextShortPosition);
    agent.updateStock(assetIndex, newStock);
}

ForcedBuyInResult RiskControlService::enforceMaintenanceMargin(
    double marketPrice, std::size_t timeStep, const SimulationConfig& config,
    const std::vector<Agent*>& agentsById,
    std::vector<ExternalTradeLedgerRecord>& externalTradeLedger, std::size_t& nextTradeId,
    bool recordTradeLedger) {
    return enforceMaintenanceMargin(std::vector<double>{marketPrice}, timeStep, config, agentsById,
                                    externalTradeLedger, nextTradeId, recordTradeLedger);
}

ForcedBuyInResult RiskControlService::enforceMaintenanceMargin(
    const std::vector<double>& marketPrices, std::size_t timeStep, const SimulationConfig& config,
    const std::vector<Agent*>& agentsById,
    std::vector<ExternalTradeLedgerRecord>& externalTradeLedger, std::size_t& nextTradeId,
    bool recordTradeLedger) {
    ForcedBuyInResult result{};
    result.volumeByAsset.assign(marketPrices.size(), 0.0);
    result.transactionCostsByAsset.assign(marketPrices.size(), 0.0);
    if (!config.shortSellingEnabled) {
        return result;
    }

    /*
     * Maintenance margin is enforced by a broker-style forced buy-in. The
     * covering trade is executed against an external liquidity account rather
     * than an endogenous behavioural counterparty, so the risk constraint is
     * always binding even when the auction book is temporarily one-sided.
     * Assets are covered sequentially in index order against shared cash.
     */
    const double transactionCostRate =
        config.transactionCosts.applyToForcedBuyIns ? config.transactionCosts.rate : 0.0;
    auto agentIt = agentsById.begin();
    if (agentIt != agentsById.end()) {
        ++agentIt;
    }
    for (; agentIt != agentsById.end(); ++agentIt) {
        Agent* agent = *agentIt;
        if (agent == nullptr) {
            continue;
        }

        for (std::size_t assetIndex = 0; assetIndex < marketPrices.size(); ++assetIndex) {
            const double marketPrice = marketPrices[assetIndex];
            const double agentStock =
                assetIndex < agent->assetCount() ? agent->getStock(assetIndex) : 0.0;
            const double requiredCoverQuantity = requiredBuyToCoverQuantity(
                ShortSaleMarginCallRequest{agent->getCash(), agentStock, marketPrice,
                                           config.shortSale.initialMarginRequirement,
                                           config.shortSale.maintenanceMarginRequirement});
            if (requiredCoverQuantity <= kMinimumOrderQuantity) {
                continue;
            }

            const double affordableCoverQuantity = transaction_costs::affordableBuyQuantity(
                agent->getCash(), marketPrice, transactionCostRate);
            const double coverQuantity =
                std::min({requiredCoverQuantity, shortPositionShares(agentStock),
                          std::max(0.0, affordableCoverQuantity)});
            if (coverQuantity <= kMinimumOrderQuantity) {
                continue;
            }

            const double tradeNotional =
                transaction_costs::grossNotional(marketPrice, coverQuantity);
            const double transactionCost =
                transaction_costs::oneSideCost(marketPrice, coverQuantity, transactionCostRate);
            const double cashOutflow = tradeNotional + transactionCost;
            /*
             * Formula note:
             * forced_buy_notional = q_cover * P_t,
             * forced_buy_fee = tau * forced_buy_notional.
             *
             * The buy-in reduces the short position and cash balance at the
             * current market price because it is treated as broker-enforced
             * external liquidity rather than a strategic order.
             */
            agent->recordExecutedTrade(assetIndex,
                                       ExecutedTrade{OrderType::BUY, marketPrice, coverQuantity});
            agent->recordTransactionCost(transactionCost);
            agent->updateCash(std::max(0.0, agent->getCash() - cashOutflow));
            updateAgentStockWithShortInterest(*agent, assetIndex,
                                              agent->getStock(assetIndex) + coverQuantity);
            result.volume += coverQuantity;
            result.transactionCosts += transactionCost;
            result.volumeByAsset[assetIndex] += coverQuantity;
            result.transactionCostsByAsset[assetIndex] += transactionCost;

            if (recordTradeLedger) {
                /*
                 * Forced buy-ins are broker-enforced external liquidity, so the
                 * ledger row has no counterparty agent and no originating
                 * orders; those fields keep their zero defaults.
                 */
                ExternalTradeLedgerRecord buyInRow{};
                buyInRow.tradeId = nextTradeId++;
                buyInRow.timeStep = timeStep;
                buyInRow.agentId = static_cast<std::uint32_t>(agent->getNumericalId());
                buyInRow.side = OrderType::BUY;
                buyInRow.price = marketPrice;
                buyInRow.quantity = coverQuantity;
                buyInRow.grossNotional = tradeNotional;
                buyInRow.transactionCost = transactionCost;
                buyInRow.netCashFlow = -cashOutflow;
                buyInRow.asset = assetNameForIndex(config, assetIndex);
                externalTradeLedger.push_back(std::move(buyInRow));
            }
        }
    }

    return result;
}

} // namespace abm
