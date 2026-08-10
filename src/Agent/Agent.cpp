// Agent.cpp

#include "Agent/Agent.h"
#include "Utility/NumericValidation.h"
#include "Utility/SimulationConstants.h"

#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace abm {
namespace {
int positionSign(double stock) {
    if (stock > kMinimumOrderQuantity) {
        return 1;
    }
    if (stock < -kMinimumOrderQuantity) {
        return -1;
    }
    return 0;
}

} // namespace

Agent::Agent()
    : numericalId(0), initialCash(0.0), initialStockByAsset{0.0}, cash(0.0), stockByAsset{0.0},
      executedTradeCount(0), executedTradeVolume(0.0), cumulativeTransactionCostsPaid(0.0),
      xCoordinate(0.0), yCoordinate(0.0), socialGamma(0.0), privateSignalStdDev(0.0),
      previousOpinionValue(0.0), currentOpinionValue(0.0),
      initialWealth(std::numeric_limits<double>::quiet_NaN()),
      wealth(std::numeric_limits<double>::quiet_NaN()),
      lastValuationPrices{std::numeric_limits<double>::quiet_NaN()}, prospectTheoryEnabled(true),
      positionAnchors(1), recentPeakWealth(std::numeric_limits<double>::quiet_NaN()),
      lastProspectReferencePoint(prospectTheoryPreferences.referencePoint()) {}

Agent::Agent(uint32_t numericalIdA, AgentEndowment initialEndowment,
             const ProspectTheory& prospectTheory, bool useProspectTheory)
    : numericalId(numericalIdA), initialCash(initialEndowment.cash),
      initialStockByAsset(std::move(initialEndowment.stockByAsset)), cash(initialEndowment.cash),
      stockByAsset(initialStockByAsset), executedTradeCount(0), executedTradeVolume(0.0),
      cumulativeTransactionCostsPaid(0.0), xCoordinate(0.0), yCoordinate(0.0), socialGamma(0.0),
      privateSignalStdDev(0.0), previousOpinionValue(0.0), currentOpinionValue(0.0),
      initialWealth(std::numeric_limits<double>::quiet_NaN()),
      wealth(std::numeric_limits<double>::quiet_NaN()),
      lastValuationPrices(initialStockByAsset.size(), std::numeric_limits<double>::quiet_NaN()),
      prospectTheoryPreferences(prospectTheory), prospectTheoryEnabled(useProspectTheory),
      positionAnchors(initialStockByAsset.size()),
      recentPeakWealth(std::numeric_limits<double>::quiet_NaN()),
      lastProspectReferencePoint(prospectTheoryPreferences.referencePoint()) {
    requireFinite(initialEndowment.cash, "Cash");
    for (const double assetStock : initialStockByAsset) {
        requireFinite(assetStock, "Stock");
    }
}

uint32_t Agent::getNumericalId() const {
    return numericalId;
}

std::size_t Agent::assetCount() const {
    return stockByAsset.size();
}

double Agent::getInitialCash() const {
    return initialCash;
}

double Agent::getInitialStock(std::size_t assetIndex) const {
    return initialStockByAsset.at(assetIndex);
}

double Agent::getInitialWealth() const {
    return initialWealth;
}

double Agent::getCash() const {
    return cash;
}

void Agent::updateCash(double newCash) {
    requireFinite(newCash, "Cash");
    cash = newCash;
    refreshCachedWealth();
}

double Agent::getStock(std::size_t assetIndex) const {
    return stockByAsset.at(assetIndex);
}

void Agent::updateStock(std::size_t assetIndex, double newStock) {
    requireFinite(newStock, "Stock");
    stockByAsset.at(assetIndex) = newStock;
    refreshCachedWealth();
}

