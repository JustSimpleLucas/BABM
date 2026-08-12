// SimulationConfigSettingAppliersSimulation.cpp

#include "Config/SimulationConfigSettingAppliers.h"

#include "Config/ConfigKeyRegistry.h"

#include <stdexcept>
#include <string>
#include <vector>

namespace abm::config_io_detail {
namespace {

constexpr char kAssetKeyPrefix[] = "asset.";

[[nodiscard]] std::string trimWhitespace(const std::string& text) {
    const std::size_t first = text.find_first_not_of(" \t");
    if (first == std::string::npos) {
        return {};
    }
    const std::size_t last = text.find_last_not_of(" \t");
    return text.substr(first, last - first + 1);
}

/**
 * Records the first legacy scalar asset key and returns the asset it configures.
 *
 * Returns nullptr once an `assets = ...` declaration has been parsed, in which
 * case the value is dropped: validateAssetDefinitions then rejects the mixed
 * configuration by naming the recorded key, which is a more useful error than
 * silently overwriting a declared asset.
 */
[[nodiscard]] AssetDefinition* legacyAssetScalarTarget(SimulationConfig& simulation,
                                                       const std::string& key) {
    if (simulation.legacyAssetScalarKeySeen.empty()) {
        simulation.legacyAssetScalarKeySeen = key;
    }
    return simulation.assets.legacyScalarAsset();
}

void applyAssetListSetting(SimulationConfig& simulation, const ConfigSetting& setting) {
    if (simulation.assets.declared()) {
        throw std::invalid_argument(
            "Duplicate 'assets' declaration at " +
            config_parsing::describeLocation(setting.path, setting.lineNumber) + '.');
    }

    std::vector<AssetDefinition> declaredAssets;
    std::string remaining = config_parsing::parseString(setting.value);
    while (true) {
        const std::size_t separator = remaining.find(',');
        const std::string token = trimWhitespace(remaining.substr(0, separator));
        if (token.empty()) {
            throw std::invalid_argument(
                "Empty asset name in 'assets' declaration at " +
                config_parsing::describeLocation(setting.path, setting.lineNumber) + '.');
        }
        for (const AssetDefinition& asset : declaredAssets) {
            if (asset.name == token) {
                throw std::invalid_argument(
                    "Duplicate asset name '" + token + "' in 'assets' declaration at " +
                    config_parsing::describeLocation(setting.path, setting.lineNumber) + '.');
            }
        }
        AssetDefinition asset;
        asset.name = token;
        declaredAssets.push_back(std::move(asset));
        if (separator == std::string::npos) {
            break;
        }
        remaining = remaining.substr(separator + 1);
    }
    simulation.assets.declare(std::move(declaredAssets));
}

void applyPerAssetSetting(SimulationConfig& simulation, const ConfigSetting& setting) {
    const std::string remainder = setting.key.substr(sizeof(kAssetKeyPrefix) - 1);
    const std::size_t separator = remainder.find('.');
    if (separator == std::string::npos || separator == 0 || separator + 1 >= remainder.size()) {
        throw std::invalid_argument(
            "Malformed per-asset key '" + setting.key + "' at " +
            config_parsing::describeLocation(setting.path, setting.lineNumber) +
            ". Expected asset.<name>.<parameter>.");
    }
    const std::string assetName = remainder.substr(0, separator);
    const std::string parameter = remainder.substr(separator + 1);

    AssetDefinition* target =
        simulation.assets.declared() ? simulation.assets.findMutable(assetName) : nullptr;
    if (target == nullptr) {
        throw std::invalid_argument(
            "Unknown asset '" + assetName + "' in key '" + setting.key + "' at " +
            config_parsing::describeLocation(setting.path, setting.lineNumber) +
            ". Declare it first with 'assets = ...'.");
    }

    if (parameter == "enabled") {
        target->enabled = parseBoolValue(setting);
        return;
    }
    if (parameter == "fundamental_process") {
        target->fundamentalProcess = parseFundamentalProcessType(setting);
        return;
    }
    if (parameter == "initial_price") {
        target->initialPrice = parseDoubleValue(setting);
        return;
    }
    if (parameter == "initial_stock") {
        target->initialStock = parseDoubleValue(setting);
        return;
    }
    if (parameter == "price_tick_size") {
        target->priceTickSize = parseDoubleValue(setting);
        return;
    }
    if (parameter == "fundamental_shock_std_dev") {
        target->fundamentalShockStdDev = parseDoubleValue(setting);
        return;
    }
    if (parameter == "fundamental_drift_per_step") {
        target->fundamentalDriftPerStep = parseDoubleValue(setting);
        return;
    }
    if (parameter == "minimum_fundamental_value") {
        target->minimumFundamentalValue = parseDoubleValue(setting);
        return;
    }

    throw std::invalid_argument("Unknown per-asset parameter '" + parameter + "' in key '" +
                                setting.key + "' at " +
                                config_parsing::describeLocation(setting.path, setting.lineNumber) +
                                '.' + describeSuggestions(nearestPerAssetFields(parameter)));
}

} // namespace

bool applyAssetSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    SimulationConfig& simulation = config.simulation;

