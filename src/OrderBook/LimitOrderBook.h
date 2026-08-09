// LimitOrderBook.h

#ifndef LIMIT_ORDER_BOOK_H
#define LIMIT_ORDER_BOOK_H

#include <cstddef>
#include <optional>
#include <set>
#include <vector>

#include "OrderBook/Order.h"

namespace abm {

class RandomEngine;

/** Snapshot of the visible state of the persistent limit order book. */
struct LimitOrderBookMetrics {
    double bestBid{0.0};
    double bestAsk{0.0};
    double bidAskSpread{0.0};
    double midQuote{0.0};
    double bidDepth{0.0};
    double askDepth{0.0};
    std::size_t restingBidOrders{0};
    std::size_t restingAskOrders{0};
};

/** Copy-only snapshot of resting order liquidity on both sides of the book. */
struct LimitOrderBookSnapshot {
    std::vector<Order> bids;
    std::vector<Order> asks;
};

/**
 * Persistent continuous double-auction order book.
 *
 * The book owns priority and lifecycle mechanics only. The simulation
 * coordinator remains responsible for cash, inventory, margin, and borrow
 * validation because those constraints depend on current agent balance sheets.
 */
class LimitOrderBook {
  public:
    /** Removes all resting orders and resets sequence priority. */
    void clear();

    /** Assigns time-priority metadata and submits a non-marketable resting order. */
    void submitRestingOrder(Order order);

    /** Returns true when the incoming order can execute against the opposite book. */
    [[nodiscard]] bool canMatch(const Order& incomingOrder) const;

    /** Returns the current best order on the opposite side of the incoming order. */
    [[nodiscard]] const Order& bestOpposingOrder(const Order& incomingOrder) const;

    /** Reduces the current best opposite order and removes it if fully filled. */
    void reduceBestOpposingOrder(const Order& incomingOrder, double fillQuantity);

    /** Removes the current best opposite order, usually after it becomes infeasible. */
    void removeBestOpposingOrder(const Order& incomingOrder);

    /** Expires resting orders whose expiry time has passed. */
    [[nodiscard]] std::size_t expireOrders(std::size_t currentTimeStep);

    /** Applies deterministic random and stale-price cancellations to resting orders. */
    [[nodiscard]] std::size_t cancelStaleOrders(double referencePrice,
                                                double baseProbability,
                                                double mispricingSensitivity,
                                                RandomEngine& random);

    /** Aggregates spread, best quote, depth, and resting-order diagnostics. */
    [[nodiscard]] LimitOrderBookMetrics metrics(std::size_t depthLevels) const;

    /** Returns a copy of all resting orders for non-mutating diagnostics. */
    [[nodiscard]] LimitOrderBookSnapshot restingOrdersSnapshot() const;

    /** Returns the best resting bid when available. */
    [[nodiscard]] std::optional<Order> bestBidOrder() const;

    /** Returns the best resting ask when available. */
    [[nodiscard]] std::optional<Order> bestAskOrder() const;

    /** Returns the next stable sequence number without advancing it. */
    [[nodiscard]] std::size_t nextSequence() const;

  private:
    struct BidOrderPriority {
        bool operator()(const Order& lhs, const Order& rhs) const;
    };

    struct AskOrderPriority {
        bool operator()(const Order& lhs, const Order& rhs) const;
    };

    using BidBook = std::multiset<Order, BidOrderPriority>;
    using AskBook = std::multiset<Order, AskOrderPriority>;

    [[nodiscard]] static bool crosses(const Order& incomingOrder, const Order& restingOrder);

    BidBook bids_;
    AskBook asks_;
    std::size_t nextSequence_{1};
};

} // namespace abm

#endif // LIMIT_ORDER_BOOK_H
