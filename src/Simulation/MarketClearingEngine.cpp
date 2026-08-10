// MarketClearingEngine.cpp

#include "Simulation/MarketClearingEngine.h"

#include "Metrics/AllocativeEfficiency.h"
#include "RiskManagement/ShortSaleRiskControls.h"
#include "Utility/SimulationConstants.h"
#include "Utility/TransactionCosts.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <utility>
#include <vector>

namespace abm {
namespace {

double orderQuantityForAccounting(const Order& order) {
    return order.remainingQuantity > kMinimumOrderQuantity ? order.remainingQuantity
                                                           : order.quantity;
}

Agent* findAgentById(const std::vector<Agent*>& agentsById, int ownerAgentId) {
    if (ownerAgentId <= 0) {
        return nullptr;
    }

    const auto agentIndex = static_cast<std::size_t>(ownerAgentId);
    if (agentIndex >= agentsById.size()) {
        return nullptr;
    }
    return agentsById.at(agentIndex);
}

struct FillQuantities {
    double requested{0.0};
    double affordableBuy{0.0};
    double feasibleSell{0.0};
    double fill{0.0};
};

struct TradeExecution {
    double price{0.0};
    double quantity{0.0};
};

struct OrderMatch {
    const Order* incoming{nullptr};
    const Order* resting{nullptr};
    const Order* buy{nullptr};
    const Order* sell{nullptr};
};

struct MatchedAgents {
    Agent* buyer{nullptr};
    Agent* seller{nullptr};
};

class OrderExecutionSession {
  public:
    OrderExecutionSession(std::vector<LimitOrderBook>* orderBooks,
                          const OrderExecutionRequest& request)
        : orderBooks_(orderBooks), request_(&request) {}

    [[nodiscard]] std::vector<MicrostructureStepResult> execute() {
        const std::size_t assetCount = orderBooks_->size();
        results_.assign(assetCount, MicrostructureStepResult{});
        allocativeTradesByAsset_.assign(assetCount, {});

        for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
            MicrostructureStepResult& result = results_[assetIndex];
            if (assetIndex < request_->lifecycleCounts.size()) {
                const RestingOrderLifecycleCounts& lifecycle =
                    request_->lifecycleCounts[assetIndex];
                result.expiredOrders = lifecycle.expiredOrders;
                result.cancelledOrders = lifecycle.cancelledOrders;
                result.staleCancelledOrders = lifecycle.cancelledOrders;
            }
            result.lastTradePrice = referencePriceForAsset(assetIndex);
        }

        const std::vector<std::vector<AllocativeEfficiencyOrder>> benchmarkOrdersByAsset =
            buildAllocativeEfficiencyBenchmarkOrders(assetCount);
        for (const Order& submittedOrder : *request_->orders) {
            processSubmittedOrder(submittedOrder);
        }

        for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
            const AllocativeEfficiencyResult efficiency = calculateAllocativeEfficiency(
                benchmarkOrdersByAsset[assetIndex], allocativeTradesByAsset_[assetIndex]);
            MicrostructureStepResult& result = results_[assetIndex];
            result.realizedAllocativeSurplus = efficiency.realizedSurplus;
            result.maximumAllocativeSurplus = efficiency.maximumSurplus;
            result.allocativeEfficiency = efficiency.efficiency;
            result.bookMetrics = (*orderBooks_)[assetIndex].metrics(
                request_->config->microstructure.bookDepthLevels);
        }
        return std::move(results_);
    }

  private:
    [[nodiscard]] LimitOrderBook& bookFor(const Order& order) {
        return orderBooks_->at(order.assetIndex);
    }

    [[nodiscard]] MicrostructureStepResult& resultFor(const Order& order) {
        return results_.at(order.assetIndex);
    }

    [[nodiscard]] double referencePriceForAsset(std::size_t assetIndex) const {
        if (request_->referencePrices == nullptr ||
            assetIndex >= request_->referencePrices->size()) {
            return 0.0;
        }
        return (*request_->referencePrices)[assetIndex];
    }

    [[nodiscard]] const std::string& assetNameForIndex(std::size_t assetIndex) const {
        return request_->config->assets.at(assetIndex).name;
    }

