// ShortSaleRiskControls.h

#ifndef RISK_MANAGEMENT_SHORT_SALE_RISK_CONTROLS_H
#define RISK_MANAGEMENT_SHORT_SALE_RISK_CONTROLS_H

namespace abm {

/**
 * Inputs needed to clip a sell order by short-sale margin and borrow constraints.
 *
 * Grouping these quantities makes call sites self-documenting and prevents
 * accidental swaps among same-typed financial state variables.
 */
struct ShortSaleSellConstraintRequest {
    double requestedSellQuantity;
    double currentStock;
    double cash;
    double price;
    double currentShortInterest;
    double reservedNewShortShares;
    double totalShareSupply;
    double initialMarginRequirement;
    double borrowableSupplyRatio;
};

/**
 * Inputs used to calculate a broker-style forced buy-to-cover quantity.
 */
struct ShortSaleMarginCallRequest {
    double cash;
    double currentStock;
    double price;
    double initialMarginRequirement;
    double maintenanceMarginRequirement;
};

/**
 * Returns the absolute short inventory represented by a signed stock position.
 *
 * The model stores long positions as positive inventory and short positions as
 * negative inventory. This helper keeps the sign convention local to the risk
 * management layer.
 */
[[nodiscard]] double shortPositionShares(double stock);

/**
 * Computes agent equity using marked-to-market short liabilities.
 *
 * Equity is cash plus signed inventory valued at the current market price. For
 * a short seller, negative inventory therefore subtracts the cost of buying
 * back borrowed shares. This is the balance-sheet quantity used by margin
 * constraints in the short-sale literature and broker risk controls.
 */
[[nodiscard]] double markedToMarketEquity(double cash, double stock, double price);

/**
 * Returns equity divided by current short notional.
 *
 * Long-only or flat agents have no short notional, so the function returns
 * infinity. A finite ratio below the maintenance margin signals that the broker
 * should force the agent to buy shares and reduce the short position.
 */
[[nodiscard]] double shortMarginRatio(double cash, double stock, double price);

/**
 * Converts an initial-margin requirement into a maximum short position.
 *
 * In this ABM the initial margin requirement is modelled as:
 *
 *     agent_equity >= initial_margin_requirement * short_notional
 *
 * This deliberately simple formulation makes the maximum permitted short
 * exposure transparent for calibration experiments.
 */
[[nodiscard]] double maximumShortSharesByInitialMargin(double equity, double price,
                                                       double initialMarginRequirement);

/**
 * Returns the remaining aggregate borrowable share supply.
 *
 * The borrowable pool is expressed as a fraction of total share supply. Existing
 * short interest and same-period locate reservations are deducted so submitted
 * orders cannot create more new shorts than the model assumes can be borrowed.
 */
[[nodiscard]] double remainingBorrowableShortShares(double currentShortInterest,
                                                    double reservedNewShortShares,
                                                    double totalShareSupply,
                                                    double borrowableSupplyRatio);

/**
 * Applies initial margin and borrow availability to a requested sell quantity.
 *
 * Long inventory can always be sold. The part of a sell order that would create
 * or increase a short position is clipped by both the agent-level initial margin
 * capacity and the market-level borrowable share supply.
 */
[[nodiscard]] double
constrainSellQuantityByShortSaleRules(const ShortSaleSellConstraintRequest& request);

/**
 * Calculates the forced buy-to-cover quantity needed after a margin breach.
 *
 * If the maintenance margin is breached, the broker reduces the short position
 * far enough to restore the stricter initial-margin ratio when possible. This
 * creates a clear crisis-period deleveraging channel: rising prices against
 * short sellers force them to cover part of their position.
 */
[[nodiscard]] double requiredBuyToCoverQuantity(const ShortSaleMarginCallRequest& request);

} // namespace abm

#endif // RISK_MANAGEMENT_SHORT_SALE_RISK_CONTROLS_H
