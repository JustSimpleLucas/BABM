// Agent.h

#ifndef ABM_AGENT_AGENT_H
#define ABM_AGENT_AGENT_H

#include "BehaviouralFinance/ProspectTheory.h"
#include "OrderBook/Order.h"
#include <cstddef>
#include <limits>
#include <vector>

namespace abm {

/**
 * Initial resources assigned to one agent at population creation.
 *
 * Grouping the endowment avoids long constructor argument lists where cash and
 * inventory can be accidentally swapped. Both values are model-state quantities
 * rather than calibration parameters.
 *
 * Inventory is per-asset only. A scalar `stock` field used to sit alongside the
 * vector and win whenever the vector was empty, which meant an endowment had
 * two spellings and a silent precedence rule between them; a single-asset
 * endowment is now written `{cash, {stock}}`.
 */
struct AgentEndowment {
    double cash{0.0};
    std::vector<double> stockByAsset{};
};

/**
 * Agent-level view of an executed trade.
 *
 * The clearing engine records the side from this agent's perspective, the
 * realised transaction price, and the filled quantity. Keeping the two double
 * quantities in a named record makes execution accounting explicit.
 */
struct ExecutedTrade {
    OrderType side{OrderType::BUY};
    double executionPrice{0.0};
    double quantity{0.0};
};

/**
 * Per-asset position reference used by behavioural risk rules.
 *
 * The average entry price anchors stop-loss, take-profit, and CPT reference
 * points; the direction distinguishes long, short, and flat inventory.
 */
struct PositionAnchor {
    double averageEntryPrice{std::numeric_limits<double>::quiet_NaN()};
    int direction{0};
};

/**
 * Persistent state for one heterogeneous market participant.
 *
 * The class owns accounting state that is common to all behavioural strategies:
 * cash, per-asset inventory, wealth, social coordinates, trade statistics, and
 * agent-specific behavioural preferences. Trading strategies decide when to
 * trade; this class preserves the investor identity and state that must remain
 * stable if strategy-switching rules are introduced later.
 *
 * Inventory, valuation prices, and position anchors are indexed by asset in
 * the deterministic AssetUniverse order. The balance sheet is addressed by
 * index only: there are deliberately no scalar accessors defaulting to asset
 * zero, because a call site that means "asset zero" should say so rather than
 * read as if the agent held a single position.
 */
class Agent {
  private:
    uint32_t numericalId;
    double initialCash;
    std::vector<double> initialStockByAsset;
    double cash;
    std::vector<double> stockByAsset;
    std::size_t executedTradeCount;
    double executedTradeVolume;
    double cumulativeTransactionCostsPaid;
    double xCoordinate;
    double yCoordinate;
    double socialGamma;
    double privateSignalStdDev;
    double previousOpinionValue;
    double currentOpinionValue;
    double initialWealth;
    double wealth;
    std::vector<double> lastValuationPrices;
    ProspectTheory prospectTheoryPreferences;
    bool prospectTheoryEnabled;
    std::vector<PositionAnchor> positionAnchors;
    double recentPeakWealth;
    double lastProspectReferencePoint;

  public:
    /** Constructs an empty agent used by default-initialised containers/tests. */
    Agent();

    /**
     * Constructs an agent with deterministic identity and initial endowment.
     *
     * @param numericalId Stable agent identifier used in orders and CSV outputs.
     * @param initialEndowment Initial cash and asset inventory.
     * @param prospectTheory Agent-specific behavioural preference parameters.
     * @param useProspectTheory Enables behavioural valuation when true.
     */
    Agent(std::uint32_t numericalId, AgentEndowment initialEndowment,
          const ProspectTheory& prospectTheory = ProspectTheory{}, bool useProspectTheory = true);

    /** Returns the stable agent identifier. */
    [[nodiscard]] uint32_t getNumericalId() const;

    /** Returns the number of assets tracked by this agent's balance sheet. */
    [[nodiscard]] std::size_t assetCount() const;

    /** Returns the cash endowment recorded at model initialisation. */
    [[nodiscard]] double getInitialCash() const;

    /** Returns the stock endowment of the given asset recorded at initialisation. */
    [[nodiscard]] double getInitialStock(std::size_t assetIndex) const;

    /** Returns initial mark-to-market wealth after the first valuation price is known. */
    [[nodiscard]] double getInitialWealth() const;

    /** Returns current cash. */
    [[nodiscard]] double getCash() const;

