// Market.cpp
#include "Market/Market.h"
#include "Utility/NumericValidation.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <iterator>
#include <stdexcept>
#include <string>
#include <utility>

namespace abm {

void Market::configureAssets(std::vector<std::string> assetNames) {
    if (assetNames.empty()) {
        throw std::invalid_argument("A market requires at least one asset.");
    }
    for (std::size_t assetIndex = 0; assetIndex < assetNames.size(); ++assetIndex) {
        for (std::size_t otherIndex = assetIndex + 1; otherIndex < assetNames.size();
             ++otherIndex) {
            if (assetNames[assetIndex] == assetNames[otherIndex]) {
                throw std::invalid_argument("Duplicate asset name in market configuration: " +
                                            assetNames[assetIndex]);
            }
        }
    }
    assetNames_ = std::move(assetNames);
    series_.assign(assetNames_.size(), AssetPriceSeries{});
}

std::size_t Market::assetCount() const {
    return series_.size();
}

std::string Market::assetLabel(std::size_t assetIndex) const {
    if (assetIndex < assetNames_.size()) {
        return "'" + assetNames_[assetIndex] + "' (index " + std::to_string(assetIndex) + ")";
    }
    return "index " + std::to_string(assetIndex);
}

const AssetPriceSeries& Market::seriesAt(std::size_t assetIndex) const {
    if (assetIndex >= series_.size()) {
        throw std::out_of_range("No configured market series for asset " + assetLabel(assetIndex) +
                                "; the market carries " + std::to_string(series_.size()) +
                                " asset(s).");
    }
    return series_[assetIndex];
}

AssetPriceSeries& Market::seriesAt(std::size_t assetIndex) {
    return const_cast<AssetPriceSeries&>(std::as_const(*this).seriesAt(assetIndex));
}

void Market::storeMarketValue(std::size_t assetIndex, double value) {
    requireFinite(value, "Market value");
    seriesAt(assetIndex).marketValues.push_back(value);
}

void Market::storeTrueValue(std::size_t assetIndex, double value) {
    requireFinite(value, "Fundamental value");
    seriesAt(assetIndex).trueValues.push_back(value);
}

const std::vector<double>& Market::getMarketValues(std::size_t assetIndex) const {
    return seriesAt(assetIndex).marketValues;
}

const std::vector<double>& Market::getTrueValues(std::size_t assetIndex) const {
    return seriesAt(assetIndex).trueValues;
}

double Market::calculateMovingAverage(std::size_t assetIndex, std::size_t window) const {
    requirePositiveSize(window, "Moving average window");

    const auto& values = getMarketValues(assetIndex);
    if (values.size() < window) {
        throw std::invalid_argument(
            "Insufficient market values to calculate moving average for asset " +
            assetLabel(assetIndex) + '.');
    }

    const auto windowBegin = std::prev(values.cend(), static_cast<std::ptrdiff_t>(window));
    double sum = 0.0;
    for (auto valueIt = windowBegin; valueIt != values.cend(); ++valueIt) {
        sum += *valueIt;
    }

    /*
     * Formula note:
     * MA_t(h) = (1 / h) * sum_{k=0}^{h-1} P_{t-k}.
     */
    return sum / static_cast<double>(window);
}

double Market::calculateStandardDeviation(std::size_t assetIndex, std::size_t window) const {
    requirePositiveSize(window, "Standard deviation window");

    const auto& values = getMarketValues(assetIndex);
    if (values.size() < window) {
        throw std::invalid_argument(
            "Insufficient market values to calculate standard deviation for asset " +
            assetLabel(assetIndex) + '.');
    }

    const auto windowBegin = std::prev(values.cend(), static_cast<std::ptrdiff_t>(window));
    const double mean = calculateMovingAverage(assetIndex, window);

    double squaredDiffSum = 0.0;
    for (auto valueIt = windowBegin; valueIt != values.cend(); ++valueIt) {
        const double diff = *valueIt - mean;
        squaredDiffSum += diff * diff;
    }

    /*
     * Formula note:
     * sigma_P(h) = sqrt((1 / h) * sum_{k=0}^{h-1} (P_{t-k} - MA_t(h))^2).
     */
    const double variance = squaredDiffSum / static_cast<double>(window);
    return std::sqrt(variance);
}

double Market::calculateLogReturnStandardDeviation(std::size_t assetIndex,
                                                   std::size_t window) const {
    requirePositiveSize(window, "Log-return standard deviation window");

    const auto& values = getMarketValues(assetIndex);
    if (values.size() <= window) {
        throw std::invalid_argument(
            "Insufficient market values to calculate log-return standard deviation for asset " +
            assetLabel(assetIndex) + '.');
    }

    auto currentIt = std::prev(values.cend(), static_cast<std::ptrdiff_t>(window));
    auto previousIt = std::prev(currentIt);
    std::vector<double> logReturns;
    logReturns.reserve(window);
    double logReturnSum = 0.0;
    for (; currentIt != values.cend(); ++currentIt, ++previousIt) {
        const double previousPrice = *previousIt;
        const double currentPrice = *currentIt;
        if (previousPrice <= 0.0 || currentPrice <= 0.0) {
            throw std::invalid_argument(
                "Log-return standard deviation requires strictly positive market prices.");
        }
        /*
         * Formula note:
         * r_tau = log(P_tau / P_{tau-1}).
         */
        const double logReturn = std::log(currentPrice / previousPrice);
        logReturns.push_back(logReturn);
        logReturnSum += logReturn;
    }

    const double meanLogReturn = logReturnSum / static_cast<double>(window);

    double squaredDiffSum = 0.0;
    for (const double logReturn : logReturns) {
        const double diff = logReturn - meanLogReturn;
        squaredDiffSum += diff * diff;
    }

    /*
     * Formula note:
     * sigma_r(h) = sqrt((1 / h) * sum_tau (r_tau - mean_r)^2).
     *
     * This realised-volatility estimate is used by the portfolio-allocation
     * rules, so it is intentionally computed on log returns rather than prices.
     */
    const double variance = squaredDiffSum / static_cast<double>(window);
    return std::sqrt(variance);
}

double Market::calculateRSI(std::size_t assetIndex, std::size_t period) const {
    requirePositiveSize(period, "RSI period");

    const auto& values = getMarketValues(assetIndex);
    if (values.size() <= period) {
        throw std::invalid_argument("Insufficient market values to calculate RSI for asset " +
                                    assetLabel(assetIndex) + '.');
    }

    auto currentIt = std::prev(values.cend(), static_cast<std::ptrdiff_t>(period));
    auto previousIt = std::prev(currentIt);
    double gains = 0.0;
    double losses = 0.0;

    for (; currentIt != values.cend(); ++currentIt, ++previousIt) {
        const double delta = *currentIt - *previousIt;
        if (delta > 0.0) {
            gains += delta;
        } else {
            losses -= delta;
        }
    }

    const double avgGain = gains / static_cast<double>(period);
    const double avgLoss = losses / static_cast<double>(period);

    if (avgLoss == 0.0) {
        return 100.0;
    }
    if (avgGain == 0.0) {
        return 0.0;
    }

    const double rs = avgGain / avgLoss;
    /*
     * Formula note:
     * RS = average_gain / average_loss,
     * RSI = 100 - 100 / (1 + RS).
     */
    return 100.0 - (100.0 / (1.0 + rs));
}

} // namespace abm