    if (key == "assets") {
        applyAssetListSetting(simulation, setting);
        return true;
    }
    if (key == "primary_asset") {
        simulation.primaryAssetName = config_parsing::parseString(setting.value);
        return true;
    }
    if (key == "asset_fundamental_correlation") {
        simulation.assetFundamentalCorrelation = parseDoubleValue(setting);
        return true;
    }
    if (key.rfind(kAssetKeyPrefix, 0) == 0) {
        applyPerAssetSetting(simulation, setting);
        return true;
    }

    return false;
}

void rejectRetiredSetting(const ConfigSetting& setting) {
    const std::string& key = setting.key;
    if (key == "price_noise_std_dev" || key == "fundamental_pull_strength") {
        throw std::invalid_argument(
            "Config key '" + key + "' at " +
            config_parsing::describeLocation(setting.path, setting.lineNumber) +
            " was renamed with a warmup_ prefix because it only affects the pre-trading warm-up "
            "history. Use 'warmup_price_noise_std_dev' or "
            "'warmup_fundamental_pull_strength'.");
    }
    if (key == "order_imbalance_impact") {
        throw std::invalid_argument(
            "Config key 'order_imbalance_impact' at " +
            config_parsing::describeLocation(setting.path, setting.lineNumber) +
            " was removed. Continuous LOB price formation uses realised transaction prices; "
            "order imbalance is exported as a diagnostic, not as a direct price-impact control.");
    }
}

bool applyCoreSimulationSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    SimulationConfig& simulation = config.simulation;

    if (key == "asset_name") {
        std::string name = config_parsing::parseString(setting.value);
        if (AssetDefinition* asset = legacyAssetScalarTarget(simulation, key)) {
            asset->name = std::move(name);
        }
        return true;
    }
    if (key == "time_steps") {
        simulation.timeSteps = parseSizeValue(setting);
        return true;
    }
    if (key == "warmup_steps") {
        simulation.warmupSteps = parseSizeValue(setting);
        return true;
    }
    if (key == "num_fundamentalists") {
        simulation.numFundamentalists = parseSizeValue(setting);
        return true;
    }
    if (key == "num_chartists") {
        simulation.numChartists = parseSizeValue(setting);
        return true;
    }
    if (key == "num_noise_traders") {
        simulation.numNoiseTraders = parseSizeValue(setting);
        return true;
    }
    if (key == "num_buy_and_hold_agents") {
        simulation.numBuyAndHoldAgents = parseSizeValue(setting);
        return true;
    }
    if (key == "initial_price") {
        const double value = parseDoubleValue(setting);
        if (AssetDefinition* asset = legacyAssetScalarTarget(simulation, key)) {
            asset->initialPrice = value;
        }
        return true;
    }
    if (key == "initial_cash") {
        simulation.initialCash = parseDoubleValue(setting);
        return true;
    }
    if (key == "initial_stock") {
        const double value = parseDoubleValue(setting);
        if (AssetDefinition* asset = legacyAssetScalarTarget(simulation, key)) {
            asset->initialStock = value;
        }
        return true;
    }
    if (key == "short_selling_enabled") {
        simulation.shortSellingEnabled = parseBoolValue(setting);
        return true;
    }
    if (key == "risk_free_rate") {
        simulation.riskFreeRate = parseDoubleValue(setting);
        return true;
    }
    if (key == "agent_activity_rate") {
        simulation.agentActivityRate = parseDoubleValue(setting);
        return true;
    }
    if (key == "price_tick_size") {
        const double value = parseDoubleValue(setting);
        if (AssetDefinition* asset = legacyAssetScalarTarget(simulation, key)) {
            asset->priceTickSize = value;
        }
        return true;
    }
    if (key == "fundamental_shock_std_dev") {
        const double value = parseDoubleValue(setting);
        if (AssetDefinition* asset = legacyAssetScalarTarget(simulation, key)) {
            asset->fundamentalShockStdDev = value;
        }
        return true;
    }
    if (key == "fundamental_drift_per_step") {
        const double value = parseDoubleValue(setting);
        if (AssetDefinition* asset = legacyAssetScalarTarget(simulation, key)) {
            asset->fundamentalDriftPerStep = value;
        }
        return true;
    }
    if (key == "minimum_fundamental_value") {
        const double value = parseDoubleValue(setting);
        if (AssetDefinition* asset = legacyAssetScalarTarget(simulation, key)) {
            asset->minimumFundamentalValue = value;
        }
        return true;
    }
    if (key == "covariance_window") {
        simulation.covarianceWindow = parseSizeValue(setting);
        return true;
    }
    if (key == "seed") {
        simulation.seed = parseSeedValue(setting);
        return true;
    }

    return false;
}

