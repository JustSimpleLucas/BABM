// OutputSerialization.cpp

#include "Output/OutputSerialization.h"

#include "Config/SimulationConfigParsing.h"

#include <filesystem>
#include <iomanip>
#include <sstream>
#include <system_error>

namespace abm::output_detail {

int boolToFlag(bool value) {
    return value ? 1 : 0;
}

const char* orderSideLabel(OrderType side) {
    return side == OrderType::BUY ? "BUY" : "SELL";
}

std::string csvEscape(const std::string& value) {
    const bool requiresQuoting =
        value.find(',') != std::string::npos || value.find('"') != std::string::npos ||
        value.find('\n') != std::string::npos || value.find('\r') != std::string::npos;
    if (!requiresQuoting) {
        return value;
    }

    std::string escaped;
    escaped.reserve(value.size() + 2);
    escaped.push_back('"');
    for (const char c : value) {
        if (c == '"') {
            escaped.push_back('"');
        }
        escaped.push_back(c);
    }
    escaped.push_back('"');
    return escaped;
}

std::string formatFixedDouble(double value, int precision) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(precision) << value;
    return out.str();
}

std::string jsonEscape(const std::string& value) {
    std::string escaped;
    escaped.reserve(value.size());
    for (const unsigned char c : value) {
        switch (c) {
        case '"':
            escaped.push_back('\\');
            escaped.push_back('"');
            break;
        case '\\':
            escaped.push_back('\\');
            escaped.push_back('\\');
            break;
        case '\b':
            escaped += R"(\b)";
            break;
        case '\f':
            escaped += R"(\f)";
            break;
        case '\n':
            escaped += R"(\n)";
            break;
        case '\r':
            escaped += R"(\r)";
            break;
        case '\t':
            escaped += R"(\t)";
            break;
        default:
            if (c < 0x20) {
                std::ostringstream out;
                out << R"(\u)" << std::hex << std::setw(4) << std::setfill('0')
                    << static_cast<int>(c);
                escaped += out.str();
            } else {
                escaped.push_back(static_cast<char>(c));
            }
            break;
        }
    }
    return escaped;
}

std::string jsonBool(bool value) {
    return value ? "true" : "false";
}

/**
 * Writes one asset's generating parameters as a JSON object, without its
 * closing brace so the caller can append a separator.
 *
 * @param out Destination stream.
 * @param asset Asset definition to serialise.
 * @param enabled Enable state to record; disabled assets are serialised from a
 *        separate list, so the flag is supplied rather than read from the
 *        definition to keep the two lists self-describing.
 */
void writeAssetDefinition(std::ostringstream& out, const AssetDefinition& asset, bool enabled) {
    out << "      {\n";
    out << R"(        "name": ")" << jsonEscape(asset.name) << R"(",)" << '\n';
    out << R"(        "enabled": )" << jsonBool(enabled) << ",\n";
    out << R"(        "fundamental_process": ")"
        << jsonEscape(config_parsing::fundamentalProcessTypeName(asset.fundamentalProcess))
        << R"(",)" << '\n';
    out << R"(        "initial_price": )" << asset.initialPrice << ",\n";
    out << R"(        "initial_stock": )" << asset.initialStock << ",\n";
    out << R"(        "price_tick_size": )" << asset.priceTickSize << ",\n";
    out << R"(        "fundamental_shock_std_dev": )" << asset.fundamentalShockStdDev << ",\n";
    out << R"(        "fundamental_drift_per_step": )" << asset.fundamentalDriftPerStep << ",\n";
    out << R"(        "minimum_fundamental_value": )" << asset.minimumFundamentalValue << '\n';
}

