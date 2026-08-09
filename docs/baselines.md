# Regression baselines

## Phase-0 baseline (multi-asset extension reference)

The multi-asset extension work (config schema, per-asset order books, Markowitz
allocation) is gated on bit-for-bit reproduction of this single-asset baseline
until the deliberately behaviour-changing Phase-3 fixes (log-return units, CPT
scale invariance) land.

Recipe (release build, current `config/simulation.cfg`, 50 000 steps, seed 66):

```bash
sed -e 's/^experiment_output_enabled = 1/experiment_output_enabled = 0/' \
    -e 's/^python_analysis_enabled = 1/python_analysis_enabled = 0/' \
    config/simulation.cfg > /tmp/baseline_check.cfg
./build/release/simulate /tmp/baseline_check.cfg
shasum -a 256 data/latest/step_timeseries.csv
```

Expected SHA-256 of `data/latest/step_timeseries.csv`:

```
1a60fe53006e0e4426920a1751b5755c4e60d1530fb6630f0066acc1c488126c
```

Note: the sed above writes the derived config to `/tmp` only because relative
output paths resolve from the config file's directory; running from a repo-local
copy under `config/` gives the same simulation but writes `data/` next to the
repo root either way.

## Phase-3 behaviour changes (Markowitz + log-units + CPT scale invariance)

Phase 3 replaced the scalar mean-variance rule with the full Markowitz solve
(shared rolling covariance, `covariance_window`), moved fundamentalist and
chartist forecasts into log-return space, and made the CPT adjustment
scale-invariant (reference anchors mapped into return space). These changes
alter trajectories for any population containing fundamentalists or chartists
and require recalibrating behavioural parameters before comparing to earlier
calibrated results.

The shipped `config/simulation.cfg` is a noise-trader-only population; noise
traders keep the legacy single-asset path (and untouched private random
streams) when only one asset is declared, so the Phase-0 baseline hash above
**still reproduces bit-for-bit** for that config after Phase 3. Populations
with fundamentalists/chartists take the optimiser path: verified live by
observing distinct trajectories under `fundamentalist_max_gross_exposure`
values of 1.0 versus 0.1 on a 50/50/20 mixed population.

## Two-asset example

`config/examples/two_asset.cfg` declares two risky assets that share the same
geometric Brownian fundamental process and differ only in their parameters
(alpha: drift +0.0002, shock sd 0.0003, tick 0.01, P0 100; beta: drift −0.0005,
shock sd 0.02, tick 0.05, P0 40) and a mixed 40/40/20 fundamentalist/chartist/
noise population:

```bash
./build/release/simulate config/examples/two_asset.cfg
```

The run archive gains `asset_timeseries.csv` with two rows per step.
`step_timeseries.csv` keeps its 34 columns and reports the primary asset
(alpha) only, so existing tooling is unaffected.

### Neither asset is privileged

`primary_asset` nominates the asset projected into that single-asset
`step_timeseries.csv` view. It carries no analytical weight: every asset is
reported, calibrated, and screened on identical terms.

- **Stylised facts.** `stylised_facts.csv` carries an `asset` column and one
  screening block per asset. The Python diagnostics layer produces one row per
  `(run, asset)` with its own Ljung-Box, Jarque-Bera, ARCH LM, and GARCH
  results, plus its own drawdown and traded volume, so the two markets can
  legitimately reach different verdicts.
- **Web report.** On a multi-asset run the core price, return, quote,
  liquidity, order-flow, and allocative-efficiency figures are rebuilt per
  asset under the same figure names, and the return distribution, ECDF, and ACF
  panels plot one series per `(run, asset)`. The evidence cards and key-metric
  rows name each asset. The Cross-Asset Dynamics section holds only the joint
  quantities — realised correlation, relative price, portfolio composition.
- **Calibration.** Each asset's returns are scored against the empirical
  benchmarks independently and the trial objective is the mean of those scores,
  recorded per asset as `asset_score.<name>`. Seed-robustness verdicts are
  computed per asset and pooled, so a candidate has to be both a good fit and
  stable in every market.

Runs archived without an `asset_timeseries.csv` fall back to the single-asset
`step_timeseries.csv` view throughout and render exactly as they did before.

Note on order flow: fundamentalists and chartists share one view of each
asset and therefore quote the same side, so a population without noise traders
produces little crossing and few trades. That is pre-existing single-asset
behaviour, not a multi-asset artefact — the legacy single-asset smoke
configuration shows the same one-sided book. Multi-asset tests that assert
trades therefore include noise traders.

## Two-asset extension: process types, rho_AB, and the Asset B toggle

The two-asset work adds three controls on top of the multi-asset foundation.

### Per-asset fundamental process

`asset.<name>.fundamental_process` selects the stochastic process generating an
asset's latent fundamental value:

| Value | Process | Drift and shock units |
| --- | --- | --- |
| `gbm` (default) | `F_{t+1} = max(F_min, F_t * exp((mu - sigma^2/2) + sigma * zeta))` | per-step log return |
| `random_walk` | `F_{t+1} = max(F_min, F_t + mu + sigma * zeta)` | price units |

