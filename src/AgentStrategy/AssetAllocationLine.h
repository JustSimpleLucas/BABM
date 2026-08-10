// AssetAllocationLine.h
#ifndef ABM_AGENT_STRATEGY_ASSET_ALLOCATION_LINE_H
#define ABM_AGENT_STRATEGY_ASSET_ALLOCATION_LINE_H

namespace abm {

/**
 * Mean-variance allocation line used by trading strategies.
 *
 * Given expected return, risk-free rate, and volatility, the class computes a
 * bounded risky-asset demand. Keeping this rule separate from signal formation
 * makes it clear which part of the model is behavioural belief formation and
 * which part is portfolio sizing.
 */
class AssetAllocationLine {
  public:
    /** Constructs the default allocation rule used by config defaults. */
    AssetAllocationLine();

    /**
     * Constructs an allocation rule with explicit risk aversion and bounds.
     *
     * @param riskAversion Positive coefficient of risk aversion.
     * @param minRiskyWeight Lower risky-asset portfolio weight.
     * @param maxRiskyWeight Upper risky-asset portfolio weight.
     */
    AssetAllocationLine(double riskAversion, double minRiskyWeight, double maxRiskyWeight);

    /** Updates the risk-aversion coefficient. */
    void setRiskyAversion(double aversion);

    /** Updates lower and upper risky-weight constraints. */
    void setRiskyWeightBounds(double minRiskyWeight, double maxRiskyWeight);

    /** Returns the coefficient of risk aversion. */
    [[nodiscard]] double riskAversion() const;

    /** Returns the lower risky-asset portfolio weight. */
    [[nodiscard]] double minRiskyWeight() const;

    /** Returns the upper risky-asset portfolio weight. */
    [[nodiscard]] double maxRiskyWeight() const;

    /** Returns the bounded risky-asset weight implied by mean-variance demand. */
    [[nodiscard]] double optimalRiskyWeight(double mu, double rf, double sigma) const;

  private:
    double riskAversion_;
    double minRiskyWeight_;
    double maxRiskyWeight_;
};

} // namespace abm

#endif // ABM_AGENT_STRATEGY_ASSET_ALLOCATION_LINE_H
