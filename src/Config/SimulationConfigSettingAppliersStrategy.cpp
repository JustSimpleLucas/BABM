// SimulationConfigSettingAppliersStrategy.cpp

#include "Config/SimulationConfigSettingAppliers.h"

namespace abm::config_io_detail {

bool applyFundamentalistSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    FundamentalistConfig& fundamentalist = config.simulation.fundamentalist;

    if (key == "fundamentalist_mispricing_threshold") {
        fundamentalist.mispricingThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "fundamentalist_stop_loss_threshold") {
        fundamentalist.stopLossThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "fundamentalist_take_profit_threshold") {
        fundamentalist.takeProfitThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "fundamentalist_volatility_window") {
        fundamentalist.volatilityWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "fundamentalist_risk_aversion") {
        fundamentalist.allocation.riskAversion = parseDoubleValue(setting);
        return true;
    }
    if (key == "fundamentalist_min_risky_weight") {
        fundamentalist.allocation.minRiskyWeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "fundamentalist_max_risky_weight") {
        fundamentalist.allocation.maxRiskyWeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "fundamentalist_max_gross_exposure") {
        fundamentalist.allocation.maxGrossExposure = parseDoubleValue(setting);
        return true;
    }

    return false;
}

bool applyChartistSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    ChartistConfig& chartist = config.simulation.chartist;

    if (key == "chartist_short_window") {
        chartist.shortWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "chartist_long_window") {
        chartist.longWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "chartist_momentum_signal_threshold") {
        chartist.momentumSignalThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "chartist_breakout_window") {
        chartist.breakoutWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "chartist_volatility_window") {
        chartist.volatilityWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "chartist_max_short_weight") {
        chartist.maxShortWeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "chartist_risk_aversion") {
        chartist.allocation.riskAversion = parseDoubleValue(setting);
        return true;
    }
    if (key == "chartist_min_risky_weight") {
        chartist.allocation.minRiskyWeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "chartist_max_risky_weight") {
        chartist.allocation.maxRiskyWeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "chartist_max_gross_exposure") {
        chartist.allocation.maxGrossExposure = parseDoubleValue(setting);
        return true;
    }
    if (key == "chartist_strategy_mode") {
        chartist.strategyMode = config_parsing::parseChartistStrategyMode(
            setting.value, setting.path, setting.lineNumber);
        return true;
    }

    return false;
}

bool applyNoiseTraderSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    NoiseTraderConfig& noiseTrader = config.simulation.noiseTrader;

    if (key == "noise_trader_belief_shock_std_dev") {
        noiseTrader.beliefShockStdDev = parseDoubleValue(setting);
        return true;
    }
    if (key == "noise_trader_order_size_fraction") {
        noiseTrader.orderSizeFraction = parseDoubleValue(setting);
        return true;
    }
    if (key == "noise_trader_max_short_weight") {
        noiseTrader.maxShortWeight = parseDoubleValue(setting);
        return true;
    }

    return false;
}

bool applyBuyAndHoldSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    BuyAndHoldConfig& buyAndHold = config.simulation.buyAndHold;

    if (key == "buy_hold_target_risky_weight") {
        buyAndHold.targetRiskyWeight = parseDoubleValue(setting);
        return true;
    }

    return false;
}

bool applySocialSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    SocialInfluenceConfig& social = config.simulation.social;

    if (key == "social_enabled") {
        social.enabled = parseBoolValue(setting);
        return true;
    }
    if (key == "social_space_width") {
        social.spaceWidth = parseDoubleValue(setting);
        return true;
    }
    if (key == "social_space_height") {
        social.spaceHeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "social_interaction_radius") {
        social.interactionRadius = parseDoubleValue(setting);
        return true;
    }
    if (key == "social_opinion_kappa") {
        social.opinionKappa = parseDoubleValue(setting);
        return true;
    }
    if (key == "social_hold_tolerance") {
        social.holdTolerance = parseDoubleValue(setting);
        return true;
    }
    if (key == "social_gamma_min") {
        social.gammaMin = parseDoubleValue(setting);
        return true;
    }
    if (key == "social_gamma_max") {
        social.gammaMax = parseDoubleValue(setting);
        return true;
    }
    if (key == "social_private_signal_std_min") {
        social.privateSignalStdMin = parseDoubleValue(setting);
        return true;
    }
    if (key == "social_private_signal_std_max") {
        social.privateSignalStdMax = parseDoubleValue(setting);
        return true;
    }

    return false;
}

} // namespace abm::config_io_detail