Geometric Brownian motion is the model's fundamental-value theory and applies
to every declared asset unless a configuration explicitly opts out. Assets are
meant to differ in their parameters, not in their functional form: a shared
process is what makes per-asset returns like-for-like, so no asset is
privileged in the report, the calibration objective, or the stylised-fact
screen. Under `gbm` the Ito correction makes `mu` the expected arithmetic
growth rate, so `E[F_{t+1} | F_t] = F_t * exp(mu)`.

`random_walk` is retained only for reproducing studies that predate the
geometric process. Legacy single-asset configurations — those using the scalar
`fundamental_shock_std_dev` keys rather than an `assets` declaration — are
pinned to `random_walk`, because those keys were written in price units and
reading them as log returns would silently inflate a `0.03` price increment
into a 3% per-step volatility.

**The units change with the process.** Copying `fundamental_shock_std_dev =
3.0` (three price units) onto a geometric asset would request a 300% per-step
volatility. Validation rejects a geometric shock above
`kMaximumGeometricProcessLogStdDev` (1.0) with a message naming the units,
turning the most likely misconfiguration into an explicit error.

### Cross-asset fundamental correlation

`asset_fundamental_correlation` sets the correlation between the standardised
fundamental innovations of every distinct asset pair — exactly `rho_AB` in the
two-asset case. Innovations are drawn as independent standard normals and
mapped through the closed-form one-factor square root of the equicorrelation
matrix:

```text
zeta_j = a * z_j + b * sum_k z_k,  a = sqrt(1 - rho),  b = (sqrt(1 + (n-1) rho) - a) / n
```

This is used in preference to a Cholesky factorization because it stays exact
on the positive-semi-definite boundary (`rho = 1`, or the lower limit
`rho = -1/(n-1)`), where the equicorrelation matrix is singular and Cholesky
fails. Correlations below `-1/(n-1)` are rejected: no joint distribution exists.

### Bit-for-bit preservation of the single-asset baseline

The joint draw path is used for every run, including single-asset runs, so the
following equivalence is load-bearing rather than incidental:

- with one asset, or with `rho = 0`, the correlation map is short-circuited to
  the identity;
- the process helper draws `Normal(0, 1)` and scales by `sigma`, which is
  bit-identical to the former `Normal(0, sigma)` draw and consumes the same
  engine state.

`testCorrelatedFundamentalMatchesLegacySingleAssetDraw` pins the second point
directly. The Phase-0 baseline hash above still reproduces:

```text
1a60fe53006e0e4426920a1751b5755c4e60d1530fb6630f0066acc1c488126c
```

### Asset enable/disable toggle

`asset.<name>.enabled = 0` removes an asset from the tradable universe.
Disabled assets are still parsed and validated, and are retained in
`SimulationConfig::disabledAssets` and in `config.json` under
`assets.disabled_definitions`, so a run with Asset B switched off is
distinguishable from one where Asset B was never declared. Validation rejects
disabling every asset, and rejects nominating a disabled asset as `primary_asset`.

With Asset B disabled the run collapses exactly onto the single-asset model:
`asset_timeseries.csv` carries only Asset A, `step_timeseries.csv` keeps its 34
columns, and the analysis report contains no multi-asset section and no
multi-asset figures. `test_disabled_asset_b_leaves_pre_existing_report_unchanged`
asserts the generated figure index is identical to the single-asset baseline
report's.

### Web output

Reports for multi-asset runs gain a **Multi-Asset Dynamics** section with four
panels, plus an Asset Configuration table recording each asset's process,
parameters, and units:

1. price vs fundamental, one subplot per asset;
2. per-asset traded volume and rolling realised volatility;
3. cross-asset rolling return correlation (against the configured `rho_AB`
   reference line) and the price ratio `p_A / p_B`;
4. mean agent portfolio composition in each asset and cash, as a stacked area.

Panels are stacked subplots rather than a single panel with an asset toggle
because reports export publication figures to static PNG/PDF/SVG via Kaleido,
and a Plotly `updatemenus` toggle would export only the selected asset.

Portfolio weights come from `asset_timeseries.csv` columns
`mean_agent_portfolio_weight` and `portfolio_weight_agent_count`, written per
(step, asset). The weight is the cross-sectional mean of
`w_ij = q_ij * P_j / W_i` over agents with strictly positive wealth; the mean
cash weight is recovered as `1 - sum_j w_j` because the mean is linear. Database
schema migration 008 adds the two columns (`CURRENT_SCHEMA_VERSION` 8); the
config/metadata JSON `schema_version` moved from 6 to 7.

## Relationship to pre-Phase-0 results (`pre-multiasset-baseline` tag)

The git tag `pre-multiasset-baseline` (commit `ac73221`) marks the last state
that reproduces earlier thesis runs. Phase 0 diverges from that state through
exactly one mechanism: **self-trade prevention**. With the prevention branch
disabled, the Phase-0 code reproduces the tagged state bit-for-bit over the
full 50 000-step run; with it enabled, the first divergence appears at
simulation step 29, where an agent previously executed against its own resting
bid. All other Phase-0 changes (shared order-sizing helpers, cancellation
counter split, market-order price collar plumbing, chartist allocation-floor
fix with the config updated to `chartist_min_risky_weight = -0.30`) are
behaviour-preserving by construction and verified by the comparison above.
