# Configuration guide

Why each section of `config/simulation.cfg` exists, what it is modelling, and
why the shipped values are the values they are.

This is the companion to **[config_reference.md](config_reference.md)**, and the
two answer different questions:

| Document | Answers | Maintained by |
| --- | --- | --- |
| [`config_reference.md`](config_reference.md) | *What is this key? What are its units and valid range?* | Generated from the C++ key registry — never edit by hand |
| `config_guide.md` (this file) | *What is this section modelling, and why these values?* | Written by hand |

The split matters. Every per-key fact — units, admissible range, one-line
meaning — already lives in `src/Config/ConfigKeyRegistry.cpp` and is regenerated
into the reference by a test, so it cannot drift. This guide deliberately holds
only what a registry structurally cannot: the reasoning behind a section, and
the rationale for the particular numbers this configuration ships with.

Check a file without running anything:

```bash
build/debug/simulate --validate --config config/simulation.cfg
```

---

## Assets

Every asset follows the same theory, geometric Brownian motion:

```
F_{t+1} = F_t * exp((mu - sigma^2 / 2) + sigma * zeta)
```

Drift (`mu`) and shock (`sigma`) are per-step **log returns** for every asset,
not price increments. Values stay strictly positive and are log-normally
distributed, so each fundamental carries proportional rather than additive
shocks.

Because the units are relative, `sigma` is directly comparable across assets
regardless of price level: `0.0003` and `0.02` are a 0.03% and a 2% per-step
volatility whatever the asset costs. The assets therefore differ only in their
*parameters* — volatility, drift, price level, tick size, supply — never in
their functional form.

Neither asset is privileged. Reports, calibration, and stylised-fact screening
cover every enabled asset on identical terms. `primary_asset` only nominates
which asset is projected into the single-asset `step_timeseries.csv` view kept
for legacy tooling; it carries no analytical weight. The authoritative
multi-asset series is `asset_timeseries.csv`.

Agents allocate jointly across all assets through the Markowitz rule, so
cross-asset covariance shapes the demand for each.
`asset_fundamental_correlation` (rho_AB) is what limits the diversification
genuinely available to them: at 0.0 the fundamentals are independent, and as rho
approaches 1 the Markowitz rule can no longer reduce risk by spreading across
assets.

**On the shipped values.** Alpha's `fundamental_shock_std_dev = 0.0003` and
`fundamental_drift_per_step = 0.0002` are the model's former arithmetic-walk
values (0.03 and 0.02 in price units) divided by its initial price of 100. That
division is deliberate: it lets alpha keep the fundamental dynamics it had
before the model adopted the geometric functional form, so results either side
of that change stay comparable.

`fundamental_process` accepts `gbm` (multiplicative, log-return units — the
model default) or `random_walk` (additive, price units), the latter retained
only for reproducing studies that predate the geometric process.

Setting `asset.beta.enabled = 0` collapses the configuration onto the
single-asset model. Every pre-existing output and dashboard view then renders
exactly as it did before multi-asset support.

**Ordering.** `assets = ...` must appear before any `asset.<name>.*` key,
because per-asset settings are resolved against an already-declared universe.
Getting this wrong is reported clearly rather than silently ignored.

## Population

The strategy mix. Counts are absolute numbers of agents, not proportions, so
changing one count changes both that strategy's presence *and* the total market
size. At least one agent is required — though a protagonist on his own also
satisfies that.

## Protagonist

One identified investor, followed individually through the run.

Everyone in the population above is anonymous: an agent belongs to a strategy
group and draws its behavioural preferences from a shared distribution. That is
the right representation for studying aggregate market outcomes, and it is the
wrong one for the question a behavioural-finance case study actually asks —
what happened to *one* investor, with a stated endowment, a stated risk
appetite, and stated loss aversion.

The protagonist is that investor, and he is deliberately an **ordinary trader**.
He runs one of the four rules above, through the same order generation,
clearing, and risk machinery as everybody else; the market is not told that he
is special. Only his parameters are individual, which is what makes him a case
study rather than a new market mechanism.

