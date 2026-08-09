// LimitOrderBook.cpp

#include "OrderBook/LimitOrderBook.h"

#include "RandomGenerator/RandomGenerator.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace abm {
namespace {

double positiveQuantity(double quantity) {
    return std::max(0.0, quantity);
}

bool shouldExpire(const Order& order, std::size_t currentTimeStep) {
    return order.expiryTimeStep > 0 && currentTimeStep > order.expiryTimeStep;
}

double cancellationProbability(const Order& order, double referencePrice, double baseProbability,
                               double mispricingSensitivity) {
    if (order.style == OrderStyle::MARKET || order.price <= kMinimumPrice ||
        referencePrice <= kMinimumPrice) {
        return std::clamp(baseProbability, 0.0, 1.0);
    }

    const double logDistance = std::abs(std::log(order.price / referencePrice));
    /*
     * Formula note:
     * Pr(cancel) = clamp(rho_0 + gamma_mis * |log(P_order / P_ref)|, 0, 1).
     *
     * Orders farther from the current reference price are more likely to be
     * removed as stale liquidity.
     */
    return std::clamp(baseProbability + (mispricingSensitivity * logDistance), 0.0, 1.0);
}

template <typename Book>
double visibleDepthByPriceLevel(const Book& book, std::size_t depthLevels) {
    if (depthLevels == 0) {
        return 0.0;
    }

    double depth = 0.0;
    std::size_t observedLevels = 0;
    double currentLevelPrice = 0.0;
    bool hasCurrentLevel = false;

    for (const Order& order : book) {
        if (!hasCurrentLevel || std::abs(order.price - currentLevelPrice) > kMinimumPrice) {
            if (observedLevels >= depthLevels) {
                break;
            }
            currentLevelPrice = order.price;
            hasCurrentLevel = true;
            ++observedLevels;
        }
        depth += order.remainingQuantity;
    }

    /*
     * Formula note:
     * visible_depth(h) = sum of remaining quantities across the first h
     * distinct price levels on one side of the book.
     */
    return depth;
}

template <typename Book> void reduceBestOrder(Book& book, double fillQuantity) {
    if (book.empty()) {
        return;
    }

    Order updatedOrder = *book.begin();
    book.erase(book.begin());
    updatedOrder.remainingQuantity =
        positiveQuantity(updatedOrder.remainingQuantity - positiveQuantity(fillQuantity));
    if (updatedOrder.remainingQuantity > kMinimumOrderQuantity) {
        book.insert(updatedOrder);
    }
}

template <typename Book> std::size_t eraseExpiredOrders(Book& book, std::size_t currentTimeStep) {
    const std::size_t oldSize = book.size();
    for (auto it = book.begin(); it != book.end();) {
        if (shouldExpire(*it, currentTimeStep)) {
            it = book.erase(it);
        } else {
            ++it;
        }
    }
    return oldSize - book.size();
}

template <typename Book>
std::size_t cancelOrders(Book& book, double referencePrice, double baseProbability,
                         double mispricingSensitivity, RandomEngine& random) {
    const std::size_t oldSize = book.size();
    for (auto it = book.begin(); it != book.end();) {
        const double probability =
            cancellationProbability(*it, referencePrice, baseProbability, mispricingSensitivity);
        if (random.generateUniformDist(0.0, 1.0) < probability) {
            it = book.erase(it);
        } else {
            ++it;
        }
    }
    return oldSize - book.size();
}

} // namespace

void LimitOrderBook::clear() {
    bids_.clear();
    asks_.clear();
    nextSequence_ = 1;
}

void LimitOrderBook::submitRestingOrder(Order order) {
    if (order.style != OrderStyle::LIMIT || order.remainingQuantity <= kMinimumOrderQuantity) {
        return;
    }
    if (order.price <= kMinimumPrice) {
        return;
    }
    if (order.sequence == 0) {
        order.sequence = nextSequence_++;
    } else {
        nextSequence_ = std::max(nextSequence_, order.sequence + 1);
    }

    if (order.type == OrderType::BUY) {
        bids_.insert(order);
    } else {
        asks_.insert(order);
    }
}

bool LimitOrderBook::canMatch(const Order& incomingOrder) const {
    if (incomingOrder.remainingQuantity <= kMinimumOrderQuantity) {
        return false;
    }
    if (incomingOrder.type == OrderType::BUY) {
        return !asks_.empty() && crosses(incomingOrder, *asks_.begin());
    }
    return !bids_.empty() && crosses(incomingOrder, *bids_.begin());
}