    [[nodiscard]] std::vector<std::vector<AllocativeEfficiencyOrder>>
    buildAllocativeEfficiencyBenchmarkOrders(std::size_t assetCount) const {
        std::vector<std::vector<AllocativeEfficiencyOrder>> benchmarkOrdersByAsset(assetCount);
        for (std::size_t assetIndex = 0; assetIndex < assetCount; ++assetIndex) {
            const LimitOrderBookSnapshot restingOrders =
                (*orderBooks_)[assetIndex].restingOrdersSnapshot();
            std::vector<AllocativeEfficiencyOrder>& benchmarkOrders =
                benchmarkOrdersByAsset[assetIndex];
            benchmarkOrders.reserve(restingOrders.bids.size() + restingOrders.asks.size());
            for (const Order& order : restingOrders.bids) {
                appendBenchmarkOrder(benchmarkOrders, order);
            }
            for (const Order& order : restingOrders.asks) {
                appendBenchmarkOrder(benchmarkOrders, order);
            }
        }
        for (const Order& order : *request_->orders) {
            appendBenchmarkOrder(benchmarkOrdersByAsset.at(order.assetIndex), order);
        }
        return benchmarkOrdersByAsset;
    }

    static void appendBenchmarkOrder(std::vector<AllocativeEfficiencyOrder>& benchmarkOrders,
                                     const Order& order) {
        benchmarkOrders.push_back(
            AllocativeEfficiencyOrder{order.type, order.price, orderQuantityForAccounting(order)});
    }

    void processSubmittedOrder(const Order& submittedOrder) {
        Order incoming = submittedOrder;
        incoming.remainingQuantity = orderQuantityForAccounting(incoming);

        recordSubmittedOrder(incoming);
        matchIncomingOrder(incoming);
        submitResidualLimitOrder(incoming);
    }

    void recordSubmittedOrder(const Order& incoming) {
        MicrostructureStepResult& result = resultFor(incoming);
        if (incoming.style == OrderStyle::MARKET) {
            ++result.submittedMarketOrders;
        } else {
            ++result.submittedLimitOrders;
        }

        const double submittedQuantity = std::max(0.0, incoming.quantity);
        result.netDemand +=
            incoming.type == OrderType::BUY ? submittedQuantity : -submittedQuantity;
    }

    void matchIncomingOrder(Order& incoming) {
        LimitOrderBook& orderBook = bookFor(incoming);
        MicrostructureStepResult& result = resultFor(incoming);
        std::size_t matchIterations = 0;
        while (incoming.remainingQuantity > kMinimumOrderQuantity && orderBook.canMatch(incoming)) {
            if (++matchIterations > kMaximumMatchIterationsPerOrder) {
                std::fprintf(stderr,
                             "Warning: cancelled order %d (agent %d, step %d) after %zu matching "
                             "iterations; binding constraints permitted only negligible fills.\n",
                             incoming.orderId, incoming.ownerAgentId, incoming.timeStep,
                             kMaximumMatchIterationsPerOrder);
                incoming.remainingQuantity = 0.0;
                ++result.cancelledOrders;
                ++result.infeasibleIncomingCancellations;
                break;
            }
            const Order& resting = orderBook.bestOpposingOrder(incoming);
            if (resting.ownerAgentId == incoming.ownerAgentId) {
                /*
                 * Self-trade prevention with cancel-resting semantics: the
                 * agent's own stale quote is removed so the incoming order can
                 * continue matching against true counterparties.
                 */
                orderBook.removeBestOpposingOrder(incoming);
                ++result.selfTradePreventions;
                continue;
            }
            const double executionPrice = std::max(kMinimumPrice, resting.price);
            if (marketOrderBreachesCollar(incoming, executionPrice)) {
                incoming.remainingQuantity = 0.0;
                ++result.collarRejectedOrders;
                break;
            }
            const Order& buyOrder = incoming.type == OrderType::BUY ? incoming : resting;
            const Order& sellOrder = incoming.type == OrderType::SELL ? incoming : resting;
            const OrderMatch matchedOrders{&incoming, &resting, &buyOrder, &sellOrder};
            const MatchedAgents matchedAgents{
                findAgentById(*request_->agentsById, buyOrder.ownerAgentId),
                findAgentById(*request_->agentsById, sellOrder.ownerAgentId)};

            if (cancelMissingCounterparty(incoming, matchedAgents)) {
                continue;
            }

            const FillQuantities quantities =
                calculateFillQuantities(matchedOrders, matchedAgents, executionPrice);
            if (quantities.fill <= minimumEconomicFill(quantities.requested)) {
                if (cancelInfeasibleFill(incoming, quantities)) {
                    continue;
                }
                break;
            }

            applyTrade(matchedAgents, matchedOrders,
                       TradeExecution{executionPrice, quantities.fill});
            incoming.remainingQuantity =
                std::max(0.0, incoming.remainingQuantity - quantities.fill);
            orderBook.reduceBestOpposingOrder(incoming, quantities.fill);
        }
    }

