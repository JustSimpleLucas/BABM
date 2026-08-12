// ModelConfig.h

#ifndef ABM_CONFIG_MODEL_CONFIG_H
#define ABM_CONFIG_MODEL_CONFIG_H

#include <cstddef>
#include <cstdint>
#include <string>

#include "Config/BehaviouralConfig.h"
#include "Config/MarketConfig.h"
#include "Config/StrategyConfig.h"

namespace abm {

/**
 * Complete set of model parameters required for one simulation run.
 *
 * This struct is deliberately explicit rather than clever: each field
 * corresponds to a modelling assumption that can be documented, calibrated, and
 * reproduced from a configuration file.
 */
struct SimulationConfig {
    /**
     * Tradable risky assets in declared (index) order.
     *
     * Never empty: see AssetUniverse. After normalisation it holds only
     * *enabled* assets, so every downstream consumer can iterate it without
     * re-checking the enable flag.
     */
    AssetUniverse assets{};

    /**
     * Pairwise correlation between the standardised fundamental innovations of
     * any two distinct assets (an equicorrelation structure).
     *
     * For the two-asset case this is exactly rho_AB. Zero reproduces
     * independent per-asset innovations and the historical draw sequence.
     * Correlated fundamentals matter because they determine how much
     * diversification is genuinely available to agents: with rho near 1 the
     * Markowitz rule cannot reduce risk by spreading across assets.
     */
    double assetFundamentalCorrelation{0.0};

    /** Parse-time primary-asset name request; resolved to an index during normalisation. */
    std::string primaryAssetName{};

    /** Parse-time provenance: first legacy scalar asset key seen (empty when none). */
    std::string legacyAssetScalarKeySeen{};

    /** Returns the primary asset definition. */
    [[nodiscard]] const AssetDefinition& primaryAsset() const {
        return assets.primary();
    }

    /*
     * Primary-asset projections.
     *
     * Single-asset consumers — the run-id builder, the step-timeseries writer,
     * the calibration pipeline — read the market through these. They are
     * derived rather than stored so that the asset definition is the single
     * source of truth; the two used to be separate fields kept in step by a
     * hand-written mirror block in normaliseSimulationConfig.
     */

    /** Returns the primary asset's history key. */
    [[nodiscard]] const std::string& assetName() const {
        return primaryAsset().name;
    }

    /** Returns the primary asset's initial market and fundamental price at t = 0. */
    [[nodiscard]] double initialPrice() const {
        return primaryAsset().initialPrice;
    }

    /** Returns the primary asset's per-agent initial inventory. */
    [[nodiscard]] double initialStock() const {
        return primaryAsset().initialStock;
    }

    /** Returns the primary asset's limit-order price grid. */
    [[nodiscard]] double priceTickSize() const {
        return primaryAsset().priceTickSize;
    }

    /** Returns the primary asset's fundamental-innovation scale. */
    [[nodiscard]] double fundamentalShockStdDev() const {
        return primaryAsset().fundamentalShockStdDev;
    }

    /** Returns the primary asset's deterministic fundamental drift per period. */
    [[nodiscard]] double fundamentalDriftPerStep() const {
        return primaryAsset().fundamentalDriftPerStep;
    }

    /** Returns the primary asset's lower bound on the latent fundamental value. */
    [[nodiscard]] double minimumFundamentalValue() const {
        return primaryAsset().minimumFundamentalValue;
    }

    /** Number of trading periods simulated after warm-up. */
    std::size_t timeSteps{250};

    /** Pre-simulation observations used to initialise technical indicators. */
    std::size_t warmupSteps{25};

    /** Number of value-oriented agents trading on fundamental mispricing. */
    std::size_t numFundamentalists{60};

    /** Number of technical-trading agents. */
    std::size_t numChartists{60};

    /** Number of uninformed random-liquidity traders. */
    std::size_t numNoiseTraders{0};

    /** Number of passive long-only buy-and-hold investors. */
    std::size_t numBuyAndHoldAgents{0};

    /** Initial cash endowment assigned to every agent. */
    double initialCash{10000.0};

    /** Enables negative inventory when sell orders exceed current holdings. */
    bool shortSellingEnabled{true};

    /** Margin, forced buy-in, and securities-lending constraints for shorts. */
    ShortSaleConfig shortSale{};

    /** Proportional execution costs and associated behavioural no-trade bands. */
    TransactionCostConfig transactionCosts{};

    /** Per-step risk-free cash accrual rate. */
    double riskFreeRate{0.001};

    /** Probability that an agent is active in a given simulation step. */
    double agentActivityRate{0.75};

    /** Price process used only before agent trading starts. */
    WarmupPriceProcessConfig warmupPriceProcess{};

    /** Trailing log-return observations used to estimate the asset covariance matrix. */
    std::size_t covarianceWindow{50};

    /** Deterministic seed used for reproducible stochastic draws. */
    std::uint64_t seed{42};

    /** Behavioural preference controls. */
    ControlParameters control{};

    /** Fundamentalist strategy controls. */
    FundamentalistConfig fundamentalist{};

    /** Chartist strategy controls. */
    ChartistConfig chartist{};

    /** Noise-trader random-liquidity controls. */
    NoiseTraderConfig noiseTrader{};

    /** Passive buy-and-hold allocation controls. */
    BuyAndHoldConfig buyAndHold{};

    /** Spatial social-influence controls. */
    SocialInfluenceConfig social{};

    /** Continuous market microstructure controls. */
    MicrostructureConfig microstructure{};
};

} // namespace abm

#endif // ABM_CONFIG_MODEL_CONFIG_H