std::string buildNormalizedConfigJson(const SimulationConfig& config) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(10);
    out << "{\n";
    out << R"(  "schema_version": 8,)" << '\n';
    out << R"(  "assets": {)" << '\n';
    out << R"(    "primary": ")" << jsonEscape(config.assetName()) << R"(",)" << '\n';
    out << R"(    "covariance_window": )" << config.covarianceWindow << ",\n";
    out << R"(    "fundamental_correlation": )" << config.assetFundamentalCorrelation << ",\n";
    out << R"(    "definitions": [)" << '\n';
    for (std::size_t assetIndex = 0; assetIndex < config.assets.size(); ++assetIndex) {
        writeAssetDefinition(out, config.assets[assetIndex], true);
        out << "      }" << (assetIndex + 1 < config.assets.size() ? "," : "") << '\n';
    }
    out << "    ],\n";
    /*
     * Assets that were declared but switched off are recorded separately so the
     * archive distinguishes a deliberately disabled asset from one that was
     * never configured. They carry no simulation output.
     */
    out << R"(    "disabled_definitions": [)" << '\n';
    for (std::size_t assetIndex = 0; assetIndex < config.assets.disabled().size(); ++assetIndex) {
        writeAssetDefinition(out, config.assets.disabled()[assetIndex], false);
        out << "      }" << (assetIndex + 1 < config.assets.disabled().size() ? "," : "") << '\n';
    }
    out << "    ]\n";
    out << "  },\n";
    out << R"(  "simulation": {)" << '\n';
    out << R"(    "asset_name": ")" << jsonEscape(config.assetName()) << R"(",)" << '\n';
    out << R"(    "time_steps": )" << config.timeSteps << ",\n";
    out << R"(    "warmup_steps": )" << config.warmupSteps << ",\n";
    out << R"(    "num_fundamentalists": )" << config.numFundamentalists << ",\n";
    out << R"(    "num_chartists": )" << config.numChartists << ",\n";
    out << R"(    "num_noise_traders": )" << config.numNoiseTraders << ",\n";
    out << R"(    "num_buy_and_hold_agents": )" << config.numBuyAndHoldAgents << ",\n";
    out << R"(    "initial_price": )" << config.initialPrice() << ",\n";
    out << R"(    "initial_cash": )" << config.initialCash << ",\n";
    out << R"(    "initial_stock": )" << config.initialStock() << ",\n";
    out << R"(    "short_selling_enabled": )" << jsonBool(config.shortSellingEnabled) << ",\n";
    out << R"(    "risk_free_rate": )" << config.riskFreeRate << ",\n";
    out << R"(    "agent_activity_rate": )" << config.agentActivityRate << ",\n";
    out << R"(    "price_tick_size": )" << config.priceTickSize() << ",\n";
    out << R"(    "fundamental_shock_std_dev": )" << config.fundamentalShockStdDev() << ",\n";
    out << R"(    "fundamental_drift_per_step": )" << config.fundamentalDriftPerStep() << ",\n";
    out << R"(    "minimum_fundamental_value": )" << config.minimumFundamentalValue() << ",\n";
    out << R"(    "seed": )" << config.seed << '\n';
    out << "  },\n";
    out << R"(  "warmup_price_process": {)" << '\n';
    out << R"(    "scope": "pre_trading_warmup_only",)" << '\n';
    out << R"(    "noise_std_dev": )" << config.warmupPriceProcess.noiseStdDev << ",\n";
    out << R"(    "fundamental_pull_strength": )"
        << config.warmupPriceProcess.fundamentalPullStrength << '\n';
    out << "  },\n";
    out << R"(  "microstructure": {)" << '\n';
    out << R"(    "mode": ")"
        << config_parsing::marketMicrostructureModeName(config.microstructure.mode) << R"(",)"
        << '\n';
    out << R"(    "order_expiry_steps": )" << config.microstructure.orderExpirySteps << ",\n";
    out << R"(    "cancellation_base_probability": )"
        << config.microstructure.cancellationBaseProbability << ",\n";
    out << R"(    "cancellation_mispricing_sensitivity": )"
        << config.microstructure.cancellationMispricingSensitivity << ",\n";
    out << R"(    "market_order_probability": )" << config.microstructure.marketOrderProbability
        << ",\n";
    out << R"(    "market_order_log_gap_threshold": )"
        << config.microstructure.marketOrderLogGapThreshold << ",\n";
    out << R"(    "market_order_price_collar": )" << config.microstructure.marketOrderPriceCollar
        << ",\n";
    out << R"(    "book_depth_levels": )" << config.microstructure.bookDepthLevels << '\n';
    out << "  },\n";
    out << R"(  "short_sale": {)" << '\n';
    out << R"(    "initial_margin_requirement": )" << config.shortSale.initialMarginRequirement
        << ",\n";
    out << R"(    "maintenance_margin_requirement": )"
        << config.shortSale.maintenanceMarginRequirement << ",\n";
    out << R"(    "borrowable_supply_ratio": )" << config.shortSale.borrowableSupplyRatio << '\n';
    out << "  },\n";
    out << R"(  "transaction_costs": {)" << '\n';
    out << R"(    "rate": )" << config.transactionCosts.rate << ",\n";
    out << R"(    "affects_decisions": )" << jsonBool(config.transactionCosts.affectsDecisions)
        << ",\n";
    out << R"(    "apply_to_forced_buy_ins": )"
        << jsonBool(config.transactionCosts.applyToForcedBuyIns) << '\n';
    out << "  },\n";
    out << R"(  "prospect_theory": {)" << '\n';
    out << R"(    "enabled": )" << jsonBool(config.control.prospectTheoryEnabled) << ",\n";
    out << R"(    "agent_fraction": )" << config.control.prospectTheoryAgentFraction << ",\n";
    out << R"(    "heterogeneity_enabled": )"
        << jsonBool(config.control.prospectParameterHeterogeneityEnabled) << ",\n";
    out << R"(    "loss_aversion": )" << config.control.lossAversion << ",\n";
    out << R"(    "loss_aversion_std_dev": )" << config.control.lossAversionStdDev << ",\n";
    out << R"(    "curvature_for_gain": )" << config.control.curvatureForGain << ",\n";
    out << R"(    "curvature_for_gain_std_dev": )" << config.control.curvatureForGainStdDev
        << ",\n";
    out << R"(    "curvature_for_loss": )" << config.control.curvatureForLoss << ",\n";
    out << R"(    "curvature_for_loss_std_dev": )" << config.control.curvatureForLossStdDev
        << ",\n";
    out << R"(    "prob_distortion_for_gain": )" << config.control.probDistortionForGain << ",\n";
    out << R"(    "prob_distortion_for_loss": )" << config.control.probDistortionForLoss << ",\n";
    out << R"(    "probability_distortion_min": )" << config.control.probabilityDistortionMin
        << ",\n";
    out << R"(    "probability_distortion_max": )" << config.control.probabilityDistortionMax
        << ",\n";
    out << R"(    "reference_point": )" << config.control.referencePoint << ",\n";
    out << R"(    "reference_point_mode": ")"
        << config_parsing::prospectReferencePointModeName(config.control.referencePointMode)
        << R"(",)" << '\n';
    out << R"(    "reference_moving_average_window": )"
        << config.control.referenceMovingAverageWindow << ",\n";
    out << R"(    "scenario_count": )" << config.control.prospectScenarioCount << '\n';
    out << "  },\n";
    out << R"(  "fundamentalist": {)" << '\n';
    out << R"(    "mispricing_threshold": )" << config.fundamentalist.mispricingThreshold << ",\n";
    out << R"(    "stop_loss_threshold": )" << config.fundamentalist.stopLossThreshold << ",\n";
    out << R"(    "take_profit_threshold": )" << config.fundamentalist.takeProfitThreshold << ",\n";
    out << R"(    "volatility_window": )" << config.fundamentalist.volatilityWindow << ",\n";
    out << R"(    "risk_aversion": )" << config.fundamentalist.allocation.riskAversion << ",\n";
    out << R"(    "min_risky_weight": )" << config.fundamentalist.allocation.minRiskyWeight
        << ",\n";
    out << R"(    "max_risky_weight": )" << config.fundamentalist.allocation.maxRiskyWeight << '\n';
    out << "  },\n";
    out << R"(  "chartist": {)" << '\n';
    out << R"(    "short_window": )" << config.chartist.shortWindow << ",\n";
    out << R"(    "long_window": )" << config.chartist.longWindow << ",\n";
    out << R"(    "momentum_signal_threshold": )" << config.chartist.momentumSignalThreshold
        << ",\n";
    out << R"(    "breakout_window": )" << config.chartist.breakoutWindow << ",\n";
    out << R"(    "volatility_window": )" << config.chartist.volatilityWindow << ",\n";
    out << R"(    "max_short_weight": )" << config.chartist.maxShortWeight << ",\n";
    out << R"(    "risk_aversion": )" << config.chartist.allocation.riskAversion << ",\n";
    out << R"(    "min_risky_weight": )" << config.chartist.allocation.minRiskyWeight << ",\n";
    out << R"(    "max_risky_weight": )" << config.chartist.allocation.maxRiskyWeight << ",\n";
    out << R"(    "strategy_mode": ")"
        << jsonEscape(config_parsing::chartistStrategyModeName(config.chartist.strategyMode)) << '"'
        << '\n';
    out << "  },\n";
    out << R"(  "noise_trader": {)" << '\n';
    out << R"(    "belief_shock_std_dev": )" << config.noiseTrader.beliefShockStdDev << ",\n";
    out << R"(    "order_size_fraction": )" << config.noiseTrader.orderSizeFraction << ",\n";
    out << R"(    "max_short_weight": )" << config.noiseTrader.maxShortWeight << '\n';
    out << "  },\n";
    out << R"(  "buy_and_hold": {)" << '\n';
    out << R"(    "target_risky_weight": )" << config.buyAndHold.targetRiskyWeight << '\n';
    out << "  },\n";
    /*
     * The protagonist's block is always written, disabled or not, so the config
     * hash distinguishes a run with an individually parameterised trader from an
     * otherwise identical run without one.
     */
    out << R"(  "protagonist": {)" << '\n';
    out << R"(    "enabled": )" << jsonBool(config.protagonist.enabled) << ",\n";
    out << R"(    "name": ")" << jsonEscape(config.protagonist.name) << R"(",)" << '\n';
    out << R"(    "strategy": ")"
        << jsonEscape(config_parsing::protagonistStrategyKindName(config.protagonist.strategy))
        << R"(",)" << '\n';
    out << R"(    "chartist_rule": ")"
        << jsonEscape(config_parsing::chartistStrategyModeName(config.protagonist.chartistRule))
        << R"(",)" << '\n';
    out << R"(    "initial_cash": )" << config.protagonist.initialCash << ",\n";
    out << R"(    "initial_stock": )" << config.protagonist.initialStock << ",\n";
    out << R"(    "risk_aversion": )" << config.protagonist.allocation.riskAversion << ",\n";
    out << R"(    "min_risky_weight": )" << config.protagonist.allocation.minRiskyWeight << ",\n";
    out << R"(    "max_risky_weight": )" << config.protagonist.allocation.maxRiskyWeight << ",\n";
    out << R"(    "max_gross_exposure": )" << config.protagonist.allocation.maxGrossExposure
        << ",\n";
    out << R"(    "mispricing_threshold": )" << config.protagonist.mispricingThreshold << ",\n";
    out << R"(    "stop_loss_threshold": )" << config.protagonist.stopLossThreshold << ",\n";
    out << R"(    "take_profit_threshold": )" << config.protagonist.takeProfitThreshold << ",\n";
    out << R"(    "volatility_window": )" << config.protagonist.volatilityWindow << ",\n";
    out << R"(    "short_window": )" << config.protagonist.shortWindow << ",\n";
    out << R"(    "long_window": )" << config.protagonist.longWindow << ",\n";
    out << R"(    "momentum_signal_threshold": )" << config.protagonist.momentumSignalThreshold
        << ",\n";
    out << R"(    "breakout_window": )" << config.protagonist.breakoutWindow << ",\n";
    out << R"(    "max_short_weight": )" << config.protagonist.maxShortWeight << ",\n";
    out << R"(    "noise_belief_shock_std_dev": )" << config.protagonist.noiseBeliefShockStdDev
        << ",\n";
    out << R"(    "noise_order_size_fraction": )" << config.protagonist.noiseOrderSizeFraction
        << ",\n";
    out << R"(    "buy_hold_target_risky_weight": )" << config.protagonist.buyHoldTargetRiskyWeight
        << ",\n";
    out << R"(    "prospect_theory_enabled": )"
        << jsonBool(config.protagonist.prospectTheoryEnabled) << ",\n";
    out << R"(    "loss_aversion": )" << config.protagonist.lossAversion << ",\n";
    out << R"(    "curvature_for_gain": )" << config.protagonist.curvatureForGain << ",\n";
    out << R"(    "curvature_for_loss": )" << config.protagonist.curvatureForLoss << ",\n";
    out << R"(    "prob_distortion_for_gain": )" << config.protagonist.probDistortionForGain
        << ",\n";
    out << R"(    "prob_distortion_for_loss": )" << config.protagonist.probDistortionForLoss
        << '\n';
    out << "  },\n";
    out << R"(  "social_influence": {)" << '\n';
    out << R"(    "enabled": )" << jsonBool(config.social.enabled) << ",\n";
    out << R"(    "space_width": )" << config.social.spaceWidth << ",\n";
    out << R"(    "space_height": )" << config.social.spaceHeight << ",\n";
    out << R"(    "interaction_radius": )" << config.social.interactionRadius << ",\n";
    out << R"(    "opinion_kappa": )" << config.social.opinionKappa << ",\n";
    out << R"(    "hold_tolerance": )" << config.social.holdTolerance << ",\n";
    out << R"(    "gamma_min": )" << config.social.gammaMin << ",\n";
    out << R"(    "gamma_max": )" << config.social.gammaMax << ",\n";
    out << R"(    "private_signal_std_min": )" << config.social.privateSignalStdMin << ",\n";
    out << R"(    "private_signal_std_max": )" << config.social.privateSignalStdMax << '\n';
    out << "  }\n";
    out << "}\n";
    return out.str();
}

std::string stableConfigHash(const std::string& normalizedConfigJson) {
    /*
     * FNV-1a is not cryptographic. It is used here only as a stable, compact
     * identifier for grouping reruns with identical resolved parameters.
     */
    std::uint64_t hash = 14695981039346656037ULL;
    for (const unsigned char c : normalizedConfigJson) {
        hash ^= static_cast<std::uint64_t>(c);
        hash *= 1099511628211ULL;
    }

    std::ostringstream out;
    out << std::hex << std::setw(16) << std::setfill('0') << hash;
    return out.str();
}

bool ensureParentDirectoryExists(const std::string& outputPath, std::string& error) {
    const std::filesystem::path outPath(outputPath);
    const std::filesystem::path parent = outPath.parent_path();
    if (parent.empty()) {
        return true;
    }

    std::error_code ec;
    std::filesystem::create_directories(parent, ec);
    if (ec) {
        error = "Unable to create output directory: " + parent.string() + " (" + ec.message() + ")";
        return false;
    }

    return true;
}

} // namespace abm::output_detail
