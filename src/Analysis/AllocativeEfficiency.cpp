// AllocativeEfficiency.cpp

#include "Analysis/AllocativeEfficiency.h"

#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>
#include <utility>

namespace abm {
namespace {

struct SurplusScheduleOrder {
    double reservationPrice{0.0};
    double quantity{0.0};
};

[[nodiscard]] bool isUsableSurplusQuantity(double quantity) {
    return std::isfinite(quantity) && quantity > kMinimumOrderQuantity;
}

[[nodiscard]] bool isUsableReservationPrice(double price) {
    return std::isfinite(price) && price > kMinimumPrice;
}

void appendIfUsable(std::vector<SurplusScheduleOrder>& target,
                    const AllocativeEfficiencyOrder& order) {
    if (isUsableReservationPrice(order.reservationPrice) &&
        isUsableSurplusQuantity(order.quantity)) {
        target.push_back(SurplusScheduleOrder{order.reservationPrice, order.quantity});
    }
}

} // namespace

double calculateMaximumAllocativeSurplus(std::vector<AllocativeEfficiencyOrder> orders) {
    std::vector<SurplusScheduleOrder> buyOrders;
    std::vector<SurplusScheduleOrder> sellOrders;
    buyOrders.reserve(orders.size());
    sellOrders.reserve(orders.size());

    for (const AllocativeEfficiencyOrder& order : orders) {
        if (order.side == OrderType::BUY) {
            appendIfUsable(buyOrders, order);
        } else {
            appendIfUsable(sellOrders, order);
        }
    }

    std::sort(buyOrders.begin(), buyOrders.end(),
              [](const SurplusScheduleOrder& lhs, const SurplusScheduleOrder& rhs) {
                  return lhs.reservationPrice > rhs.reservationPrice;
              });
    std::sort(sellOrders.begin(), sellOrders.end(),
              [](const SurplusScheduleOrder& lhs, const SurplusScheduleOrder& rhs) {
                  return lhs.reservationPrice < rhs.reservationPrice;
              });

    double maximumSurplus = 0.0;
    std::size_t buyIndex = 0;
    std::size_t sellIndex = 0;
    while (buyIndex < buyOrders.size() && sellIndex < sellOrders.size()) {
        const double marginalSurplus =
            buyOrders[buyIndex].reservationPrice - sellOrders[sellIndex].reservationPrice;
        if (marginalSurplus <= kMinimumPrice) {
            break;
        }

        const double matchedQuantity =
            std::min(buyOrders[buyIndex].quantity, sellOrders[sellIndex].quantity);
        /*
         * Formula note:
         * S_max += q_match * (v_buy - v_sell).
         *
         * The schedules have already been sorted by reservation value, so matching
         * the current marginal buyer and seller gives the efficient double-auction
         * allocation for the submitted order set.
         */
        maximumSurplus += matchedQuantity * marginalSurplus;

        buyOrders[buyIndex].quantity -= matchedQuantity;
        sellOrders[sellIndex].quantity -= matchedQuantity;
        if (buyOrders[buyIndex].quantity <= kMinimumOrderQuantity) {
            ++buyIndex;
        }
        if (sellOrders[sellIndex].quantity <= kMinimumOrderQuantity) {
            ++sellIndex;
        }
    }

    return maximumSurplus;
}

double calculateRealizedAllocativeSurplus(const std::vector<AllocativeEfficiencyTrade>& trades) {
    double realizedSurplus = 0.0;
    for (const AllocativeEfficiencyTrade& trade : trades) {
        if (!isUsableReservationPrice(trade.buyerReservationPrice) ||
            !isUsableReservationPrice(trade.sellerReservationPrice) ||
            !isUsableSurplusQuantity(trade.quantity)) {
            continue;
        }
        realizedSurplus +=
            trade.quantity * (trade.buyerReservationPrice - trade.sellerReservationPrice);
    }
    return realizedSurplus;
}

AllocativeEfficiencyResult
calculateAllocativeEfficiency(std::vector<AllocativeEfficiencyOrder> orders,
                              const std::vector<AllocativeEfficiencyTrade>& trades) {
    AllocativeEfficiencyResult result{};
    result.realizedSurplus = calculateRealizedAllocativeSurplus(trades);
    result.maximumSurplus = calculateMaximumAllocativeSurplus(std::move(orders));
    if (result.maximumSurplus > kMinimumPrice) {
        result.efficiency = result.realizedSurplus / result.maximumSurplus;
    }
    return result;
}

} // namespace abm