Two properties follow, and both are intentional:

- **He is an additional agent.** The population counts keep meaning exactly what
  they say, so a run with him has one more participant than the same
  configuration without him.
- **Nothing about him is sampled.** His preferences and his technical rule are
  configured rather than drawn, so constructing him consumes no values from the
  shared agent random stream. With `protagonist_enabled = 0` a run reproduces
  byte-for-byte what it produced before the protagonist existed. (With him
  enabled the agent-side stream does differ — social-network initialisation and
  the per-step activation draw both scale with population size — which is
  correct: an extra participant changes the market.)

`protagonist_chartist_rule` is read only when `protagonist_strategy = chartist`,
and unlike `chartist_strategy_mode` it rejects `random`. A population may
reasonably sample across the four technical rules; an identified individual
whose rule is not known until the seed is drawn cannot be described in a
write-up.

`protagonist_forecast_horizon` plays the role of the population's forecast
horizon for his fundamentalist or chartist rule.

Only the rule block matching `protagonist_strategy` is read when his strategy is
built, but **every** value is validated regardless. A mistyped threshold
belonging to an unselected rule should fail the run rather than sit unnoticed
until someone switches strategies.

His behavioural preferences are set directly rather than through
`control_prospect_theory_agent_fraction`. That fraction assigns CPT across the
anonymous population by a seeded draw, which is exactly the mechanism an
identified individual must not be subject to. Setting his preferences directly
is what lets an experiment make him the loss-averse investor in an otherwise
expected-utility market, or the reverse.

His outcome is written to `protagonist_timeseries.csv`, flagged as
`is_protagonist` in `agents_final.csv`, and summarised in `summary_metrics.csv`.
The web dashboard shows where he finished relative to everyone else.

## Run control

`seed` is the master seed, but the run uses two independent streams derived from
it: the fundamental process uses `seed` and the agent side uses `seed + 1`.
Keeping them apart means a change to agent behaviour cannot perturb the
fundamental path, so behavioural experiments stay comparable against a fixed
seed.

`warmup_steps` seeds the pre-trading price history that technical indicators and
volatility estimates read. It must be at least the longest lookback of **every
active strategy, including the protagonist**, whose windows are configured
independently of the population's — so raising a volatility or moving-average
window may force raising the warm-up too. This is validated rather than assumed.

`warmup_price_noise_std_dev` and `warmup_fundamental_pull_strength` apply to the
warm-up price process only. After warm-up, prices are realised transaction
prices from the continuous limit-order book.

`covariance_window` is the trailing log-return window used to estimate the asset
covariance matrix behind the Markowitz portfolio rule, and it is shared by all
agents.

## Behavioural finance (Cumulative Prospect Theory)

Boolean keys accept `true/false`, `on/off`, `yes/no`, or `1/0`.

Set `control_prospect_theory_enabled = 0` for an expected-utility baseline run.
When it is on, `control_prospect_theory_agent_fraction` decides how much of the
population uses CPT valuation; the assignment is seeded and reproducible for a
given run seed.

`control_prospect_heterogeneity_enabled` switches between shared preferences and
per-agent draws of lambda_i, alpha_i, beta_i and gamma_i. The `*_std_dev` keys
and the `control_probability_distortion_min/max` interval are the dispersions
those draws use, and they are inert when heterogeneity is off.

The reference point is the anchor against which gains and losses are judged, and
`control_reference_point_mode` chooses the rule:

- `configured` — the fixed `control_reference_point` value.
- `average_purchase_price` — the agent's own average entry price (the default).
- `recent_peak_wealth` — the highest wealth the agent has reached.
- `moving_average_price` — a trailing price average, windowed by
  `control_reference_moving_average_window`.
- `initial_wealth` — the agent's endowment.

`control_reference_point` is the fallback scale used when an agent has no
personal entry price yet. `control_prospect_scenario_count` is the odd number of
scenarios in the binomial ladder that stands for the agent's belief about next
step's return. The ladder is moment-matched: its variance equals the estimated
volatility squared for every count, so the count sets only how finely the tails
are resolved, never the risk the agent perceives. Results settle by about 13
scenarios (the shipped value); 3 is a coarse approximation.

