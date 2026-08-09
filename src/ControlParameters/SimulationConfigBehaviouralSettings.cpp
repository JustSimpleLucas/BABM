// SimulationConfigBehaviouralSettings.cpp

#include "ControlParameters/SimulationConfigSettingAppliers.h"

namespace abm::config_io_detail {

bool applyControlSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    ControlParameters& control = config.simulation.control;

    if (key == "control_prospect_theory_enabled") {
        control.prospectTheoryEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "control_prospect_theory_agent_fraction") {
        control.prospectTheoryAgentFraction = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_prospect_heterogeneity_enabled") {
        control.prospectParameterHeterogeneityEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "control_loss_aversion") {
        control.lossAversion = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_loss_aversion_std_dev") {
        control.lossAversionStdDev = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_curvature_for_gain") {
        control.curvatureForGain = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_curvature_for_gain_std_dev") {
        control.curvatureForGainStdDev = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_curvature_for_loss") {
        control.curvatureForLoss = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_curvature_for_loss_std_dev") {
        control.curvatureForLossStdDev = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_prob_distortion_for_gain") {
        control.probDistortionForGain = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_prob_distortion_for_loss") {
        control.probDistortionForLoss = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_probability_distortion_min") {
        control.probabilityDistortionMin = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_probability_distortion_max") {
        control.probabilityDistortionMax = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_reference_point") {
        control.referencePoint = parseDoubleValue(setting);
        return true;
    }
    if (key == "control_reference_point_mode") {
        control.referencePointMode = config_parsing::parseProspectReferencePointMode(
            setting.value, setting.path, setting.lineNumber);
        return true;
    }
    if (key == "control_reference_moving_average_window") {
        control.referenceMovingAverageWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "control_prospect_scenario_count") {
        control.prospectScenarioCount = parseSizeValue(setting);
        return true;
    }

    return false;
}

} // namespace abm::config_io_detail
