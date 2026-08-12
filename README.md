# BABM — Behavioural Agent-Based Market Model

BABM simulates a stock market populated by artificial traders. Each trader follows rules grounded in
behavioural finance theory — Cumulative Prospect Theory valuation, social influence and herding,
technical and fundamental trading rules — and orders meet in a continuous limit-order book. The
research question the code serves is whether such a market reproduces the **stylised facts** of real
financial markets (fat tails, volatility clustering, excess kurtosis, autocorrelation patterns),
especially under stress and crisis regimes.

The repository holds two halves of one pipeline:

| Half | Language | Responsibility |
| --- | --- | --- |
| `src/`, `app/` | C++17 | **The model engine.** Reads one config file, runs the simulation, writes a reproducible folder of CSV/JSON artefacts. |
| `analysis/python/abm_analysis/` | Python 3.11+ | **The analysis layer.** Reads those artefacts and produces econometric diagnostics, HTML reports, publication figures, calibration studies, seed-robustness verdicts, and an optional PostgreSQL store. |

The boundary is strict and deliberate: only the C++ side generates model data, and the Python side
never simulates — it launches the C++ binary and consumes its files.

You do not need to know how to code to run a simulation. Follow the steps below.

---

## 1. What you need first

On macOS or Linux:

- **Python 3.11 or newer** — runs the analysis and reports
- **CMake 3.25 or newer** and a **C++17 compiler** — build the simulator

On a Mac, open the **Terminal** app and run:

```bash
xcode-select --install
```

```bash
brew install cmake python@3.11
```