void Agent::initializeWealth(const std::vector<double>& marketPrices) {
    if (marketPrices.size() != stockByAsset.size()) {
        throw std::invalid_argument("Valuation price count must match agent asset count.");
    }
    for (const double marketPrice : marketPrices) {
        requireStrictlyPositive(marketPrice, "Market price");
    }

    initialWealth = initialCash;
    for (std::size_t assetIndex = 0; assetIndex < stockByAsset.size(); ++assetIndex) {
        initialWealth += initialStockByAsset[assetIndex] * marketPrices[assetIndex];
    }
    updateWealth(marketPrices);
    initialiseEntryReferencesFromInventory(marketPrices);
}

double Agent::getWealth() const {
    return wealth;
}

void Agent::updateWealth(const std::vector<double>& marketPrices) {
    if (marketPrices.size() != stockByAsset.size()) {
        throw std::invalid_argument("Valuation price count must match agent asset count.");
    }
    for (const double marketPrice : marketPrices) {
        requireStrictlyPositive(marketPrice, "Market price");
    }
    lastValuationPrices = marketPrices;
    refreshCachedWealth();
}

double Agent::getAverageEntryPrice(std::size_t assetIndex) const {
    return positionAnchors.at(assetIndex).averageEntryPrice;
}

int Agent::getPositionDirection(std::size_t assetIndex) const {
    return positionAnchors.at(assetIndex).direction;
}

double Agent::getRecentPeakWealth() const {
    return recentPeakWealth;
}

double Agent::getLastProspectReferencePoint() const {
    return lastProspectReferencePoint;
}

void Agent::setLastProspectReferencePoint(double referencePoint) {
    requireStrictlyPositive(referencePoint, "Prospect reference point");
    lastProspectReferencePoint = referencePoint;
}

std::size_t Agent::getExecutedTradeCount() const {
    return executedTradeCount;
}

double Agent::getExecutedTradeVolume() const {
    return executedTradeVolume;
}

double Agent::getCumulativeTransactionCostsPaid() const {
    return cumulativeTransactionCostsPaid;
}

void Agent::recordTrade(double quantity) {
    requireFinite(quantity, "Trade quantity");
    if (quantity <= 0.0) {
        return;
    }

    ++executedTradeCount;
    executedTradeVolume += quantity;
}

void Agent::recordTransactionCost(double cost) {
    requireFinite(cost, "Transaction cost");
    if (cost <= 0.0) {
        return;
    }

    cumulativeTransactionCostsPaid += cost;
}

void Agent::recordExecutedTrade(std::size_t assetIndex, const ExecutedTrade& trade) {
    requireStrictlyPositive(trade.executionPrice, "Execution price");
    requireFinite(trade.quantity, "Trade quantity");
    if (trade.quantity <= 0.0) {
        return;
    }

    PositionAnchor& anchor = positionAnchors.at(assetIndex);
    const double signedQuantity = trade.side == OrderType::BUY ? trade.quantity : -trade.quantity;
    const double previousStock = stockByAsset.at(assetIndex);
    const double nextStock = previousStock + signedQuantity;
    const int previousDirection = positionSign(previousStock);
    const int nextDirection = positionSign(nextStock);

    if (nextDirection == 0) {
        anchor.averageEntryPrice = std::numeric_limits<double>::quiet_NaN();
        anchor.direction = 0;
    } else if (previousDirection == 0 || previousDirection != nextDirection ||
               !std::isfinite(anchor.averageEntryPrice) ||
               anchor.averageEntryPrice <= kMinimumPrice) {
        anchor.averageEntryPrice = trade.executionPrice;
        anchor.direction = nextDirection;
    } else {
        const double previousAbsolutePosition = std::abs(previousStock);
        const double nextAbsolutePosition = std::abs(nextStock);
        if (nextAbsolutePosition > previousAbsolutePosition + kMinimumOrderQuantity) {
            const double addedQuantity = nextAbsolutePosition - previousAbsolutePosition;
            /*
             * Formula note:
             * P_entry_new = (P_entry_old * |x_old| + P_exec * added_quantity)
             *               / |x_new|.
             *
             * The average entry price updates only when a trade increases
             * exposure in the current position direction.
             */
            anchor.averageEntryPrice = ((anchor.averageEntryPrice * previousAbsolutePosition) +
                                        (trade.executionPrice * addedQuantity)) /
                                       nextAbsolutePosition;
        }
        anchor.direction = nextDirection;
    }

    recordTrade(trade.quantity);
}

