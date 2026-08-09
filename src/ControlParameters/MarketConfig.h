// MarketConfig.h

#ifndef CONTROL_PARAMETERS_MARKET_CONFIG_H
#define CONTROL_PARAMETERS_MARKET_CONFIG_H

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "Utility/SimulationConstants.h"

namespace abm {

/**
 * Stochastic process generating an asset's latent fundamental value.
 *
 * Geometric Brownian motion is the model's fundamental-value theory, and every
 * declared asset uses it unless a configuration explicitly opts out. Assets are
 * meant to differ in their *parameters* — volatility, drift, price level — not
 * in their functional form, so that no asset is analytically privileged and
 * cross-asset comparisons of returns are like-for-like.
 *
 * The units of AssetDefinition::fundamentalDriftPerStep and
 * AssetDefinition::fundamentalShockStdDev depend on the process selected here,
 * so the two must always be read together.
 */
enum class FundamentalProcessType : std::uint8_t {
    /**
     * Arithmetic (additive) random walk with drift:
     * F_{t+1} = max(F_min, F_t + mu + sigma * zeta_t).
     *
     * Drift and shock are in *price* units. This is the model's historical
     * process, retained so that studies predating the geometric process can be
     * reproduced exactly. It must be requested explicitly by a declared asset.
     */
    ArithmeticRandomWalk = 0,

    /**
     * Geometric Brownian motion in Euler-Maruyama log form:
     * F_{t+1} = max(F_min, F_t * exp((mu - sigma^2 / 2) + sigma * zeta_t)).
     *
     * Drift and shock are in *log-return* units per step, so E[F_{t+1} | F_t]
     * = F_t * exp(mu) and E[log F_{t+1} - log F_t] = mu - sigma^2 / 2. The
     * Ito correction term keeps mu interpretable as the expected arithmetic
     * growth rate, following the standard Black-Scholes discretisation.
     *
     * Multiplicative dynamics keep the value strictly positive without relying
     * on the floor, and produce log-normal rather than normal fundamentals.
     *
     * This is the default for every declared asset.
     */
    GeometricBrownianMotion = 1,
};

/**
 * Generating parameters for one tradable risky asset.
 *
 * Each asset carries its own fundamental-value process, initial market state,
 * and price grid. Assets are identified by name and addressed at runtime by
 * their index in SimulationConfig::assets, which fixes a deterministic
 * iteration order.
 */
struct AssetDefinition {
    /** Symbolic identifier used as the market/fundamental history key. */
    std::string name{"asset"};

    /**
     * Includes this asset in the simulated market when true.
     *
     * Disabled assets are parsed and validated, and are retained in
     * AssetUniverse::disabled() for provenance and reporting, but they
     * are given no order book, no allocation weight, and no output rows. This
     * lets a two-asset configuration collapse exactly onto the single-asset
     * model without editing the rest of the file.
     */
    bool enabled{true};

    /** Stochastic process used to evolve the latent fundamental value. */
    FundamentalProcessType fundamentalProcess{FundamentalProcessType::GeometricBrownianMotion};

    /** Initial market and fundamental price at t = 0. */
    double initialPrice{100.0};

    /**
     * Initial inventory of this asset assigned to every agent.
     *
     * Aggregate share supply is populationSize * initialStock, which is the
     * quantity the short-sale locate constraint is expressed against.
     */
    double initialStock{0.0};

    /** Minimum price grid used when quantising limit-order prices. */
    double priceTickSize{0.01};

    /**
     * Scale of the latent fundamental-value innovation.
     *
     * Per-step log-return units under GeometricBrownianMotion (the default);
     * price units under ArithmeticRandomWalk.
     */
    double fundamentalShockStdDev{0.02};

    /**
     * Deterministic drift applied to the latent fundamental value each period.
     *
     * Per-step log-return units under GeometricBrownianMotion (the default);
     * price units under ArithmeticRandomWalk.
     */
    double fundamentalDriftPerStep{0.0};