(Homebrew: https://brew.sh)

Optional extras, needed only for specific features:

- **Google Chrome** — for exporting figures as PNG/PDF/SVG (see [§8](#8-publication-ready-figures))
- **PostgreSQL** — for the optional database store (see [§9](#9-optional-postgresql-store))

---

## 2. One-time setup

Run each block from the repository root. You only do this once.

**1. Open the project folder**

```bash
cd path/to/BABM
```

**2. Create the Python environment**

This keeps the project's libraries separate from everything else on your computer:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

If it worked, your terminal prompt now starts with `(.venv)`. Then install the analysis package:

```bash
pip install --upgrade pip && pip install -r requirements.txt
```

**3. Build the simulator**

```bash
cmake --preset debug && cmake --build --preset debug
```

The first build takes a few minutes. When it finishes without errors, the executable is at
`build/debug/simulate`.

---

## 3. Run your first simulation

```bash
build/debug/simulate --config config/simulation.cfg
```

The simulator states what it is about to run, prints a progress bar with an estimated finish time,
then a grouped summary — and because `python_analysis_enabled = 1` in the config, builds an HTML
report and opens it in your browser.

The executable also accepts a bare path (`build/debug/simulate config/simulation.cfg`) and can run
with no argument at all when it finds `config/simulation.cfg` on its own. Other options:
`--validate` to check a config without running it (see [§4](#4-changing-the-model)),
`--config-reference` to print the key reference, and `--quiet-progress` to suppress the progress bar.
The progress bar is written to standard error, so redirecting standard output captures only the
summary and the artefact paths.

### What you get

Every run is archived in its own folder under `data/experiments/<experiment_name>/<run_id>/`:

| File | Contents |
| --- | --- |
| `step_timeseries.csv` | One row per step phase for the primary asset (single-asset view). |
| `asset_timeseries.csv` | Long format: one row per step phase **and** asset. The authoritative multi-asset series. |
| `trade_ledger.csv` | Counterparty-level execution audit rows (when `trade_ledger_enabled = 1`). |
| `agents_final.csv` | End-of-run wealth, holdings, strategy, and behavioural parameters per agent. |
| `summary_metrics.csv` | The run's headline scalars. |
| `stylised_facts.csv` | In-simulator screening block per traded asset. |
| `config.json`, `config_used.cfg` | The exact parameters that produced this run. |
| `metadata.json` | Build metadata: model version, git commit, dirty flag, compiler. |
| `logs/run.log` | The run log. |
| `python_analysis/index.html` | The generated report, plus `figures/`. |

`experiment_manifest.csv` at the experiment level is an append-only index of every run, joinable by
`run_id`.

The run-id folder name records the experiment settings in numeric form:

```text
YYYYMMDDHHMMSS_<prospect_theory>_<prospect_heterogeneity>_<social>_<short_sale>_<fundamentalists>_<chartists>_<noise_traders>_<buy_and_hold>_<time_steps>_<seed>
```

for example `20260711161424_1_1_0_1_340_300_100_100_2900_101`. Booleans are `1` (on) / `0` (off).
**This schema is frozen** — new parameters go into `metadata.json` and `summary_metrics.csv`, never
into the folder name, because the Python layer parses it.

> **Note on data:** `data/` is not tracked by git. Your results exist only on your computer — back up
> `data/experiments/` if you need them for your thesis.

---

## 4. Changing the model

Every parameter a user can change lives in one plain-text file: **`config/simulation.cfg`**. Open it
in any text editor, change the numbers, save, and run again. Unknown keys are rejected loudly, so a
typo fails the run rather than silently doing nothing — and the parser suggests the key you probably
meant.

Check a file before committing to a long run:

```bash
build/debug/simulate --validate --config config/simulation.cfg
```

This parses and validates without running the simulation or creating anything under `data/`. It
reports **every** problem in one pass — malformed lines, unknown keys, out-of-range values, and
constraints that span two keys — each with the offending value and the line to edit:

```text
config/simulation.cfg:158: error: Chartist short window (chartist_short_window) = 40 cannot exceed
                           long window (chartist_long_window) = 20.
config/simulation.cfg:201: error: Unknown config key 'social_hold_tolerence'.
                           Did you mean 'social_hold_tolerance'?
2 errors found.
```

When the file is valid it prints the resolved settings grouped by section, plus any keys the file did
not mention (those take their built-in defaults, and are also recorded in the run's `logs/run.log`).

**[docs/config_reference.md](docs/config_reference.md)** lists every key with its units, valid range,
and meaning. It is generated from the code, so it cannot drift:

```bash
build/debug/simulate --config-reference > docs/config_reference.md
```

One ordering rule: `assets = ...` must appear before any `asset.<name>.*` key, because per-asset
settings are resolved against an already-declared universe.

The main groups of settings, in the order they appear in the file:

| Group | Example keys | What it controls |
| --- | --- | --- |
| Assets | `assets`, `asset.alpha.*`, `asset_fundamental_correlation` | Per-asset fundamental process (GBM or random walk), initial price, tick size, endowment, volatility, drift, and cross-asset correlation. Both assets share the same functional form; neither is analytically privileged. |
| Population | `num_fundamentalists`, `num_chartists`, `num_noise_traders`, `num_buy_and_hold_agents` | The strategy mix. |
| Run control | `time_steps`, `warmup_steps`, `seed`, `agent_activity_rate` | Length, warm-up, reproducibility, activation rate. |
| Behavioural finance | `control_prospect_theory_enabled`, `control_loss_aversion`, `control_reference_point_mode`, `control_prospect_heterogeneity_enabled` | Cumulative Prospect Theory: loss aversion, value-function curvature, probability weighting, reference-point rule, and per-agent heterogeneity. |
| Social influence | `social_enabled`, `social_interaction_radius`, `social_opinion_kappa`, `social_gamma_*` | The herding mechanism and the spatial network agents talk through. |
| Microstructure | `market_microstructure`, `order_expiry_steps`, `cancellation_*`, `market_order_*`, `book_depth_levels` | Continuous double-auction order-book behaviour. |
| Trading rules | `fundamentalist_*`, `chartist_*`, `noise_trader_*`, `buy_hold_*` | Per-strategy thresholds, windows, risk aversion, and weight bounds. `chartist_strategy_mode` selects momentum / mean-reversion / breakout / RSI, or `random` to sample all four. |
| Risk and costs | `short_selling_enabled`, `short_sale_*`, `transaction_cost_rate`, `risk_free_rate` | Short-sale margin and borrow limits, proportional trading costs. |
| Output | `experiment_output_enabled`, `experiment_name`, `run_label`, `trade_ledger_enabled` | Archiving behaviour and which artefacts get written. |
| Post-processing | `python_analysis_enabled`, `python_analysis_python`, `database_output_enabled` | Whether the HTML report and the database import run automatically after a simulation. |

Everything below the `Pipeline settings (not model parameters)` banner in the file — artefact paths,
archiving, post-processing, database — controls where output goes rather than what the model does,
so it can be left alone while experimenting.

Setting `asset.beta.enabled = 0` collapses the configuration onto the single-asset model; every
report view then renders exactly as it did before multi-asset support.

---

## 5. The analysis commands

With the virtual environment active, the analysis layer runs as `python -m abm_analysis <command>`
(or through the installed `abm-analysis` script):

| Command | What it does |
| --- | --- |
| `run <run_dir>` | Diagnostics and a single-run HTML report. |
| `compare <experiment_dir>` | Cross-run comparison report for a whole experiment. |
| `replicate` | Runs one fixed config across a list of seeds, then builds the seed-robustness report. |
| `robustness <experiment_dir>` | Rebuilds the seed-robustness report for an already-archived experiment. |
| `calibrate` | Searches the parameter space against empirical benchmark returns. |
| `compress <experiment_dir>` | Gzips completed archives (the big per-row CSVs shrink ~5–10×; loaders read `.gz` transparently). |
| `db …` | Optional PostgreSQL: `init`, `import-run`, `import-experiment`, `import-benchmarks`, `import-all`, `validate`, `inspect-run`. |
| `web` | Opens the local dashboard for browsing every archived run and its market statistics ([§5.1](#51-the-market-statistics-dashboard)). |

Every command supports `--help`. Report-producing commands share `--phase`, `--price-column`,
`--output-dir`, `--export-images` / `--no-export-images`, and `--figure-formats`.

```bash
.venv/bin/python -m abm_analysis run data/experiments/demo/<run_id>
```

```bash
.venv/bin/python -m abm_analysis compare data/experiments/demo
```

### 5.1 The market-statistics dashboard

The commands above write reports to disk — that is what makes them citable, but it also means
answering "what did that run actually look like?" costs a report build. The dashboard is the quick
way in: one command, and every archived run is browsable in your browser.

```bash
.venv/bin/python -m abm_analysis web
```

It prints an address (`http://127.0.0.1:8000/`) and opens it. Pick a run on the left.

**Every traded market gets its own column.** A run configured with `assets = alpha, beta` is two
markets, and the page reports both side by side rather than only the primary asset. That matters:
on the demo two-asset run, alpha's excess kurtosis is 4.00 against beta's 0.17, and beta ends 970%
above its fundamental while alpha ends 31% below — differences invisible in a single-asset view.

For the selected run the page shows:

- **Stylised-fact verdicts**, one per market — absence of linear autocorrelation, fat tails, and
  volatility clustering, each with the test statistic behind it (Ljung–Box, Jarque–Bera, ARCH-LM,
  GARCH). A run can reproduce a fact in one market and not the other, and the cards say so.
- **Return distribution** — observations, mean, volatility, skewness, excess kurtosis, Jarque–Bera.
- **Serial dependence** — lag-1 autocorrelation, Ljung–Box and ARCH-LM minimum p-values, and the
  GARCH(1,1) α, β, and persistence.
- **Market outcomes** — final price against the fundamental, mispricing, maximum drawdown, traded
  volume, mean bid–ask spread, and allocative efficiency.
- **Cross-asset** (two or more markets only) — realised rolling return correlation against the
  configured fundamental ρ, and the relative price ratio.
- **Agents** — population size, strategy count, wealth Gini, and a per-strategy table of agent
  count, mean/median/s.d. final wealth, mean wealth change, mean trades, and mean traded volume,
  with the final-wealth distribution drawn per strategy.
- **Charts** — price against fundamental, the log-return series, the return distribution against a
  fitted Gaussian, and the autocorrelation of raw, absolute, and squared returns. Colour identifies
  the market; the price chart has a `Level | Indexed` switch so markets at different price levels
  share one axis, and the autocorrelation panel switches between raw, |r|, and r².

The `Phase` and `Price column` selectors at the top re-run the diagnostics on a different window or a
different price series, the same way `--phase` and `--price-column` do for the report commands.

Four things are worth knowing:

- **It is read-only.** The dashboard never simulates and never writes to `data/`, so it is safe to
  leave open while a long experiment is running.
- **The numbers are the report's numbers.** Every statistic is recomputed by the same
  `abm_analysis.statistics` functions the static reports use, so the two cannot disagree. Where a
  figure comes straight from the simulator's `summary_metrics.csv` instead, it is labelled.
- **It finds runs wherever they are.** Anything under `data/` holding a `step_timeseries.csv` is
  listed, so experiments, calibration studies, and `data/latest` all appear without configuration.
- **It states its own limits.** The simulator leaves `simulation_step` blank on initial and warm-up
  rows of `asset_timeseries.csv`, so the per-asset panels cover the simulation phase only, and the
  warm-up phase falls back to the primary market. Per-asset return diagnostics also use the
  simulator's own `log_return` column, so `Price column` changes the price chart but not those
  statistics. The footer of every run says which artefact was read and notes any such caveat.

Useful options: `--data-root <dir>` to browse a different archive, `--port <n>` if 8000 is taken, and
`--no-browser` to leave the browser alone. The server binds to `127.0.0.1`, so unpublished results
are not exposed on the network.

---

## 6. Calibrating against real market data

Instead of guessing parameter values by hand, calibration tries many combinations automatically
(Optuna TPE search) and keeps the ones whose simulated returns are closest to real market data. The
empirical series live in `data/stock_data/candle_chart/` and are registered in
`config/benchmarks/manifest.csv` (`SPX`, `NAQ`, `FTS100`, `VINFAST`).

**1. Build the optimised simulator** — calibration runs hundreds of simulations:

```bash
cmake --preset release && cmake --build --preset release
```

**2. Start the study.** A ready-made search space is included:

```bash
.venv/bin/python -m abm_analysis calibrate \
  --base-config config/simulation.cfg \
  --search-space config/calibration/search_space.json \
  --simulator build/release/simulate \
  --benchmark-series SPX \
  --trials 50 \
  --validation-seeds 55,101:109
```

Be patient — this is one simulation per trial. `--validation-seeds` re-runs the best candidates
across several seeds so the winner is robust rather than a one-seed fluke: use at least 5 seeds, 10
or more recommended. Candidates are ranked by **fit × seed-robustness pass rate**, not fit alone.
Defaults for trials, seeds, and scoring live in `config/calibration/calibration_settings.json`.

**3. Read the results** in `data/calibration/<study_name>/`:

| Output | Contents |
| --- | --- |
| `best_config.cfg` | The winning parameters, saved as a ready-to-run config file. |
| `calibration_trials.csv` | Every combination tried and its score. |
| `calibration_report/` | HTML ranking report explaining *why* the winner won. |
| `best_runs_robustness_report/` | Seed-stability report for the top candidates. |
| `holdout_validation/` | Out-of-sample checks. |

**4. Run the tuned model:**

```bash
build/debug/simulate --config data/calibration/<study_name>/best_config.cfg
```

---

## 7. Checking robustness across seeds

To test whether a result holds generally rather than being an artefact of one random draw, replicate
the same configuration across many seeds:

```bash
.venv/bin/python -m abm_analysis replicate \
  --base-config config/simulation.cfg \
  --simulator build/release/simulate \
  --seeds 1:30
```

Seeds run in parallel across CPU cores; pass `--jobs 1` for sequential execution with the live
progress bar, or `--jobs N` to cap the worker count.

This creates a `seed_robustness_<timestamp>` folder under `data/experiments/` with one run per seed
plus a report at `robustness_reports/latest_seed_robustness/index.html` containing cross-seed
distribution tests, stylised-fact success rates, seed-convergence curves, and a pass / borderline /
fail verdict table with fixed, literature-anchored thresholds.

The report can be regenerated for any archived experiment without re-running the simulations:

```bash
.venv/bin/python -m abm_analysis robustness data/experiments/<experiment_name>
```

---

## 8. Publication-ready figures

Every report also saves each chart as standalone files in a `figures/` folder next to `index.html`:
a 300 DPI PNG plus vector PDF and SVG, styled for print (serif fonts, white background, sized to a
full LaTeX text width). `figure_index.csv` lists every exported file. In a thesis or paper, include
the PDF directly:

```latex
\includegraphics[width=\textwidth]{.../python_analysis/figures/price_timeseries.pdf}
```

Static export uses Kaleido, which needs Google Chrome. If Chrome is missing, the command stops with
instructions — install Chrome, download a private copy with
`.venv/bin/python -c "import kaleido; kaleido.get_chrome_sync()"`, or pass `--no-export-images` (the
interactive HTML report is always produced either way). To export only what you need, pass
`--figure-formats pdf` for LaTeX-only output or `--figure-formats png,pdf` to drop the SVG copies.

---

## 9. Optional: PostgreSQL store

The CSV/JSON artefacts are treated as staging output; the database is the queryable research store.
It is entirely optional and disabled by default.

```bash
export ABM_DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/abm"
```

```bash
.venv/bin/python -m abm_analysis db init
```

```bash
.venv/bin/python -m abm_analysis db import-experiment data/experiments/demo
```

`ABM_DATABASE_URL` is a SQLAlchemy URL; every `db` subcommand also accepts an explicit
`--database-url`. Set `database_output_enabled = 1` in `config/simulation.cfg` to import each run
automatically as it finishes; `database_prune_after_import` then deletes the staging files once the
import succeeds. Imports are content-hashed, so re-imports are detectable and reproducible. Check an
import with `db validate` (compares source CSV row counts against the database) or `db inspect-run`.

---

## 10. Repository layout

```text
app/simulate/main.cpp   Executable entry point (forwards argc/argv only)
src/                    The C++ model engine, one directory per domain
  Application/            CLI parsing, run coordination, console summary, Python hand-off
  Config/                 Config schema, parsing, setting appliers, validation
  Market/ OrderBook/      Fundamental-value process, market state, limit-order book
  BehaviouralFinance/     Cumulative Prospect Theory and per-agent preference sampling
  Agent/ AgentStrategy/   Agents plus fundamentalist, chartist, noise-trader, buy-and-hold rules
  Simulation/             The engine and its collaborators (scheduling, herding, clearing, risk)
  Metrics/ Results/       Stylised-fact screening, allocative efficiency, the run-result DTO
  Output/ DataManagement/ Experiment/   Artefact writers, archive schema, run-folder policy
  RandomGenerator/ Utility/ RiskManagement/   Seeded RNG, numerics, tick pricing, short-sale controls
analysis/python/abm_analysis/
  cli.py                   The console-script entry point; everything else CLI-shaped is below
  commands/                One module per subcommand, the parser, and the options they share
  archive/                 Reading run archives, run-ids, manifests, benchmarks, compression
  statistics/              Stylised-fact tests, stress diagnostics, robustness verdicts, convergence
  calibration/             Optuna study, scoring, execution, seed validation, trial worker
  plots/ report/           Figures and the HTML/PDF report builders
  database/                Optional PostgreSQL schema, imports, exports, validation
  web/                     Read-only local dashboard: run catalogue, statistics API, single page
config/                 simulation.cfg, calibration search space, benchmark manifest
data/                   Simulation output, calibration studies, empirical data (git-ignored)
docs/                   Code map, Mermaid diagrams, and the LaTeX formalism
tests/cpp/              C++ CTest suites, mirroring src/
tests/python/           Python pytest suite, mirroring analysis/python/
```

---

## 11. Tests and CI

GitHub Actions runs three jobs on every push and pull request; reproduce them locally before
committing.

**C++ build and tests** (warnings are errors in CI):

```bash
cmake --preset debug -DABM_WARNINGS_AS_ERRORS=ON && cmake --build --preset debug && ctest --preset debug
```

**Formatting** — every tracked C++ file must match `.clang-format`:

```bash
git ls-files 'src/*.h' 'src/*.cpp' 'tests/*.h' 'tests/*.cpp' 'app/*.cpp' | xargs clang-format --style=file --dry-run --Werror
```

**Python tests:**

```bash
.venv/bin/pip install -e ".[test]" && .venv/bin/pytest
```

When changing simulation logic, order-book code, or memory-sensitive output code, also run the
sanitizer build (AddressSanitizer + UndefinedBehaviorSanitizer):

```bash
cmake --preset sanitizers && cmake --build --preset sanitizers && ctest --preset sanitizers
```

`.clang-tidy` is advisory — editors and local runs read it, CI does not enforce it.

---

## 12. Reproducibility

- Every stochastic draw goes through a seeded RNG wrapper, so a config plus its `seed` reproduces a
  run exactly. The fundamental-value process uses `seed` and the agent side uses `seed + 1`, so
  changing agent behaviour cannot perturb the fundamental path.
- Each run archives the exact config that produced it (`config_used.cfg`, `config.json`) together
  with the model version, git commit, dirty flag, and compiler in `metadata.json`.
- Four cross-language contracts hold the pipeline together: the config key set, the frozen run-id
  schema, the CSV column layout, and the CMake source lists.
  `tests/python/test_schema_sync.py` fails deliberately when a C++ CSV column changes without the
  matching Python and database update.

---

## 13. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Coming back to the project later | Reactivate the environment first: `source .venv/bin/activate` |
| "command not found" | Make sure you are in the repository root (`cd path/to/BABM`). |
| Changed C++ code, results unchanged | Rebuild: `cmake --build --preset debug` |
| Config error mentioning a key | Run `build/debug/simulate --validate --config <file>` — it lists every problem at once with the line to edit, and suggests corrections for misspelled keys. |
| Figure export fails | Chrome is missing; see [§8](#8-publication-ready-figures) or pass `--no-export-images`. |
| Disk filling up | Compress finished experiments: `.venv/bin/python -m abm_analysis compress data/experiments/<name>` |

---

## 14. Further documentation

| Document | Contents |
| --- | --- |
| [docs/config_reference.md](docs/config_reference.md) | Every configuration key with its units, valid range, and meaning. Generated from the code. |
| [docs/code_map.md](docs/code_map.md) | File-by-file guide: what every source file does and how they connect. |
| [docs/baselines.md](docs/baselines.md) | Recorded baseline results, used to detect unintended behavioural drift. |
| `docs/*.mmd` | Mermaid diagrams: class architecture, build structure, data management, simulation flow, agent decision flow, sequence diagram. |
| [AGENTS.md](AGENTS.md) | Research context and the working rules for contributors (naming, reproducibility, required commands). |
| `docs/formalism.tex` | The model's mathematics — the paper-side counterpart of the code. |