What CPT contributes to an agent's forecast is a premium: the certainty-equivalent
return of holding the asset for one more step minus that of holding cash, both
judged against the agent's reference point. A riskless forecast passes through
unchanged. Near the reference point risk lowers the premium (loss aversion); in a
paper loss it raises it (risk seeking in losses), and in a paper gain it lowers it
(risk aversion in gains), which is why CPT agents keep losers and realise winners.
Because the premium is in log-return units, loss-aversion values are comparable
with the empirical literature (Tversky and Kahneman, 1992, report about 2.25).
The shipped `control_loss_aversion` was calibrated before this certainty-equivalent
correction (October 2026) and should be recalibrated before it is interpreted.

## Social influence

The herding mechanism and the spatial network agents talk through. Agents are
placed in a two-dimensional space and treat everyone within
`social_interaction_radius` as a neighbour.

`social_opinion_kappa` is the sensitivity of an agent's opinion adjustment to
its neighbours'. `social_hold_tolerance` is a deadband: inside it the agent
holds rather than trading. The `social_gamma_*` bounds set how much weight an
agent places on social rather than private information, and the
`social_private_signal_std_*` bounds set the noise on its private signal — both
drawn per agent from the given interval.

## Market microstructure

Continuous persistent limit-order-book price formation, which is what makes
realised prices transaction prices rather than the output of a pricing rule.

`order_expiry_steps` bounds how long a resting order survives.
`cancellation_base_probability` is the baseline per-step chance a resting order
is withdrawn, and `cancellation_mispricing_sensitivity` adds pressure as that
order drifts further from the current price.

`market_order_probability` is the chance an activated agent demands immediacy
instead of posting a limit order, and `market_order_log_gap_threshold` is the
belief-versus-price gap above which it prefers immediacy anyway.
`market_order_price_collar` caps how far from the reference price a market order
may execute; `0.0` disables the collar and lets market orders sweep freely.

## Trading rules

Per-strategy thresholds, windows, risk aversion, and weight bounds.

**Fundamentalists** trade on the gap between price and fundamental value.
Thresholds are relative deviations in `[0, 1)`:
`fundamentalist_mispricing_threshold` is how far price must move from
fundamental before they act, and the stop-loss and take-profit thresholds close
a position on a relative loss or gain from the entry price.

**Chartists** trade technical signals. `chartist_short_window` must not exceed
`chartist_long_window`. `chartist_momentum_signal_threshold` is a deadband for
weak short-minus-long moving-average gaps; `0.0` preserves the historical
MA-crossover rule. `chartist_breakout_window` is a Donchian-style window —
breakout chartists compare the latest price with the previous window's high and
low, and equality counts as no breakout. `chartist_strategy_mode` selects the
rule, and `random` samples all four with the configured deterministic seed.

**Forecast horizons.** `fundamentalist_forecast_horizon` and
`chartist_forecast_horizon` set how many steps an agent expects its forecast to
take to play out. A fundamentalist's forecast is the whole log gap between
fundamental and price; a chartist's is its rule's signal. Position sizing
divides the forecast by the horizon, which gives a per-step expected return
measured in the same units as the per-step covariance of the Markowitz rule.
When CPT is on, it judges the trade over the same horizon, with volatility
scaled by the square root of the horizon. The valuation quotes do not change:
they remain the price the agent expects at the horizon.

With a horizon of 1, a whole mispricing is treated as a one-step return, so
almost every weight sits at its bound and risk aversion and the covariance have
little effect. Longer horizons make positions interior. Fundamentalist signals
are an order of magnitude larger than chartist signals in this model, which is
why the two have separate horizons. The shipped values are provisional until
calibrated, and both keys are in the calibration search space.

Note that `chartist_min_risky_weight = -0.30` matches `chartist_max_short_weight`,
so the effective sizing floor `max(min_risky_weight, -max_short_weight)` stays
at -0.30. Changing one without the other silently changes which bound binds.