    /** Updates current cash and refreshes cached wealth when valuation prices exist. */
    void updateCash(double newCash);

    /** Returns current inventory of the given asset. */
    [[nodiscard]] double getStock(std::size_t assetIndex) const;

    /** Updates the given asset's inventory and refreshes cached wealth when prices exist. */
    void updateStock(std::size_t assetIndex, double newStock);

    /** Sets initial wealth using one current market valuation per asset. */
    void initializeWealth(const std::vector<double>& marketPrices);

    /** Returns the latest cached mark-to-market wealth. */
    [[nodiscard]] double getWealth() const;

    /** Refreshes wealth with one latest market price per asset. */
    void updateWealth(const std::vector<double>& marketPrices);

    /** Returns the average execution price of the current position in the given asset. */
    [[nodiscard]] double getAverageEntryPrice(std::size_t assetIndex) const;

    /** Returns 1 for long, -1 for short, and 0 for flat inventory in the given asset. */
    [[nodiscard]] int getPositionDirection(std::size_t assetIndex) const;

    /** Returns the highest positive mark-to-market wealth observed for this agent. */
    [[nodiscard]] double getRecentPeakWealth() const;

    /** Returns the last CPT reference point resolved by a trading strategy. */
    [[nodiscard]] double getLastProspectReferencePoint() const;

    /** Stores the CPT reference point used for the latest behavioural valuation. */
    void setLastProspectReferencePoint(double referencePoint);

    /** Returns the number of executed trades involving this agent. */
    [[nodiscard]] std::size_t getExecutedTradeCount() const;

    /** Returns cumulative executed quantity involving this agent. */
    [[nodiscard]] double getExecutedTradeVolume() const;

    /** Returns cumulative proportional transaction costs paid by this agent. */
    [[nodiscard]] double getCumulativeTransactionCostsPaid() const;

    /** Records an executed trade for agent-level diagnostics. */
    void recordTrade(double quantity);

    /** Records a positive transaction cost paid by this agent. */
    void recordTransactionCost(double cost);

    /**
     * Records an executed trade in the given asset and updates its position
     * reference.
     *
     * The update is based on the current inventory before the accounting
     * mutation is applied. This keeps average-entry anchors tied to realised
     * executions rather than to submitted orders.
     */
    void recordExecutedTrade(std::size_t assetIndex, const ExecutedTrade& trade);

    /** Resets trade counters before a fresh simulation run. */
    void resetTradeStats();

    /** Returns true when this agent applies Prospect Theory valuation. */
    [[nodiscard]] bool usesProspectTheory() const;

    /** Returns the persistent agent-specific Prospect Theory parameters. */
    [[nodiscard]] const ProspectTheory& prospectTheory() const;

    /**
     * Stores spatial-social profile parameters.
     *
     * @param xCoord Horizontal coordinate in the synthetic social space.
     * @param yCoord Vertical coordinate in the synthetic social space.
     * @param gamma Weight assigned to neighbour opinion relative to private signal.
     * @param privateSignalStdDev Standard deviation of idiosyncratic opinion noise.
     */
    void setSocialProfile(double xCoord, double yCoord, double gamma, double privateSignalStdDev);

    /** Returns horizontal coordinate in social space. */
    [[nodiscard]] double getXCoordinate() const;

    /** Returns vertical coordinate in social space. */
    [[nodiscard]] double getYCoordinate() const;

    /** Returns social-opinion weight gamma. */
    [[nodiscard]] double getSocialGamma() const;

    /** Returns private opinion noise standard deviation. */
    [[nodiscard]] double getPrivateSignalStdDev() const;

    /** Returns previous-step opinion used in neighbour averaging. */
    [[nodiscard]] double getPreviousOpinion() const;

    /** Returns current-step opinion used for quote formation. */
    [[nodiscard]] double getCurrentOpinion() const;

    /** Updates lagged and current opinion values. */
    void setOpinions(double previousOpinion, double currentOpinion);

    /**
     * Creates a validated limit order owned by this agent.
     *
     * The simulation layer later assigns the order identifier, scheduling
     * context such as the current time step, and checks cash/inventory
     * feasibility before execution.
     */
    [[nodiscard]] Order generateOrder(OrderType type, double price, double quantity) const;

  private:
    void refreshCachedWealth();
    void refreshPeakWealth();
    void initialiseEntryReferencesFromInventory(const std::vector<double>& marketPrices);
};

} // namespace abm

#endif // ABM_AGENT_AGENT_H
