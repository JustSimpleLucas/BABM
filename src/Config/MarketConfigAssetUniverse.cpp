// MarketConfigAssetUniverse.cpp

#include "Config/MarketConfig.h"

#include <stdexcept>
#include <utility>

namespace abm {
namespace {

/**
 * Scale of the fundamental innovation assumed by the legacy scalar keys.
 *
 * This differs from AssetDefinition's own default (a log-return standard
 * deviation) because the legacy `fundamental_shock_std_dev` key was written for
 * the arithmetic walk, where the value is a price increment. Studies predating
 * the multi-asset extension are reproduced exactly only if both this scale and
 * the arithmetic process below are the defaults an undeclared universe carries.
 */
constexpr double kLegacyScalarFundamentalShockStdDev = 0.03;

/** Builds the single asset that the legacy scalar keys configure. */
[[nodiscard]] AssetDefinition legacyScalarDefaultAsset() {
    AssetDefinition asset;
    asset.fundamentalProcess = FundamentalProcessType::ArithmeticRandomWalk;
    asset.fundamentalShockStdDev = kLegacyScalarFundamentalShockStdDev;
    return asset;
}

} // namespace

AssetUniverse::AssetUniverse() : assets_{legacyScalarDefaultAsset()} {}

std::size_t AssetUniverse::indexByName(const std::string& name) const {
    for (std::size_t assetIndex = 0; assetIndex < assets_.size(); ++assetIndex) {
        if (assets_[assetIndex].name == name) {
            return assetIndex;
        }
    }
    throw std::invalid_argument("Unknown asset name '" + name + "'.");
}

void AssetUniverse::declare(std::vector<AssetDefinition> assets) {
    if (declared_) {
        throw std::invalid_argument("Duplicate 'assets' declaration.");
    }
    if (assets.empty()) {
        throw std::invalid_argument("The 'assets' declaration must name at least one asset.");
    }
    assets_ = std::move(assets);
    declared_ = true;
}

AssetDefinition* AssetUniverse::findMutable(const std::string& name) {
    for (AssetDefinition& asset : assets_) {
        if (asset.name == name) {
            return &asset;
        }
    }
    return nullptr;
}

AssetDefinition* AssetUniverse::legacyScalarAsset() {
    return declared_ ? nullptr : &assets_.front();
}

void AssetUniverse::normalise(const std::string& requestedPrimaryName) {
    /*
     * Disabled assets move aside before any index is resolved, so every
     * downstream consumer sees only tradable assets and never has to test the
     * enable flag. An undeclared universe passes through unchanged because its
     * single asset is enabled.
     */
    std::vector<AssetDefinition> enabledAssets;
    enabledAssets.reserve(assets_.size());
    disabled_.clear();
    for (AssetDefinition& asset : assets_) {
        if (asset.enabled) {
            enabledAssets.push_back(std::move(asset));
        } else {
            disabled_.push_back(std::move(asset));
        }
    }
    if (enabledAssets.empty()) {
        throw std::invalid_argument(
            "Every declared asset is disabled; the market needs at least one tradable asset.");
    }
    assets_ = std::move(enabledAssets);
    primaryIndex_ = requestedPrimaryName.empty() ? 0 : indexByName(requestedPrimaryName);
}

} // namespace abm