bool applyShortSaleSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    ShortSaleConfig& shortSale = config.simulation.shortSale;

    if (key == "short_sale_initial_margin_requirement") {
        shortSale.initialMarginRequirement = parseDoubleValue(setting);
        return true;
    }
    if (key == "short_sale_maintenance_margin_requirement") {
        shortSale.maintenanceMarginRequirement = parseDoubleValue(setting);
        return true;
    }
    if (key == "short_sale_borrowable_supply_ratio") {
        shortSale.borrowableSupplyRatio = parseDoubleValue(setting);
        return true;
    }

    return false;
}

bool applyTransactionCostSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    TransactionCostConfig& transactionCosts = config.simulation.transactionCosts;

    if (key == "transaction_cost_rate") {
        transactionCosts.rate = parseDoubleValue(setting);
        return true;
    }
    if (key == "transaction_cost_affects_decisions") {
        transactionCosts.affectsDecisions = parseBoolValue(setting);
        return true;
    }
    if (key == "transaction_cost_apply_to_forced_buy_ins") {
        transactionCosts.applyToForcedBuyIns = parseBoolValue(setting);
        return true;
    }

    return false;
}

bool applyWarmupPriceSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    WarmupPriceProcessConfig& warmupPriceProcess = config.simulation.warmupPriceProcess;

    if (key == "warmup_price_noise_std_dev") {
        warmupPriceProcess.noiseStdDev = parseDoubleValue(setting);
        return true;
    }
    if (key == "warmup_fundamental_pull_strength") {
        warmupPriceProcess.fundamentalPullStrength = parseDoubleValue(setting);
        return true;
    }

    return false;
}

bool applyMicrostructureSetting(RuntimeConfig& config, const ConfigSetting& setting) {
    const std::string& key = setting.key;
    MicrostructureConfig& microstructure = config.simulation.microstructure;

    if (key == "market_microstructure") {
        microstructure.mode = config_parsing::parseMarketMicrostructureMode(
            setting.value, setting.path, setting.lineNumber);
        return true;
    }
    if (key == "order_expiry_steps") {
        microstructure.orderExpirySteps = parseSizeValue(setting);
        return true;
    }
    if (key == "cancellation_base_probability") {
        microstructure.cancellationBaseProbability = parseDoubleValue(setting);
        return true;
    }
    if (key == "cancellation_mispricing_sensitivity") {
        microstructure.cancellationMispricingSensitivity = parseDoubleValue(setting);
        return true;
    }
    if (key == "market_order_probability") {
        microstructure.marketOrderProbability = parseDoubleValue(setting);
        return true;
    }
    if (key == "market_order_log_gap_threshold") {
        microstructure.marketOrderLogGapThreshold = parseDoubleValue(setting);
        return true;
    }
    if (key == "market_order_price_collar") {
        microstructure.marketOrderPriceCollar = parseDoubleValue(setting);
        return true;
    }
    if (key == "book_depth_levels") {
        microstructure.bookDepthLevels = parseSizeValue(setting);
        return true;
    }

    return false;
}

} // namespace abm::config_io_detail
