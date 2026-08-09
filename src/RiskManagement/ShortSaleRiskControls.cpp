// ShortSaleRiskControls.cpp

#include "RiskManagement/ShortSaleRiskControls.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace abm {
namespace {
constexpr double kMinimumPrice = 1e-12;
constexpr double kMinimumMarginRequirement = 1e-12;

double positivePart(double value) {
    return std::max(0.0, value);
}

} // namespace

double shortPositionShares(double stock) {
    /*
     * Formula note:
     * s_i^- = max(0, -x_i).
     */
    return positivePart(-stock);
}

double markedToMarketEquity(double cash, double stock, double price) {
    if (!std::isfinite(cash) || !std::isfinite(stock) || !std::isfinite(price) ||
        price <= kMinimumPrice) {
        return 0.0;
    }

    /*
     * Formula note:
     * W_i,t = c_i,t + x_i,t * P_t.
     */
    return cash + (stock * price);
}

double shortMarginRatio(double cash, double stock, double price) {
    const double shortShares = shortPositionShares(stock);
    const double shortNotional = shortShares * std::max(price, kMinimumPrice);
    if (shortNotional <= 0.0) {
        return std::numeric_limits<double>::infinity();
    }

    /*
     * Formula note:
     * margin_ratio = W_i,t / (s_i^- * P_t).
     *
     * The denominator is the marked-to-market notional of the open short
     * position; a long-only account has no binding short-margin ratio.
     */
    return markedToMarketEquity(cash, stock, price) / shortNotional;
}

double maximumShortSharesByInitialMargin(double equity, double price,
                                         double initialMarginRequirement) {
    if (!std::isfinite(equity) || !std::isfinite(price) ||
        !std::isfinite(initialMarginRequirement) || equity <= 0.0 || price <= kMinimumPrice ||
        initialMarginRequirement <= kMinimumMarginRequirement) {
        return 0.0;
    }

    /*
     * Formula note:
     * max_short_shares = W_i,t / (M_0^S * P_t).
     */
    return equity / (initialMarginRequirement * price);
}

double remainingBorrowableShortShares(double currentShortInterest, double reservedNewShortShares,
                                      double totalShareSupply, double borrowableSupplyRatio) {
    if (!std::isfinite(currentShortInterest) || !std::isfinite(reservedNewShortShares) ||
        !std::isfinite(totalShareSupply) || !std::isfinite(borrowableSupplyRatio)) {
        return 0.0;
    }

    const double maximumBorrowableShares =
        positivePart(totalShareSupply) * std::clamp(borrowableSupplyRatio, 0.0, 1.0);
    const double alreadyLocatedOrBorrowed =
        positivePart(currentShortInterest) + positivePart(reservedNewShortShares);

    /*
     * Formula note:
     * remaining_borrow = max(0, phi_B * X_0 - SI_t - reserved_short).
     */
    return positivePart(maximumBorrowableShares - alreadyLocatedOrBorrowed);
}

double constrainSellQuantityByShortSaleRules(const ShortSaleSellConstraintRequest& request) {
    const double requestedQuantity = positivePart(request.requestedSellQuantity);
    if (requestedQuantity <= 0.0) {
        return 0.0;
    }

    const double longSharesAvailable = positivePart(request.currentStock);
    const double requestedNewShortShares = positivePart(requestedQuantity - longSharesAvailable);
    if (requestedNewShortShares <= 0.0) {
        return requestedQuantity;
    }

    const double equity = markedToMarketEquity(request.cash, request.currentStock, request.price);
    const double currentAgentShortShares = shortPositionShares(request.currentStock);
    const double maximumAgentShortShares =
        maximumShortSharesByInitialMargin(equity, request.price, request.initialMarginRequirement);
    const double remainingAgentShortCapacity =
        positivePart(maximumAgentShortShares - currentAgentShortShares);
    const double remainingBorrowCapacity =
        remainingBorrowableShortShares(request.currentShortInterest, request.reservedNewShortShares,
                                       request.totalShareSupply, request.borrowableSupplyRatio);

    const double permittedNewShortShares =
        std::min({requestedNewShortShares, remainingAgentShortCapacity, remainingBorrowCapacity});

    /*
     * Formula note:
     * q_sell_allowed = long_shares + min(requested_new_short,
     *                                    agent_short_capacity,
     *                                    borrow_capacity).
     */
    return longSharesAvailable + permittedNewShortShares;
}

double requiredBuyToCoverQuantity(const ShortSaleMarginCallRequest& request) {
    const double currentShortShares = shortPositionShares(request.currentStock);
    if (currentShortShares <= 0.0) {
        return 0.0;
    }

    if (shortMarginRatio(request.cash, request.currentStock, request.price) >=
        request.maintenanceMarginRequirement) {
        return 0.0;
    }

    const double equity = markedToMarketEquity(request.cash, request.currentStock, request.price);
    const double targetShortShares =
        maximumShortSharesByInitialMargin(equity, request.price, request.initialMarginRequirement);

    /*
     * Formula note:
     * buy_to_cover = max(0, current_short_shares
     *                       - min(current_short_shares, target_short_shares)).
     *
     * The target is recomputed from the stricter initial-margin requirement so
     * the forced cover moves the account back inside the opening-risk limit.
     */
    return positivePart(currentShortShares - std::min(currentShortShares, targetShortShares));
}

} // namespace abm
