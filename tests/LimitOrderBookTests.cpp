// LimitOrderBookTests.cpp

#include "tests/TestSupport.h"

#include "OrderBook/LimitOrderBook.h"
#include "RandomGenerator/RandomGenerator.h"

#include <algorithm>
#include <cstddef>

namespace {

abm::Order makeOrder(int orderId, int ownerAgentId, abm::OrderType side, abm::OrderStyle style,
                     double price, double quantity, std::size_t creationTimeStep = 1,
                     std::size_t expiryTimeStep = 10) {
    abm::Order order{};
    order.orderId = orderId;
    order.ownerAgentId = ownerAgentId;
    order.type = side;
    order.style = style;
    order.price = price;
    order.quantity = quantity;
    order.remainingQuantity = quantity;
    order.timeStep = static_cast<int>(creationTimeStep);
    order.creationTimeStep = creationTimeStep;
    order.expiryTimeStep = expiryTimeStep;
    return order;
}

void consumeBestOpposing(abm::LimitOrderBook& book, abm::Order& incomingOrder) {
    while (incomingOrder.remainingQuantity > 0.0 && book.canMatch(incomingOrder)) {
        const abm::Order restingOrder = book.bestOpposingOrder(incomingOrder);
        const double fillQuantity =
            std::min(incomingOrder.remainingQuantity, restingOrder.remainingQuantity);
        incomingOrder.remainingQuantity =
            std::max(0.0, incomingOrder.remainingQuantity - fillQuantity);
        book.reduceBestOpposingOrder(incomingOrder, fillQuantity);
    }
}

void testBookPriorityUsesPriceThenFifo(int& failures) {
    abm::LimitOrderBook book;
    book.submitRestingOrder(
        makeOrder(1, 1, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 99.0, 1.0));
    book.submitRestingOrder(
        makeOrder(2, 2, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 101.0, 1.0));
    book.submitRestingOrder(
        makeOrder(3, 3, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 101.0, 1.0));

    abm::Order incomingSell =
        makeOrder(10, 10, abm::OrderType::SELL, abm::OrderStyle::MARKET, 0.0, 1.0);
    abm::test::expect(book.bestOpposingOrder(incomingSell).orderId == 2,
                      "book should prioritise the highest bid, then FIFO within price", failures);
    book.removeBestOpposingOrder(incomingSell);
    abm::test::expect(book.bestOpposingOrder(incomingSell).orderId == 3,
                      "book should retain FIFO priority after the first same-price bid is removed",
                      failures);

    book.clear();
    book.submitRestingOrder(
        makeOrder(4, 4, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 103.0, 1.0));
    book.submitRestingOrder(
        makeOrder(5, 5, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 1.0));
    book.submitRestingOrder(
        makeOrder(6, 6, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 1.0));

    abm::Order incomingBuy =
        makeOrder(11, 11, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 1.0);
    abm::test::expect(book.bestOpposingOrder(incomingBuy).orderId == 5,
                      "book should prioritise the lowest ask, then FIFO within price", failures);
    book.removeBestOpposingOrder(incomingBuy);
    abm::test::expect(book.bestOpposingOrder(incomingBuy).orderId == 6,
                      "book should retain FIFO priority after the first same-price ask is removed",
                      failures);
}

void testLimitOrderCrossesAndPartialFillLeavesResidual(int& failures) {
    abm::LimitOrderBook book;
    book.submitRestingOrder(
        makeOrder(1, 1, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 3.0));

    abm::Order incomingBuy =
        makeOrder(2, 2, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 105.0, 2.0);
    abm::test::expect(book.canMatch(incomingBuy),
                      "crossing limit buy should match the best resting ask", failures);
    consumeBestOpposing(book, incomingBuy);

    abm::Order probe = makeOrder(3, 3, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 1.0);
    abm::test::expect(book.canMatch(probe), "partially filled resting ask should remain executable",
                      failures);
    abm::test::expect(
        abm::test::nearlyEqual(book.bestOpposingOrder(probe).remainingQuantity, 1.0),
        "partial fill should leave the correct residual quantity on the resting order", failures);
}

void testPartialFillPreservesResidualTimePriority(int& failures) {
    abm::LimitOrderBook book;
    book.submitRestingOrder(
        makeOrder(1, 1, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 3.0));
    book.submitRestingOrder(
        makeOrder(2, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 1.0));

    abm::Order incomingBuy =
        makeOrder(3, 3, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 2.0);
    consumeBestOpposing(book, incomingBuy);

    abm::Order probe = makeOrder(4, 4, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 1.0);
    abm::test::expect(book.bestOpposingOrder(probe).orderId == 1,
                      "partial fills should keep the older same-price order at the front",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(book.bestOpposingOrder(probe).remainingQuantity, 1.0),
                      "partial fills should preserve the older order's residual quantity",
                      failures);

    consumeBestOpposing(book, probe);
    abm::Order nextProbe = makeOrder(5, 5, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 1.0);
    abm::test::expect(book.bestOpposingOrder(nextProbe).orderId == 2,
                      "later same-price orders should trade only after older residuals finish",
                      failures);
}

void testMarketOrderWalksMultiplePriceLevels(int& failures) {
    abm::LimitOrderBook book;
    book.submitRestingOrder(
        makeOrder(1, 1, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 100.0, 2.0));
    book.submitRestingOrder(
        makeOrder(2, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 101.0, 3.0));

    abm::Order incomingBuy =
        makeOrder(3, 3, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 4.0);
    consumeBestOpposing(book, incomingBuy);

    abm::Order probe = makeOrder(4, 4, abm::OrderType::BUY, abm::OrderStyle::MARKET, 0.0, 1.0);
    abm::test::expect(abm::test::nearlyEqual(incomingBuy.remainingQuantity, 0.0),
                      "market order should consume available depth until filled", failures);
    abm::test::expect(book.bestOpposingOrder(probe).orderId == 2,
                      "market order should walk from the first ask level to the second", failures);
    abm::test::expect(abm::test::nearlyEqual(book.bestOpposingOrder(probe).remainingQuantity, 1.0),
                      "market order should leave the correct residual at the second price level",
                      failures);
}

void testNonCrossingLimitOrderRests(int& failures) {
    abm::LimitOrderBook book;
    book.submitRestingOrder(
        makeOrder(1, 1, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 101.0, 1.0));

    abm::Order incomingBuy =
        makeOrder(2, 2, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 100.0, 2.0);
    abm::test::expect(!book.canMatch(incomingBuy),
                      "non-crossing limit buy should not match the best ask", failures);
    book.submitRestingOrder(incomingBuy);

    const abm::LimitOrderBookMetrics metrics = book.metrics(5);
    abm::test::expect(metrics.restingBidOrders == 1 && metrics.restingAskOrders == 1,
                      "non-crossing limit order should rest beside the existing opposite side",
                      failures);
    abm::test::expect(abm::test::nearlyEqual(metrics.bestBid, 100.0) &&
                          abm::test::nearlyEqual(metrics.bestAsk, 101.0),
                      "resting non-crossing order should define the visible spread", failures);
}

void testMetricsAggregateBestQuotesSpreadAndVisibleDepth(int& failures) {
    abm::LimitOrderBook book;
    book.submitRestingOrder(
        makeOrder(1, 1, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 101.0, 2.0));
    book.submitRestingOrder(
        makeOrder(2, 2, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 100.0, 3.0));
    book.submitRestingOrder(
        makeOrder(3, 3, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 99.0, 4.0));
    book.submitRestingOrder(
        makeOrder(4, 4, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 102.0, 5.0));
    book.submitRestingOrder(
        makeOrder(5, 5, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 103.0, 6.0));
    book.submitRestingOrder(
        makeOrder(6, 6, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 104.0, 7.0));

    const abm::LimitOrderBookMetrics metrics = book.metrics(2);
    abm::test::expect(abm::test::nearlyEqual(metrics.bestBid, 101.0) &&
                          abm::test::nearlyEqual(metrics.bestAsk, 102.0),
                      "book metrics should report the best bid and ask", failures);
    abm::test::expect(abm::test::nearlyEqual(metrics.bidAskSpread, 1.0) &&
                          abm::test::nearlyEqual(metrics.midQuote, 101.5),
                      "book metrics should report spread and midquote", failures);
    abm::test::expect(abm::test::nearlyEqual(metrics.bidDepth, 5.0) &&
                          abm::test::nearlyEqual(metrics.askDepth, 11.0),
                      "book metrics should aggregate only the requested visible price levels",
                      failures);
    abm::test::expect(metrics.restingBidOrders == 3 && metrics.restingAskOrders == 3,
                      "book metrics should count resting orders on both sides", failures);

    const abm::LimitOrderBookMetrics zeroDepthMetrics = book.metrics(0);
    abm::test::expect(abm::test::nearlyEqual(zeroDepthMetrics.bidDepth, 0.0) &&
                          abm::test::nearlyEqual(zeroDepthMetrics.askDepth, 0.0),
                      "zero requested book depth should suppress visible-depth aggregation",
                      failures);
}

void testRestingOrderPersistsAndExpires(int& failures) {
    abm::LimitOrderBook book;
    book.submitRestingOrder(
        makeOrder(1, 1, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 99.0, 1.0, 1, 2));

    abm::test::expect(book.expireOrders(2) == 0,
                      "resting order should remain valid through its expiry time step", failures);
    abm::test::expect(book.metrics(5).restingBidOrders == 1,
                      "resting order should persist across steps before expiry", failures);
    abm::test::expect(book.expireOrders(3) == 1,
                      "resting order should be removed after its expiry time step", failures);
    abm::test::expect(book.metrics(5).restingBidOrders == 0,
                      "expired order should no longer contribute to book depth", failures);
}

void testCancellationCanBeDeterministicUnderFixedSeed(int& failures) {
    abm::LimitOrderBook book;
    book.submitRestingOrder(
        makeOrder(1, 1, abm::OrderType::BUY, abm::OrderStyle::LIMIT, 99.0, 1.0));
    book.submitRestingOrder(
        makeOrder(2, 2, abm::OrderType::SELL, abm::OrderStyle::LIMIT, 101.0, 1.0));

    abm::RandomEngine random(123U);
    const std::size_t cancelled = book.cancelStaleOrders(100.0, 1.0, 0.0, random);
    abm::test::expect(cancelled == 2,
                      "unit cancellation probability should remove every eligible resting order",
                      failures);
    abm::test::expect(book.metrics(5).restingBidOrders == 0 &&
                          book.metrics(5).restingAskOrders == 0,
                      "cancelled orders should be absent from both sides of the book", failures);
}

} // namespace

namespace abm::test {

void runLimitOrderBookTests(int& failures) {
    testBookPriorityUsesPriceThenFifo(failures);
    testLimitOrderCrossesAndPartialFillLeavesResidual(failures);
    testPartialFillPreservesResidualTimePriority(failures);
    testMarketOrderWalksMultiplePriceLevels(failures);
    testNonCrossingLimitOrderRests(failures);
    testMetricsAggregateBestQuotesSpreadAndVisibleDepth(failures);
    testRestingOrderPersistsAndExpires(failures);
    testCancellationCanBeDeterministicUnderFixedSeed(failures);
}

} // namespace abm::test