    /*
     * Formula note:
     * q_fill_min = max(q_min_abs, phi_fill * q_requested).
     *
     * The relative component keeps the matching loop from executing fills that
     * are technically permitted by a binding constraint yet economically
     * negligible next to the quantities being matched.
     */
    [[nodiscard]] static double minimumEconomicFill(double requestedQuantity) {
        return std::max(kMinimumOrderQuantity, kMinimumFillFraction * requestedQuantity);
    }

    bool cancelMissingCounterparty(Order& incoming, const MatchedAgents& matchedAgents) {
        if (matchedAgents.buyer == nullptr) {
            cancelInfeasibleSide(incoming, OrderType::BUY);
            return true;
        }
        if (matchedAgents.seller == nullptr) {
            cancelInfeasibleSide(incoming, OrderType::SELL);
            return true;
        }
        return false;
    }

    void cancelInfeasibleSide(Order& incoming, OrderType infeasibleSide) {
        MicrostructureStepResult& result = resultFor(incoming);
        if (incoming.type == infeasibleSide) {
            incoming.remainingQuantity = 0.0;
            ++result.infeasibleIncomingCancellations;
            return;
        }

        bookFor(incoming).removeBestOpposingOrder(incoming);
        ++result.cancelledOrders;
        ++result.infeasibleRestingCancellations;
    }

    [[nodiscard]] bool marketOrderBreachesCollar(const Order& incoming,
                                                 double executionPrice) const {
        const double collar = request_->config->microstructure.marketOrderPriceCollar;
        if (incoming.style != OrderStyle::MARKET || collar <= 0.0) {
            return false;
        }
        const double referencePrice =
            std::max(referencePriceForAsset(incoming.assetIndex), kMinimumPrice);
        return std::abs(std::log(executionPrice / referencePrice)) > collar;
    }

    [[nodiscard]] FillQuantities calculateFillQuantities(const OrderMatch& matchedOrders,
                                                         const MatchedAgents& matchedAgents,
                                                         double executionPrice) const {
        FillQuantities quantities{};
        quantities.requested = std::min(matchedOrders.incoming->remainingQuantity,
                                        matchedOrders.resting->remainingQuantity);
        quantities.affordableBuy =
            transaction_costs::affordableBuyQuantity(matchedAgents.buyer->getCash(), executionPrice,
                                                     request_->config->transactionCosts.rate);
        quantities.feasibleSell =
            feasibleSellQuantity(quantities.requested, *matchedAgents.seller, executionPrice,
                                 matchedOrders.incoming->assetIndex);
        /*
         * Formula note:
         * q_exec = min(q_requested,
         *              cash_buyer / (P_exec * (1 + tau)),
         *              q_sell_feasible).
         *
         * The final fill quantity therefore respects both buyer cash and
         * seller inventory or short-sale constraints at execution time.
         */
        quantities.fill = std::min({quantities.requested, std::max(0.0, quantities.affordableBuy),
                                    std::max(0.0, quantities.feasibleSell)});
        return quantities;
    }

    [[nodiscard]] double feasibleSellQuantity(double requestedQuantity, const Agent& seller,
                                              double executionPrice, std::size_t assetIndex) const {
        if (!request_->config->shortSellingEnabled) {
            return std::min(requestedQuantity, std::max(0.0, seller.getStock(assetIndex)));
        }

        return constrainSellQuantityByShortSaleRules(ShortSaleSellConstraintRequest{
            requestedQuantity, seller.getStock(assetIndex), seller.getCash(), executionPrice,
            request_->riskControls->aggregateShortInterest(assetIndex), 0.0,
            request_->riskControls->initialShareSupply(assetIndex),
            request_->config->shortSale.initialMarginRequirement,
            request_->config->shortSale.borrowableSupplyRatio});
    }