    /** Lower bound used to keep the latent fundamental value economically positive. */
    double minimumFundamentalValue{kMinimumPrice};
};

/**
 * The tradable asset universe of one simulation run: non-empty by construction.
 *
 * Purpose: a default-constructed universe already holds one asset, and no
 * operation can empty it, so no consumer ever has to ask whether assets were
 * configured. That question used to be asked at eleven sites across the
 * simulation, output, and validation layers, and each answer was a second,
 * single-asset implementation of the model running beside the general one.
 *
 * The type therefore exposes no `empty()`. Code that tries to re-test the
 * invariant fails to compile rather than quietly regrowing a parallel path.
 *
 * Two states are distinguished, and only while a configuration is being parsed:
 *   - undeclared (the default) — the run is configured through the legacy
 *     scalar asset keys, which write into the asset returned by
 *     legacyScalarAsset();
 *   - declared — the configuration carried an `assets = ...` list, and the
 *     legacy scalar keys are rejected as a mixed configuration.
 *
 * Index order is the declared order and is the addressing scheme used by
 * Order::assetIndex, the covariance matrix, and every per-asset output column.
 */
class AssetUniverse {
  public:
    using const_iterator = std::vector<AssetDefinition>::const_iterator;

    /** Constructs the undeclared universe holding the single legacy asset. */
    AssetUniverse();

    /** Returns the number of assets, which is always at least one. */
    [[nodiscard]] std::size_t size() const {
        return assets_.size();
    }

    [[nodiscard]] const AssetDefinition& operator[](std::size_t assetIndex) const {
        return assets_[assetIndex];
    }

    [[nodiscard]] const AssetDefinition& at(std::size_t assetIndex) const {
        return assets_.at(assetIndex);
    }

    [[nodiscard]] const_iterator begin() const {
        return assets_.cbegin();
    }

    [[nodiscard]] const_iterator end() const {
        return assets_.cend();
    }

    /** Returns the backing vector for interfaces that take one directly. */
    [[nodiscard]] const std::vector<AssetDefinition>& all() const {
        return assets_;
    }

    /** Returns true once an `assets = ...` declaration has been parsed. */
    [[nodiscard]] bool declared() const {
        return declared_;
    }

    /** Returns the asset reported by single-asset outputs and legacy accessors. */
    [[nodiscard]] const AssetDefinition& primary() const {
        return assets_[primaryIndex_];
    }

    /** Returns the index of the primary asset, resolved during normalisation. */
    [[nodiscard]] std::size_t primaryIndex() const {
        return primaryIndex_;
    }

    /** Returns the index of the named asset; throws when the name is unknown. */
    [[nodiscard]] std::size_t indexByName(const std::string& name) const;

    /**
     * Returns assets that were declared but switched off.
     *
     * Retained purely for provenance: metadata and the analysis report show
     * which assets were configured but excluded, so a disabled-Asset-B run is
     * distinguishable from a run where Asset B was never declared. Populated by
     * normalise().
     */
    [[nodiscard]] const std::vector<AssetDefinition>& disabled() const {
        return disabled_;
    }

    /**
     * Replaces the universe with an explicitly declared asset list.
     *
     * @throws std::invalid_argument when the list is empty or a declaration
     *         has already been applied.
     */
    void declare(std::vector<AssetDefinition> assets);

    /** Returns the named asset for per-asset key application, or nullptr. */
    [[nodiscard]] AssetDefinition* findMutable(const std::string& name);

    /**
     * Returns the single asset configured by the legacy scalar keys.
     *
     * Returns nullptr once a declaration has been parsed: the two spellings are
     * mutually exclusive, and validation reports the mixed configuration by
     * naming the offending scalar key, which is a better error than silently
     * overwriting a declared asset.
     */
    [[nodiscard]] AssetDefinition* legacyScalarAsset();

    /**
     * Moves disabled assets aside and resolves the primary-asset index.
     *
     * Runs for declared and legacy universes alike, so there is one asset
     * pipeline rather than one per configuration spelling.
     *
     * @param requestedPrimaryName Parse-time `primary_asset` request; empty
     *        selects the first enabled asset.
     * @throws std::invalid_argument when every asset is disabled, or when the
     *         requested primary asset is not among the enabled assets.
     */
    void normalise(const std::string& requestedPrimaryName);

  private:
    std::vector<AssetDefinition> assets_;
    std::vector<AssetDefinition> disabled_{};
    std::size_t primaryIndex_{0};
    bool declared_{false};
};

/** Selects the market-clearing mechanism used by the simulation. */
enum class MarketMicrostructureMode : std::uint8_t {
    ContinuousLimitOrderBook = 0,
};

/**
 * Short-sale market-friction parameters.
 *
 * These constraints represent institutional frictions rather than behavioural
 * preferences. They are useful for testing how pessimistic beliefs enter prices
 * when agents face margin and securities-lending limits.
 */
struct ShortSaleConfig {
    /**
     * Minimum equity-to-short-notional ratio required when creating new shorts.
     *
     * Example: 0.50 allows maximum short notional equal to two times current
     * equity. Higher values make short exposure more restrictive.
     */
    double initialMarginRequirement{0.50};