const Order& LimitOrderBook::bestOpposingOrder(const Order& incomingOrder) const {
    if (incomingOrder.type == OrderType::BUY) {
        if (asks_.empty()) {
            throw std::out_of_range("No opposing order is available.");
        }
        return *asks_.begin();
    }
    if (bids_.empty()) {
        throw std::out_of_range("No opposing order is available.");
    }
    return *bids_.begin();
}

void LimitOrderBook::reduceBestOpposingOrder(const Order& incomingOrder, double fillQuantity) {
    if (incomingOrder.type == OrderType::BUY) {
        reduceBestOrder(asks_, fillQuantity);
    } else {
        reduceBestOrder(bids_, fillQuantity);
    }
}

void LimitOrderBook::removeBestOpposingOrder(const Order& incomingOrder) {
    if (incomingOrder.type == OrderType::BUY) {
        if (!asks_.empty()) {
            asks_.erase(asks_.begin());
        }
    } else if (!bids_.empty()) {
        bids_.erase(bids_.begin());
    }
}

std::size_t LimitOrderBook::expireOrders(std::size_t currentTimeStep) {
    return eraseExpiredOrders(bids_, currentTimeStep) + eraseExpiredOrders(asks_, currentTimeStep);
}

std::size_t LimitOrderBook::cancelStaleOrders(double referencePrice, double baseProbability,
                                              double mispricingSensitivity, RandomEngine& random) {
    return cancelOrders(bids_, referencePrice, baseProbability, mispricingSensitivity, random) +
           cancelOrders(asks_, referencePrice, baseProbability, mispricingSensitivity, random);
}

LimitOrderBookMetrics LimitOrderBook::metrics(std::size_t depthLevels) const {
    LimitOrderBookMetrics snapshot{};
    snapshot.restingBidOrders = bids_.size();
    snapshot.restingAskOrders = asks_.size();

    if (!bids_.empty()) {
        snapshot.bestBid = bids_.begin()->price;
    }
    if (!asks_.empty()) {
        snapshot.bestAsk = asks_.begin()->price;
    }
    if (snapshot.bestBid > 0.0 && snapshot.bestAsk > 0.0) {
        /*
         * Formula note:
         * spread_t = best_ask_t - best_bid_t,
         * midquote_t = (best_bid_t + best_ask_t) / 2.
         */
        snapshot.bidAskSpread = std::max(0.0, snapshot.bestAsk - snapshot.bestBid);
        snapshot.midQuote = 0.5 * (snapshot.bestBid + snapshot.bestAsk);
    }

    snapshot.bidDepth = visibleDepthByPriceLevel(bids_, depthLevels);
    snapshot.askDepth = visibleDepthByPriceLevel(asks_, depthLevels);

    return snapshot;
}

LimitOrderBookSnapshot LimitOrderBook::restingOrdersSnapshot() const {
    LimitOrderBookSnapshot snapshot;
    snapshot.bids.reserve(bids_.size());
    snapshot.asks.reserve(asks_.size());
    for (const Order& order : bids_) {
        snapshot.bids.push_back(order);
    }
    for (const Order& order : asks_) {
        snapshot.asks.push_back(order);
    }
    return snapshot;
}

std::optional<Order> LimitOrderBook::bestBidOrder() const {
    if (bids_.empty()) {
        return std::nullopt;
    }
    return *bids_.begin();
}

std::optional<Order> LimitOrderBook::bestAskOrder() const {
    if (asks_.empty()) {
        return std::nullopt;
    }
    return *asks_.begin();
}

std::size_t LimitOrderBook::nextSequence() const {
    return nextSequence_;
}

bool LimitOrderBook::BidOrderPriority::operator()(const Order& lhs, const Order& rhs) const {
    if (lhs.price != rhs.price) {
        return lhs.price > rhs.price;
    }
    return lhs.sequence < rhs.sequence;
}

bool LimitOrderBook::AskOrderPriority::operator()(const Order& lhs, const Order& rhs) const {
    if (lhs.price != rhs.price) {
        return lhs.price < rhs.price;
    }
    return lhs.sequence < rhs.sequence;
}

bool LimitOrderBook::crosses(const Order& incomingOrder, const Order& restingOrder) {
    if (incomingOrder.style == OrderStyle::MARKET) {
        return true;
    }
    if (incomingOrder.type == OrderType::BUY) {
        return incomingOrder.price + kMinimumPrice >= restingOrder.price;
    }
    return incomingOrder.price <= restingOrder.price + kMinimumPrice;
}

} // namespace abm