    bool cancelInfeasibleFill(Order& incoming, const FillQuantities& quantities) {
        /*
         * A resting order can become infeasible after other trades change its
         * owner's cash, inventory, or short-sale margin. Removing it preserves
         * book integrity without mutating agent strategy state retroactively.
         */
        const double minimumFill = minimumEconomicFill(quantities.requested);
        if (quantities.affordableBuy <= minimumFill) {
            cancelInfeasibleSide(incoming, OrderType::BUY);
            return true;
        }
        if (quantities.feasibleSell <= minimumFill) {
            cancelInfeasibleSide(incoming, OrderType::SELL);
            return true;
        }
        return false;
    }

    void applyTrade(const MatchedAgents& matchedAgents, const OrderMatch& matchedOrders,
                    const TradeExecution& trade) {
        Agent& buyer = *matchedAgents.buyer;
        Agent& seller = *matchedAgents.seller;
        const std::size_t assetIndex = matchedOrders.incoming->assetIndex;
        const double tradeNotional = transaction_costs::grossNotional(trade.price, trade.quantity);
        const double transactionCost = transaction_costs::oneSideCost(
            trade.price, trade.quantity, request_->config->transactionCosts.rate);
        const double buyerCashOutflow = tradeNotional + transactionCost;
        const double sellerCashInflow = tradeNotional - transactionCost;
        /*
         * Formula note:
         * notional = q_exec * P_exec, fee = tau * notional,
         * buyer:  c' = c - notional - fee, x' = x + q_exec,
         * seller: c' = c + notional - fee, x' = x - q_exec.
         */
        buyer.recordExecutedTrade(assetIndex,
                                  ExecutedTrade{OrderType::BUY, trade.price, trade.quantity});
        seller.recordExecutedTrade(assetIndex,
                                   ExecutedTrade{OrderType::SELL, trade.price, trade.quantity});
        buyer.recordTransactionCost(transactionCost);
        seller.recordTransactionCost(transactionCost);
        buyer.updateCash(std::max(0.0, buyer.getCash() - buyerCashOutflow));
        request_->riskControls->updateAgentStockWithShortInterest(
            buyer, assetIndex, buyer.getStock(assetIndex) + trade.quantity);
        request_->riskControls->updateAgentStockWithShortInterest(
            seller, assetIndex, seller.getStock(assetIndex) - trade.quantity);
        seller.updateCash(seller.getCash() + sellerCashInflow);

        MicrostructureStepResult& result = resultFor(*matchedOrders.incoming);
        result.tradedVolume += trade.quantity;
        result.totalTransactionCosts += transactionCost * 2.0;
        result.lastTradePrice = trade.price;
        ++result.executedTrades;
        allocativeTradesByAsset_.at(assetIndex)
            .push_back(AllocativeEfficiencyTrade{matchedOrders.buy->price,
                                                 matchedOrders.sell->price, trade.quantity});

        if (request_->recordTradeLedger) {
            recordTradeLedgerRows(matchedOrders, trade, tradeNotional, transactionCost);
        }
    }

    void recordTradeLedgerRows(const OrderMatch& matchedOrders, const TradeExecution& trade,
                               double tradeNotional, double transactionCost) const {
        /*
         * Every execution is stored double-entry style: one row per side of the
         * trade, sharing the trade identifiers and economics, with the agent,
         * counterparty, order references, and net cash flow mirrored. The
         * buy-side row is populated field by field and the sell-side row is
         * derived from it, so the shared fields cannot drift apart.
         */
        ExternalTradeLedgerRecord buyRow{};
        buyRow.tradeId = (*request_->nextTradeId)++;
        buyRow.timeStep = static_cast<std::size_t>(
            std::max(matchedOrders.buy->timeStep, matchedOrders.sell->timeStep));
        buyRow.agentId = static_cast<std::uint32_t>(matchedOrders.buy->ownerAgentId);
        buyRow.counterpartyAgentId = static_cast<std::uint32_t>(matchedOrders.sell->ownerAgentId);
        buyRow.side = OrderType::BUY;
        buyRow.price = trade.price;
        buyRow.quantity = trade.quantity;
        buyRow.grossNotional = tradeNotional;
        buyRow.transactionCost = transactionCost;
        buyRow.netCashFlow = -(tradeNotional + transactionCost);
        buyRow.asset = assetNameForIndex(matchedOrders.incoming->assetIndex);
        buyRow.orderId = matchedOrders.buy->orderId;
        buyRow.counterpartyOrderId = matchedOrders.sell->orderId;

        ExternalTradeLedgerRecord sellRow = buyRow;
        sellRow.agentId = buyRow.counterpartyAgentId;
        sellRow.counterpartyAgentId = buyRow.agentId;
        sellRow.side = OrderType::SELL;
        sellRow.netCashFlow = tradeNotional - transactionCost;
        sellRow.orderId = buyRow.counterpartyOrderId;
        sellRow.counterpartyOrderId = buyRow.orderId;

        request_->externalTradeLedger->push_back(std::move(buyRow));
        request_->externalTradeLedger->push_back(std::move(sellRow));
    }