**Noise traders** submit random-liquidity orders from zero-mean stochastic
beliefs rather than from valuation or technical signals. They are the lever for
studying noise-trader risk, liquidity demand, and the limits of arbitrage during
crisis-like regimes.

**Buy-and-hold** agents represent passive long-only investors: they accumulate
until their risky-asset share reaches `buy_hold_target_risky_weight`, then hold
until the run ends.

Every `*_max_short_weight` key is ignored when `short_selling_enabled` is false.

## Risk and costs

Short-sale constraints, active only when `short_selling_enabled = 1`:

- **Initial margin** limits maximum short exposure from agent equity.
- **Maintenance margin** triggers a forced buy-in when losses erode equity, and
  must not exceed the initial margin.
- **Borrowable supply ratio** caps aggregate short interest through share
  lending.

`transaction_cost_rate` is a proportional one-way cost paid by each executed
side, so `0.001` is 10 basis points and both buyer and seller pay it.
`transaction_cost_affects_decisions` is the interesting switch: with it off
agents pay costs but do not anticipate them, and with it on the cost enters the
valuation as a no-trade band. `transaction_cost_apply_to_forced_buy_ins`
decides whether margin-triggered buy-ins are charged too.

## Pipeline settings (not model parameters)

Nothing in this section changes the model. These keys control where artefacts go
and what runs afterwards, so they can be left alone while experimenting.

### Experiment archive

With `experiment_output_enabled = 1`, each run is archived under
`<experiment_root>/<experiment_name>/<run_id>/`, where the run id encodes the
key experimental settings numerically:

```
<timestamp>_<prospect_theory>_<prospect_heterogeneity>_<social_enabled>_
<short_sale>_<num_fundamentalists>_<num_chartists>_<num_noise_traders>_
<num_buy_and_hold_agents>_<time_steps>_<seed>
```

**This schema is frozen.** New parameters are recorded in `metadata.json` and
`summary_metrics.csv` instead of being appended to the folder name, because the
analysis layer already supports three historical run-id variants and must never
need a fourth.

Each run folder receives `config_used.cfg`, `config.json`, `metadata.json`,
`step_timeseries.csv`, `asset_timeseries.csv`, `agents_final.csv`,
`summary_metrics.csv`, `stylised_facts.csv`, `logs/run.log`, plus
`trade_ledger.csv` when the ledger is enabled and
`protagonist_timeseries.csv` when a protagonist is configured.
`experiment_manifest.csv` at the experiment level is the append-only master
index for comparing runs across behavioural-finance settings and seeds.

### Artefact paths

The `*_output` paths are the latest-run convenience destinations used when
experiment archiving is disabled. Archived runs override them and place every
artefact inside the run folder. Relative paths resolve from the config file's
own directory.

`trade_ledger_enabled` is worth keeping off for large calibration sweeps:
stylised-fact metrics are computed from aggregate step diagnostics, while the
full counterparty-level ledger can consume substantial memory and disk.
`asset_timeseries_enabled` writes the long-format per-(step, asset) series,
which is the authoritative multi-asset view.

### Post-processing

`database_output_enabled` imports each completed run into PostgreSQL using the
connection URL held in the environment variable named by `database_url_env`,
running the import under the interpreter named by `python_analysis_python`.
Nothing else happens automatically after a run: results are read by starting the
dashboard (`python -m abm_analysis web`), which the simulator never launches.
Keep it off until PostgreSQL is installed and `ABM_DATABASE_URL` is configured
locally. `database_prune_after_import` deletes the staging CSV/JSON artefacts
once an import succeeds.

---

## Editing the config

Unknown keys are **rejected**, with a "did you mean" suggestion — a typo fails
the run rather than silently taking a default. Absent keys are reported too, so
a configuration that quietly inherits a built-in default is visible rather than
invisible.

Validate without simulating:

```bash
build/debug/simulate --validate --config config/simulation.cfg
```

Regenerate the key reference after changing the C++ key registry (a test fails
if the committed file is stale):

```bash
build/debug/simulate --config-reference > docs/config_reference.md
```
