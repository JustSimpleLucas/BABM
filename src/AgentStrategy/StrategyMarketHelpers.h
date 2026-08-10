// StrategyMarketHelpers.h

#ifndef ABM_AGENT_STRATEGY_STRATEGY_MARKET_HELPERS_H
#define ABM_AGENT_STRATEGY_STRATEGY_MARKET_HELPERS_H

#include "Agent/Agent.h"
#include "ControlParameters/SimulationConfig.h"
#include "Market/Market.h"
#include "Utility/SimulationConstants.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>

namespace abm::strategy_detail {

/**
 * Returns a relative difference while protecting strategies from a near-zero
 * denominator. This is a numerical guard, not an economic assumption.
 */
[[nodiscard]] inline double safeRelativeDifference(double lhs, double rhs) {
    if (std::abs(rhs) < kMinimumPrice) {
        return 0.0;
    }

    /*
     * Formula note:
     * relative_difference(lhs, rhs) = (lhs - rhs) / rhs.
     */
    return (lhs - rhs) / rhs;
}

/**
 * Returns log(numerator / denominator), or zero when either side is too close
 * to zero for a meaningful ratio. This is a numerical guard, not an economic
 * assumption.
 */
[[nodiscard]] inline double safeLogRatio(double numerator, double denominator) {
    if (!(numerator > kMinimumPrice) || !(denominator > kMinimumPrice)) {
        return 0.0;
    }
    return std::log(numerator / denominator);
}

/**
 * Returns the latest observed market price for an asset.
 *
 * Trading strategies require a strictly usable price because the value enters
 * wealth, position sizing, and log-price calculations.
 */
[[nodiscard]] inline double latestPositiveMarketPrice(const Market& market,
                                                      std::size_t assetIndex) {
    const auto& values = market.getMarketValues(assetIndex);
    if (values.empty()) {
        throw std::invalid_argument("No market values for asset index " +
                                    std::to_string(assetIndex) + '.');
    }

    const double latest = values.back();
    if (!std::isfinite(latest) || latest < kMinimumPrice) {
        throw std::invalid_argument(
            "Latest market price must be finite and at least the minimum price.");
    }
    return latest;
}

/**
 * Returns the latest latent fundamental value for an asset.
 *
 * Fundamental values may be model-implied rather than directly tradable, so
 * the strategy only requires finiteness here; economic admissibility is handled
 * by the market-generation and configuration layers.
 */
[[nodiscard]] inline double latestFiniteFundamentalPrice(const Market& market,
                                                         std::size_t assetIndex) {
    const auto& values = market.getTrueValues(assetIndex);
    if (values.empty()) {
        throw std::invalid_argument("No true values for asset index " + std::to_string(assetIndex) +
                                    '.');
    }

    const double latest = values.back();
    if (!std::isfinite(latest)) {
        throw std::invalid_argument("Latest true value must be finite.");
    }
    return latest;
}

/**
 * Returns a finite realised-volatility estimate bounded away from zero.
 *
 * Mean-variance position sizing divides by volatility, so a shared lower bound
 * keeps chartist and fundamentalist strategies numerically comparable.
 */
[[nodiscard]] inline double boundedLogReturnVolatility(const Market& market, std::size_t assetIndex,
                                                       std::size_t volatilityWindow) {
    const double logReturnVolatility =
        market.calculateLogReturnStandardDeviation(assetIndex, volatilityWindow);

    if (!std::isfinite(logReturnVolatility)) {
        return kMinimumVolatility;
    }

    return std::max(logReturnVolatility, kMinimumVolatility);
}

/** Returns the fixed CPT reference point, falling back to the latest price if needed. */
[[nodiscard]] inline double configuredProspectReferencePoint(const Agent& agent,
                                                             double latestMarketPrice) {
    const double configuredReference = agent.prospectTheory().referencePoint();
    if (std::isfinite(configuredReference) && configuredReference > kMinimumPrice) {
        return configuredReference;
    }
    return latestMarketPrice;
}

/**
 * Resolves the reference point used by Cumulative Prospect Theory valuation.
 *
 * Formula note:
 * nu_i,t is selected from the configured anchor, average entry price, recent
 * peak wealth, moving-average price, or initial wealth depending on the
 * experiment configuration.
 *
 * The function records the selected value on the agent so final outputs can
 * audit which personal anchor was active at the last behavioural decision.
 */
[[nodiscard]] inline double resolveProspectReferencePoint(Agent& agent, const Market& market,
                                                          std::size_t assetIndex,
                                                          ProspectReferencePointMode mode,
                                                          std::size_t movingAverageWindow,
                                                          double latestMarketPrice) {
    const double fallbackReference = configuredProspectReferencePoint(agent, latestMarketPrice);
    double resolvedReference = fallbackReference;

    switch (mode) {
    case ProspectReferencePointMode::Configured:
        resolvedReference = fallbackReference;
        break;
    case ProspectReferencePointMode::AveragePurchasePrice:
        /*
         * The anchor is this asset's own average entry price. Reading asset
         * zero's here would price a gain or loss in one market against the
         * entry level of another, and would disagree with the stop-loss and
         * take-profit rules, which are evaluated per asset for the same
         * decision.
         */
        if (std::isfinite(agent.getAverageEntryPrice(assetIndex)) &&
            agent.getAverageEntryPrice(assetIndex) > kMinimumPrice) {
            resolvedReference = agent.getAverageEntryPrice(assetIndex);
        }
        break;
    case ProspectReferencePointMode::RecentPeakWealth:
        if (std::isfinite(agent.getRecentPeakWealth()) &&
            agent.getRecentPeakWealth() > kMinimumPrice) {
            resolvedReference = agent.getRecentPeakWealth();
        }
        break;
    case ProspectReferencePointMode::MovingAveragePrice: {
        const auto& marketValues = market.getMarketValues(assetIndex);
        if (movingAverageWindow > 0 && marketValues.size() >= movingAverageWindow) {
            const double movingAverage =
                market.calculateMovingAverage(assetIndex, movingAverageWindow);
            if (std::isfinite(movingAverage) && movingAverage > kMinimumPrice) {
                resolvedReference = movingAverage;
            } else {
                resolvedReference = latestMarketPrice;
            }
        } else {
            resolvedReference = latestMarketPrice;
        }
        break;
    }
    case ProspectReferencePointMode::InitialWealth:
        if (std::isfinite(agent.getInitialWealth()) && agent.getInitialWealth() > kMinimumPrice) {
            resolvedReference = agent.getInitialWealth();
        }
        break;
    }

    if (!std::isfinite(resolvedReference) || resolvedReference <= kMinimumPrice) {
        resolvedReference = fallbackReference;
    }
    agent.setLastProspectReferencePoint(resolvedReference);
    return resolvedReference;
}

/** Widest reference log return accepted by the CPT scenario ladder. */
inline constexpr double kMaximumReferenceLogReturn = 0.95;

/**
 * Resolves the CPT reference point and maps it into return space.
 *
 * Price-anchored modes (configured, average purchase price, moving-average
 * price) return clamp(log(anchor / P_t), +/-0.95); wealth-anchored modes
 * (recent peak wealth, initial wealth) return clamp(log(anchor / W_t),
 * +/-0.95). Working in return space keeps behavioural risk appetite invariant
 * to price and wealth levels, which matters once assets trade at different
 * price scales. The raw anchor is still recorded on the agent for the
 * agents_final audit column.
 */
[[nodiscard]] inline double resolveProspectReferenceReturn(Agent& agent, const Market& market,
                                                           std::size_t assetIndex,
                                                           ProspectReferencePointMode mode,
                                                           std::size_t movingAverageWindow,
                                                           double latestMarketPrice) {
    const double anchor = resolveProspectReferencePoint(agent, market, assetIndex, mode,
                                                        movingAverageWindow, latestMarketPrice);
    const bool wealthAnchored = mode == ProspectReferencePointMode::RecentPeakWealth ||
                                mode == ProspectReferencePointMode::InitialWealth;
    const double base = wealthAnchored ? agent.getWealth() : latestMarketPrice;
    if (!(std::isfinite(base) && base > kMinimumPrice)) {
        return 0.0;
    }
    return std::clamp(std::log(anchor / base), -kMaximumReferenceLogReturn,
                      kMaximumReferenceLogReturn);
}

} // namespace abm::strategy_detail

#endif // ABM_AGENT_STRATEGY_STRATEGY_MARKET_HELPERS_H