    void submitResidualLimitOrder(Order& incoming) {
        if (incoming.style != OrderStyle::LIMIT ||
            incoming.remainingQuantity <= kMinimumOrderQuantity) {
            return;
        }

        Agent* owner = findAgentById(*request_->agentsById, incoming.ownerAgentId);
        if (owner == nullptr) {
            return;
        }

        const double restQuantity = constrainedRestingQuantity(incoming, *owner);
        if (restQuantity > kMinimumOrderQuantity) {
            incoming.remainingQuantity = restQuantity;
            bookFor(incoming).submitRestingOrder(incoming);
        }
    }

    [[nodiscard]] double constrainedRestingQuantity(const Order& incoming,
                                                    const Agent& owner) const {
        const std::size_t assetIndex = incoming.assetIndex;
        if (incoming.type == OrderType::BUY) {
            return std::min(
                incoming.remainingQuantity,
                transaction_costs::affordableBuyQuantity(owner.getCash(), incoming.price,
                                                         request_->config->transactionCosts.rate));
        }
        if (!request_->config->shortSellingEnabled) {
            return std::min(incoming.remainingQuantity, std::max(0.0, owner.getStock(assetIndex)));
        }

        return constrainSellQuantityByShortSaleRules(ShortSaleSellConstraintRequest{
            incoming.remainingQuantity, owner.getStock(assetIndex), owner.getCash(),
            std::max(incoming.price, kMinimumPrice),
            request_->riskControls->aggregateShortInterest(assetIndex), 0.0,
            request_->riskControls->initialShareSupply(assetIndex),
            request_->config->shortSale.initialMarginRequirement,
            request_->config->shortSale.borrowableSupplyRatio});
    }

    std::vector<LimitOrderBook>* orderBooks_;
    const OrderExecutionRequest* request_;
    std::vector<MicrostructureStepResult> results_;
    std::vector<std::vector<AllocativeEfficiencyTrade>> allocativeTradesByAsset_;
};

} // namespace

void MarketClearingEngine::resetForRun(std::size_t assetCount) {
    orderBooks_.assign(std::max<std::size_t>(1, assetCount), LimitOrderBook{});
}

void MarketClearingEngine::clear() {
    for (LimitOrderBook& orderBook : orderBooks_) {
        orderBook.clear();
    }
}

std::vector<RestingOrderLifecycleCounts>
MarketClearingEngine::processRestingOrders(const RestingOrderProcessingRequest& request,
                                           RandomEngine& random) {
    std::vector<RestingOrderLifecycleCounts> counts(orderBooks_.size());
    for (std::size_t assetIndex = 0; assetIndex < orderBooks_.size(); ++assetIndex) {
        const double referencePrice =
            request.referencePrices != nullptr && assetIndex < request.referencePrices->size()
                ? (*request.referencePrices)[assetIndex]
                : 0.0;
        counts[assetIndex].expiredOrders = orderBooks_[assetIndex].expireOrders(request.timeStep);
        counts[assetIndex].cancelledOrders = orderBooks_[assetIndex].cancelStaleOrders(
            referencePrice, request.config->cancellationBaseProbability,
            request.config->cancellationMispricingSensitivity, random);
    }
    return counts;
}

std::vector<MicrostructureStepResult>
MarketClearingEngine::executeOrders(const OrderExecutionRequest& request) {
    const std::size_t assetCount =
        std::max<std::size_t>(1, request.config != nullptr ? request.config->assets.size() : 1);
    if (orderBooks_.size() != assetCount) {
        orderBooks_.assign(assetCount, LimitOrderBook{});
    }

    OrderExecutionSession session(&orderBooks_, request);
    return session.execute();
}

} // namespace abm