void Agent::resetTradeStats() {
    executedTradeCount = 0;
    executedTradeVolume = 0.0;
    cumulativeTransactionCostsPaid = 0.0;
}

bool Agent::usesProspectTheory() const {
    return prospectTheoryEnabled;
}

const ProspectTheory& Agent::prospectTheory() const {
    return prospectTheoryPreferences;
}

void Agent::setSocialProfile(double xCoord, double yCoord, double gamma,
                             double privateSignalStdDevA) {
    requireFinite(xCoord, "Agent x coordinate");
    requireFinite(yCoord, "Agent y coordinate");
    requireFinite(gamma, "Agent social gamma");
    requireFinite(privateSignalStdDevA, "Agent private signal stddev");

    xCoordinate = xCoord;
    yCoordinate = yCoord;
    socialGamma = gamma;
    privateSignalStdDev = privateSignalStdDevA;
}

double Agent::getXCoordinate() const {
    return xCoordinate;
}

double Agent::getYCoordinate() const {
    return yCoordinate;
}

double Agent::getSocialGamma() const {
    return socialGamma;
}

double Agent::getPrivateSignalStdDev() const {
    return privateSignalStdDev;
}

double Agent::getPreviousOpinion() const {
    return previousOpinionValue;
}

double Agent::getCurrentOpinion() const {
    return currentOpinionValue;
}

void Agent::setOpinions(double previousOpinion, double currentOpinion) {
    requireFinite(previousOpinion, "Previous opinion");
    requireFinite(currentOpinion, "Current opinion");
    previousOpinionValue = previousOpinion;
    currentOpinionValue = currentOpinion;
}

Order Agent::generateOrder(OrderType type, double price, double quantity) const {
    requireStrictlyPositive(price, "Order price");
    requireStrictlyPositive(quantity, "Order quantity");

    Order order{};
    order.ownerAgentId = static_cast<int>(numericalId);
    order.type = type;
    order.style = OrderStyle::LIMIT;
    order.price = price;
    order.quantity = quantity;
    order.remainingQuantity = quantity;
    // timeStep and book lifecycle fields are assigned by the simulation layer.
    return order;
}

void Agent::refreshCachedWealth() {
    /*
     * Formula note:
     * W_i,t = c_i,t + sum_j x_i,j,t * P_j,t.
     *
     * Wealth stays undefined until a valid valuation price exists for every
     * asset on the balance sheet.
     */
    double totalWealth = cash;
    for (std::size_t assetIndex = 0; assetIndex < stockByAsset.size(); ++assetIndex) {
        const double valuationPrice = lastValuationPrices[assetIndex];
        if (!(std::isfinite(valuationPrice) && valuationPrice > 0.0)) {
            wealth = std::numeric_limits<double>::quiet_NaN();
            return;
        }
        totalWealth += stockByAsset[assetIndex] * valuationPrice;
    }

    wealth = totalWealth;
    refreshPeakWealth();
}

void Agent::refreshPeakWealth() {
    if (!std::isfinite(wealth) || wealth <= 0.0) {
        return;
    }
    if (!std::isfinite(recentPeakWealth) || wealth > recentPeakWealth) {
        recentPeakWealth = wealth;
    }
}

void Agent::initialiseEntryReferencesFromInventory(const std::vector<double>& marketPrices) {
    for (std::size_t assetIndex = 0; assetIndex < stockByAsset.size(); ++assetIndex) {
        PositionAnchor& anchor = positionAnchors[assetIndex];
        anchor.direction = positionSign(stockByAsset[assetIndex]);
        anchor.averageEntryPrice = anchor.direction == 0 ? std::numeric_limits<double>::quiet_NaN()
                                                         : marketPrices[assetIndex];
    }
}

} // namespace abm
