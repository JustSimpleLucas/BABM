// SimulationConfigSettingAppliersProtagonist.cpp

#include "Config/SimulationConfigSettingAppliers.h"

namespace abm::config_io_detail {

/*
 * The protagonist's keys are grouped in their own translation unit rather than
 * folded into the strategy appliers, because they describe one identified
 * individual rather than a strategy population. Reading this file tells you the
 * complete set of things that can be said about him.
 */
bool applyProtagonistSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    ProtagonistConfig& protagonist = config.simulation.protagonist;

    if (key == "protagonist_enabled") {
        protagonist.enabled = parseBoolValue(setting);
        return true;
    }
    if (key == "protagonist_name") {
        protagonist.name = config_parsing::parseString(setting.value);
        return true;
    }
    if (key == "protagonist_strategy") {
        protagonist.strategy = config_parsing::parseProtagonistStrategyKind(
            setting.value, setting.path, setting.lineNumber);
        return true;
    }
    if (key == "protagonist_chartist_rule") {
        protagonist.chartistRule = config_parsing::parseProtagonistChartistRule(
            setting.value, setting.path, setting.lineNumber);
        return true;
    }

    // --- Endowment ----------------------------------------------------------
    if (key == "protagonist_initial_cash") {
        protagonist.initialCash = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_initial_stock") {
        protagonist.initialStock = parseDoubleValue(setting);
        return true;
    }

    // --- Allocation and risk ------------------------------------------------
    if (key == "protagonist_risk_aversion") {
        protagonist.allocation.riskAversion = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_min_risky_weight") {
        protagonist.allocation.minRiskyWeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_max_risky_weight") {
        protagonist.allocation.maxRiskyWeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_max_gross_exposure") {
        protagonist.allocation.maxGrossExposure = parseDoubleValue(setting);
        return true;
    }

    // --- Trading-rule parameters --------------------------------------------
    if (key == "protagonist_mispricing_threshold") {
        protagonist.mispricingThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_stop_loss_threshold") {
        protagonist.stopLossThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_take_profit_threshold") {
        protagonist.takeProfitThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_volatility_window") {
        protagonist.volatilityWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "protagonist_forecast_horizon") {
        protagonist.forecastHorizon = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_short_window") {
        protagonist.shortWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "protagonist_long_window") {
        protagonist.longWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "protagonist_momentum_signal_threshold") {
        protagonist.momentumSignalThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_breakout_window") {
        protagonist.breakoutWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "protagonist_max_short_weight") {
        protagonist.maxShortWeight = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_noise_belief_shock_std_dev") {
        protagonist.noiseBeliefShockStdDev = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_noise_order_size_fraction") {
        protagonist.noiseOrderSizeFraction = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_buy_hold_target_risky_weight") {
        protagonist.buyHoldTargetRiskyWeight = parseDoubleValue(setting);
        return true;
    }

    // --- Behavioural preferences --------------------------------------------
    if (key == "protagonist_prospect_theory_enabled") {
        protagonist.prospectTheoryEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "protagonist_loss_aversion") {
        protagonist.lossAversion = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_curvature_for_gain") {
        protagonist.curvatureForGain = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_curvature_for_loss") {
        protagonist.curvatureForLoss = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_prob_distortion_for_gain") {
        protagonist.probDistortionForGain = parseDoubleValue(setting);
        return true;
    }
    if (key == "protagonist_prob_distortion_for_loss") {
        protagonist.probDistortionForLoss = parseDoubleValue(setting);
        return true;
    }

    return false;
}

} // namespace abm::config_io_detail