    /**
     * Equity-to-short-notional ratio below which forced buy-in is triggered.
     *
     * The model restores the stricter initial-margin ratio when this lower
     * maintenance threshold is breached.
     */
    double maintenanceMarginRequirement{0.30};

    /**
     * Fraction of initial share supply that can be borrowed for short selling.
     *
     * This captures a locate-style lending constraint: even solvent bearish
     * agents cannot short if no borrowable shares remain.
     */
    double borrowableSupplyRatio{0.20};
};

/**
 * Proportional transaction-cost controls.
 *
 * The rate represents a one-way cost paid by each side of an executed trade.
 * Costs leave the agent system as a market friction, so they reduce realised
 * agent cash rather than transferring wealth to the counterparty.
 */
struct TransactionCostConfig {
    /** One-way proportional fee rate applied to executed notional. */
    double rate{0.0};

    /** Enables cost-aware no-trade bands in discretionary strategy decisions. */
    bool affectsDecisions{true};

    /** Applies the same proportional cost to broker-enforced forced buy-ins. */
    bool applyToForcedBuyIns{true};
};

/**
 * Spatial social-influence parameters.
 *
 * Agents are placed in a synthetic social space. Nearby agents can transmit an
 * opinion signal that shifts quote formation, allowing experiments on herding
 * and crisis amplification.
 */
struct SocialInfluenceConfig {
    /** Enables social opinion formation when true. */
    bool enabled{false};

    /** Width of the synthetic social space. */
    double spaceWidth{1.0};

    /** Height of the synthetic social space. */
    double spaceHeight{1.0};

    /** Maximum distance at which two agents exchange opinion signals. */
    double interactionRadius{0.15};

    /** Strength with which social opinion moves limit prices. */
    double opinionKappa{0.35};

    /** Log-price gap below which an agent with social pricing holds. */
    double holdTolerance{0.001};

    /** Lower bound for each agent's social-signal weight. */
    double gammaMin{0.10};

    /** Upper bound for each agent's social-signal weight. */
    double gammaMax{0.70};

    /** Lower bound for idiosyncratic private opinion noise. */
    double privateSignalStdMin{0.002};

    /** Upper bound for idiosyncratic private opinion noise. */
    double privateSignalStdMax{0.010};
};

/**
 * Continuous limit-order-book microstructure parameters.
 *
 * These controls replace the former call-auction price formation path with a
 * persistent double auction. Prices become realised transaction prices, while
 * spread and depth diagnostics expose the state of market liquidity.
 */
struct MicrostructureConfig {
    /** Market-clearing mechanism used for new simulation runs. */
    MarketMicrostructureMode mode{MarketMicrostructureMode::ContinuousLimitOrderBook};

    /** Number of steps a resting limit order remains active after submission. */
    std::size_t orderExpirySteps{5};

    /** Baseline probability that a resting order is cancelled before new orders arrive. */
    double cancellationBaseProbability{0.02};

    /** Additional cancellation pressure from distance to the latest market price. */
    double cancellationMispricingSensitivity{2.0};

    /** Probability that an otherwise limit-style strategy order is submitted as a market order. */
    double marketOrderProbability{0.05};

    /** Absolute log valuation gap above which an order is treated as aggressive marketable flow. */
    double marketOrderLogGapThreshold{0.03};

    /**
     * Maximum absolute log distance from the reference price at which a market
     * order may execute. Zero disables the collar, preserving unconstrained
     * market-order sweeps.
     */
    double marketOrderPriceCollar{0.0};

    /** Number of price levels used when aggregating book-depth diagnostics. */
    std::size_t bookDepthLevels{5};
};

/**
 * Synthetic pre-trading warm-up price process.
 *
 * These parameters do not affect crisis-period price formation after the
 * simulation clock starts. Under the continuous LOB, post-warm-up market prices
 * are realised transaction prices; the warm-up process only creates enough
 * historical observations for technical indicators and initial reference state.
 */
struct WarmupPriceProcessConfig {
    /** Gaussian noise scale used only when generating pre-trading warm-up prices. */
    double noiseStdDev{0.003};

    /** Fundamental-value pull used only in the pre-trading warm-up price path. */
    double fundamentalPullStrength{0.08};
};

} // namespace abm

#endif // CONTROL_PARAMETERS_MARKET_CONFIG_H
