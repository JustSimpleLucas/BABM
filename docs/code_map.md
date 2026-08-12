# Code Map — What Every File Does and How They Connect

This document is a file-by-file guide to the repository. It covers what each
source file is responsible for and which other files it depends on or feeds
into. It complements the Mermaid diagrams in `docs/` (which show the same
structure graphically) and `README.md` (which shows how to *run* the project).

Two languages, one pipeline:

- **C++ (`src/`, `app/`)** — the model engine. It reads a config file, runs the
  agent-based simulation, and writes a folder of reproducible CSV/JSON
  artefacts.
- **Python (`analysis/python/abm_analysis/`)** — the analysis layer. It reads
  those artefacts and produces diagnostics, HTML reports, publication figures,
  calibration studies, seed-robustness verdicts, and an optional PostgreSQL
  database.

The boundary between the two is deliberate and strict: **the C++ side is the
only thing that generates model data; the Python side never simulates**, it only
launches the C++ binary and consumes its files.

---

## 1. Top-level orientation

| Path | What it is |
| --- | --- |
| `README.md` | Non-technical run instructions: install, build, simulate, configure, analyse, calibrate, replicate, plus repository layout and CI commands. |
| `AGENTS.md` | Research context and working rules (naming, reproducibility, run-id schema, required build/test commands). The run-id folder schema documented here is **frozen** — Python parsing depends on it. |
| `CMakeLists.txt` | Defines the static-library targets, their dependency order, the `simulate` executable, and the five CTest test executables. |
| `CMakePresets.json` | The `debug`, `release`, and `sanitizers` presets and their build dirs (`build/debug`, `build/release`, `build/sanitizers`). |
| `cmake/AbmCompilerOptions.cmake` | `abm_apply_project_warnings()` / `abm_apply_project_sanitizers()` — shared warning and ASan/UBSan flags applied to every target. |
| `cmake/AbmBuildMetadata.cmake` | Captures model version, git commit, and dirty flag at configure time; these become compile definitions consumed by the output layer so every run records the exact build that produced it. |
| `src/CMakeLists.txt` | Adds every domain directory. Each `src/<Domain>/CMakeLists.txt` then names the target its own sources belong to via `target_sources()`, so **adding a `.cpp` means editing that directory's list**, not a central one. |
| `pyproject.toml` | Python package definition (`abm-analysis`), dependency pins, the `abm-analysis` console script, and the pytest configuration. |
| `requirements.txt` | A one-line pointer (`-e .[test]`) so `pip install -r` works. Versions live only in `pyproject.toml`, so there is no second list to drift. |
| `.github/workflows/ci.yml` | CI, three jobs: **build-test** configures the debug preset with warnings-as-errors, builds, and runs `ctest`; **format** fails on any C++ file that differs from `.clang-format`; **python-test** installs the analysis package and runs `pytest`. |
| `.clang-format` | C++ formatting rules (LLVM base, 4-space indent, 100-column limit). Enforced by the `format` CI job; the whole tree is compliant. |
| `.clang-tidy` | Static-analysis rules for editors and local runs (`bugprone`, `cppcoreguidelines`, `modernize`, `performance`, `readability`, with the noisiest checks disabled). Advisory — `WarningsAsErrors` is empty and CI does not run it. |
| `docs/formalism.tex` | The LaTeX write-up of the model's mathematics — the paper-side counterpart of the code. The only `.tex` source tracked; build products (`.toc`, `.aux`, …) and scratch drafts stay local. |
| `docs/*.mmd` | Mermaid diagrams: class architecture, build structure, data management, simulation flow, agent decision flow, sequence diagram. |
| `docs/baselines.md` | Recorded baseline results used to detect unintended behavioural drift. |

### Directories that hold data, not code

| Path | What it is |
| --- | --- |
| `config/simulation.cfg` | **The** central parameter file. Every model assumption a user can change lives here. |
| `config/calibration/search_space.json` | Which parameters calibration may vary and over what ranges. |
| `config/calibration/calibration_settings.json` | Default calibration run settings (trials, seeds, scoring options). |
| `config/benchmarks/manifest.csv` | Registry of empirical benchmark series (e.g. SPX) used for validation and calibration targets. |
| `config/smoke/sql_import_smoke.cfg` | Tiny config used to smoke-test the database import path. |
| `data/experiments/<name>/<run_id>/` | One folder per simulation run, holding `step_timeseries.csv`, `asset_timeseries.csv`, `trade_ledger.csv`, `agents_final.csv`, `summary_metrics.csv`, `stylised_facts.csv`, `config.json`, `metadata.json`, `run.log`, plus generated `python_analysis/`. |
| `data/experiments/<name>/experiment_manifest.csv` | Append-only index of every run in that experiment, joinable by `run_id`. |
| `data/latest/` | Convenience copy of the most recent run. |
| `data/calibration/<study>/` | Calibration outputs: `best_config.cfg`, `calibration_trials.csv`, robustness report. |
| `data/stock_data/` | Empirical market data (`.xlsx` + converted `candle_chart` CSVs) used as calibration and validation targets. |

`data/` is git-ignored — results exist only on the local machine.

---

## 2. The C++ simulator

### 2.1 Layered dependency order

Libraries are wired in `CMakeLists.txt` so that dependencies flow strictly
downward. Nothing in a lower layer knows about a higher one:

```
                simulate (app/simulate/main.cpp)
                          |
                     abm_application
             /       /        |        \
     abm_archive  abm_output  abm_simulation  abm_analysis
          |          |            |               |
          |          |         abm_agents         |
          |          |            |               |
          |          |   abm_behavioural_finance  |
           \         \            |              /
                    abm_market  abm_config  abm_results
                            \      |      /
                              abm_utility
```

Read that as: utilities know nothing; config knows utilities; market knows
utilities; agents know behaviour + config + market; the simulation engine knows
agents; output knows results and config; the application layer knows everything
and glues it together.

### 2.2 Entry point and application layer (`abm_application`)

| File | Function | Connects to |
| --- | --- | --- |
| `app/simulate/main.cpp` | The executable's entry point. Deliberately trivial — it only forwards `argc`/`argv`. | `Application/SimulationApplication.h` |
| `src/Application/CliOptions.{h,cpp}` | Parses the command line into a result object; represents `--help` and usage errors as early exits so config loading stays separate from execution. Accepts `--config <path>`, a bare path, or nothing. | Used by `SimulationApplication` |
| `src/Application/SimulationApplication.{h,cpp}` | The run coordinator: parse CLI → load and validate config → construct `SimulationEngine` → run with a progress bar → hand the result to the archive workflow → print a console summary → optionally invoke Python. | `CliOptions`, `SimulationEngine`, `ExperimentDataWorkflow`, `ConsoleReporter`, `PythonAnalysisRunner`, `StylisedFactMetrics`, `ConsoleProgressBar`, `ProcessMemoryUsage` |
| `src/Application/ConsoleReporter.{h,cpp}` | Prints the compact terminal summary of a finished run. Kept separate from artefact export: console output is for humans, files are the research record. | Reads `SimulationRunResult` |
| `src/Application/PythonAnalysisRunner.{h,cpp}` | Optional post-processing step: shells out to the Python package to import artefacts into PostgreSQL (when enabled) and build the HTML report that opens in the browser. | Bridge to `analysis/python/` |

### 2.3 Configuration (`abm_config`)

This module turns `config/simulation.cfg` into validated, typed parameter
objects. It is split into a *schema* (headers holding plain records) and a
*parsing/validation* pipeline.

**Schema — the parameter records:**

| File | Function |
| --- | --- |
| `src/Config/SimulationConfig.h` | Stable facade that aggregates every domain config record. Older code includes just this; new code should include the narrower header it actually needs. |
| `src/Config/ModelConfig.h` | The complete set of model parameters for one run (population sizes, steps, seed, warm-up, and so on). |
| `src/Config/MarketConfig.h` | Per-asset market parameters: the GBM fundamental-value process, volatility, drift, initial price, cross-asset correlation, tick size, transaction costs. All declared assets share the same functional form so no asset is analytically privileged. |
| `src/Config/StrategyConfig.h` | Strategy-side parameters, including the chartist mode selector (momentum / mean-reversion / breakout / RSI) and per-strategy thresholds. |
| `src/Config/BehaviouralConfig.h` | Cumulative Prospect Theory parameters and the reference-point mode (fixed anchor vs. per-agent personal reference state). |
| `src/Config/OutputConfig.h` | Where artefacts go and whether one-folder-per-run archiving is enabled. |

**Parsing and validation pipeline:**

| File | Function |
| --- | --- |
| `src/Config/SimulationConfigIO.{h,cpp}` | Locates `config/simulation.cfg` (working directory first, then paths relative to the executable) and drives file reading. |
| `src/Config/SimulationConfigParsing.{h,cpp}` | Low-level typed value parsing (`parseBoolValue`, `parseDoubleValue`, …), each call carrying the key name and source line so errors are traceable to a config line. |
| `src/Config/SimulationConfigSettingAppliers.{h,cpp}` | Defines `ConfigSetting` (key + value + source location) and dispatches each parsed setting through an array of 16 applier functions until one claims the key. Unknown keys therefore fail loudly. |
| `…SimulationSettings.cpp` | Appliers for core simulation keys and the `asset.*` per-asset key family. |
| `…StrategySettings.cpp` | Appliers for fundamentalist / chartist / noise-trader / buy-and-hold keys. |
| `…BehaviouralSettings.cpp` | Appliers for `control_*` keys: prospect theory, heterogeneity, social influence, short selling. |
| `…OutputSettings.cpp` | Appliers for `experiment_output_*` keys. |
| `src/Config/SimulationConfigValidation.{h,cpp}` | Checks feasibility of the fully assembled config (positive counts, admissible probabilities, consistent asset lists). Separate from engine construction so configs can be tested without running a simulation. |

### 2.4 Market microstructure (`abm_market`)

| File | Function | Connects to |
| --- | --- | --- |
| `src/Market/Market.{h,cpp}` | The market state: per-asset realised price history and latent fundamental-value history, addressed by asset index, plus the moving-average / volatility / RSI statistics computed over them. Passive and copyable — it draws no random numbers and stores only what the fundamental process and the order book produced. | `FundamentalValueProcess`, `LimitOrderBook`, `CovarianceEstimator` |
| `src/Market/FundamentalValueProcess.{h,cpp}` | The latent fundamental-value dynamics: arithmetic random walk or geometric Brownian motion, with equicorrelated cross-asset innovations built from the closed-form one-factor square root of the equicorrelation matrix. Owns the fundamental random stream, seeded from `config.seed` — deliberately separate from the agent-side engine (`config.seed + 1`) so agent-side changes cannot perturb the fundamental path. | `Market`, `RandomGenerator`, `MarketConfig`; driven by `MarketProcess` |
| `src/OrderBook/Order.h` | The `Order` record and `OrderType` side enum. Side is kept explicit rather than implied by a signed quantity so CSV exports can distinguish buyer from seller unambiguously. | Used everywhere orders flow |
| `src/OrderBook/LimitOrderBook.{h,cpp}` | The continuous double-auction engine: resting-order storage, price-time priority matching, cancellation, and a visible-state snapshot (best bid/ask, depth). | `Order`, `Market` |
| `src/Market/CovarianceEstimator.{h,cpp}` | Rolling sample covariance of per-asset one-period log returns, using a common trailing window across assets. This is the risk input to portfolio choice. | Feeds `PortfolioOptimizer` via `SimulationEngine` |
| `src/RiskManagement/ShortSaleRiskControls.{h,cpp}` | Clips sell orders by short-sale margin and borrow availability. | Used by `OrderCollector` / `RiskControlService` |

### 2.5 Behavioural finance (`abm_behavioural_finance`)

| File | Function |
| --- | --- |
| `src/BehaviouralFinance/ProspectTheory.{h,cpp}` | The Cumulative Prospect Theory valuation: the value function over gains/losses relative to a reference point, and the probability weighting function. This is the core behavioural mechanism the thesis is about. |
| `src/BehaviouralFinance/ProspectPreferenceSampler.{h,cpp}` | Assigns CPT preferences to agents. Homogeneous runs give everyone the configured parameters; heterogeneous runs draw bounded per-agent preferences from deterministic random streams, so diversity never breaks seed reproducibility. |

### 2.6 Agents and strategies (`abm_agents`)

| File | Function |
| --- | --- |
| `src/Agent/Agent.{h,cpp}` | The agent: cash, per-asset inventory, wealth accounting, CPT preferences, and the endowment record used at population creation. |
| `src/Agent/AgentAction.h` | The buy / sell / hold decision enum, kept distinct from `OrderType` because only buy and sell can become executable orders. |
| `src/AgentStrategy/TradingStrategy.h` | The strategy interface plus the shared per-step market view handed to every portfolio-optimising strategy. All concrete strategies below implement this. |

**Concrete strategies:**

| File | Function |
| --- | --- |
| `FundamentalistStrategy.{h,cpp}` | Trades on the gap between price and latent fundamental value, with stop-loss / take-profit controls. |
| `ChartistStrategy.{h,cpp}` | Shared base and shared parameters for the four technical rules. |
| `MomentumChartistStrategy.{h,cpp}` | Moving-average crossover momentum rule. |
| `MeanReversionChartistStrategy.{h,cpp}` | Reversal rule over a configured horizon. |
| `BreakoutChartistStrategy.{h,cpp}` | Price-channel breakout rule. |
| `RelativeStrengthIndexChartistStrategy.{h,cpp}` | RSI oscillator rule with explicit 30/70 thresholds. |
| `ChartistStrategyFactory.{h,cpp}` | Builds the right concrete chartist from config and performs the random strategy sampling — so population construction never hard-codes the class list. |
| `NoiseTraderStrategy.{h,cpp}` | Uninformed random liquidity: demand driven by stochastic erroneous beliefs. |
| `BuyAndHoldStrategy.{h,cpp}` | Passive long-only target weight, then hold. Ignores signals, social opinion, and CPT — the deliberate control condition. |

**Shared portfolio machinery used by the strategies:**

| File | Function |
| --- | --- |
| `MeanVarianceUtility.{h,cpp}` | The one-period mean-variance rule, kept explicit because risk aversion is a research-critical assumption. |
| `AssetAllocationLine.{h,cpp}` | Converts expected return, risk-free rate, and volatility into a bounded risky-asset weight — the single-asset sizing rule, separated from belief formation. |
| `PortfolioOptimizer.{h,cpp}` | The multi-asset Markowitz solve: expected excess log returns and a covariance matrix in, per-asset weights out, with per-asset weight intervals applied after the unconstrained solution. |
| `OrderSizing.{h,cpp}` | Turns a target portfolio weight into a target holding, honouring long-only floors, short-exposure allowances, and forced liquidation. |
| `StrategyMarketHelpers.h` | Small shared helpers, notably safe relative-difference computation near zero prices. |

### 2.7 Simulation engine (`abm_simulation`)

`SimulationEngine` is the orchestrator; every modelling assumption lives in one
of its collaborators, not in the controller itself.

| File | Function |
| --- | --- |
| `src/Simulation/SimulationEngine.{h,cpp}` | Owns the config, market, fundamental process, agent-side RNG, and all collaborators below. Validates config, builds the population, warms up the market, then loops: schedule → collect orders → clear → apply risk controls → record diagnostics. Returns a `SimulationRunResult`. |
| `src/Simulation/SimulationState.h` | The shared state records: `AgentRecord` (participant + swappable active strategy), `SimulationPopulation` (storage + stable ID lookup), `SocialNeighbor` (weighted network edge), and `MicrostructureStepResult` (per-step execution and book diagnostics). |
| `src/Simulation/PopulationFactory.{h,cpp}` | Builds the heterogeneous population: strategy mix, CPT preference sampling, endowments, and stable ID assignment. Separated from the engine so population composition is testable on its own. |
| `src/Simulation/MarketProcess.{h,cpp}` | Runs the pre-simulation warm-up that establishes initial price history, returning the final warm-up price state, and drives `FundamentalValueProcess` for each step's fundamental advance. Also handles risk-free cash accrual, the last-trade price rule, and agent wealth refreshes. |
| `src/Simulation/SimulationClock.{h,cpp}` | Step accounting and progress callbacks. Contains no market logic, so experiment timing is testable independently of behaviour. |
| `src/Simulation/AgentActivationScheduler.{h,cpp}` | Draws which agents act this period and in what order — the stochastic activation assumption. |
| `src/Simulation/SocialInfluenceModel.{h,cpp}` | Builds the synthetic social network and updates agent opinions — the herding mechanism, kept outside the engine so it can be tested without market clearing. |
| `src/Simulation/OrderCollector.{h,cpp}` | Turns scheduled active agents into fully annotated order submissions: calls each strategy, applies sizing, tick pricing, and risk clipping. |
| `src/Simulation/MarketClearingEngine.{h,cpp}` | Applies resting-order lifecycle rules (staleness, infeasibility, anti-livelock cancellation) and then runs matching through the order books. |
| `src/Simulation/RiskControlService.{h,cpp}` | Broker-side enforcement, in particular forced buy-ins of infeasible short positions, aggregated per step. |
| `src/Simulation/DiagnosticsRecorder.{h,cpp}` | Records each completed step into the time-series and ledger structures that later become CSV. |

### 2.8 Results, analysis, and output

| File | Function |
| --- | --- |
| `src/Results/SimulationRunResult.h` (`abm_results`) | The immutable output DTO of one run: step series, per-asset series, trade ledger, final agent states, and aggregate diagnostics. This is the contract between the engine and everything downstream. |
| `src/Metrics/StylisedFactMetrics.{h,cpp}` (`abm_metrics`) | Lightweight in-simulator screening metrics for fat tails, volatility clustering, autocorrelation, and kurtosis — computed per asset. Deliberately not the inferential layer; the Python side does the formal testing. |
| `src/Metrics/AllocativeEfficiency.{h,cpp}` | Smith-style double-auction efficiency, treating strategy-generated limit prices as reservation values. |

**Artefact writing (`abm_output`):**

| File | Function |
| --- | --- |
| `src/Output/RunArtifactWriter.{h,cpp}` | The single entry point for durable output. Calls every specialised writer below and returns write metadata. This class *is* the file-format boundary. |
| `src/Output/OutputSerialization.{h,cpp}` | Shared low-level formatting: CSV escaping, fixed-precision doubles, JSON escaping, enum-to-label mapping, and `buildNormalizedConfigJson()` which produces `config.json`. |
| `src/Output/StepTimeseriesCsvWriter.{h,cpp}` | `step_timeseries.csv` — one row per step phase for the primary asset (a projection of the long-format artefact). |
| `src/Output/AssetTimeseriesCsvWriter.{h,cpp}` | `asset_timeseries.csv` — the long format, one row per phase row *and* asset. The authoritative multi-asset series. |
| `src/Output/TradeLedgerCsvWriter.{h,cpp}` | `trade_ledger.csv` — counterparty-level execution audit rows (optional, enabled by flag). |
| `src/Output/AgentSnapshotCsvWriter.{h,cpp}` | `agents_final.csv` — end-of-run per-agent wealth, holdings, strategy, and behavioural parameters. |
| `src/Output/RunSummaryCsvWriter.{h,cpp}` | `summary_metrics.csv` — the run's headline scalars. |
| `src/Output/StylisedFactCsvWriter.{h,cpp}` | `stylised_facts.csv` — one screening block per traded asset, so every market gets its own verdict. |
| `src/Output/RunMetadataWriters.{h,cpp}` | `config.json` and `metadata.json`, the latter embedding the build metadata from `AbmBuildMetadata.cmake`. |
| `src/Output/ExperimentManifestWriter.{h,cpp}` | Appends the finished run to `experiment_manifest.csv`, storing identifiers and comparable summary fields (not duplicated paths) so sweeps stay compact. |

**Archive workflow (`abm_archive`):**

| File | Function |
| --- | --- |
| `src/Experiment/ExperimentRunManager.{h,cpp}` | Creates the reproducible folder layout and generates the frozen run-id folder name (`YYYYMMDDHHMMSS_<flags…>_<seed>`). Centralises archival policy so the executable never needs to know it. |
| `src/DataManagement/RunArchiveSchema.{h,cpp}` | Declares which files a complete run archive must contain — the machine-checkable output contract. |
| `src/DataManagement/ExperimentDataWorkflow.{h,cpp}` | Coordinates one run's data lifecycle: prepare the archive layout, validate against the schema, delegate writing to `RunArtifactWriter`. |

### 2.9 Utilities (`abm_utility`)

| File | Function |
| --- | --- |
| `src/RandomGenerator/RandomGenerator.{h,cpp}` | The deterministic RNG wrapper. Every stochastic draw goes through it, which is what makes runs reproducible from a seed. |
| `src/Utility/CholeskyFactorization.{h,cpp}` | Dense symmetric matrix type and Cholesky solve — used for correlated asset shocks and for the portfolio optimisation solve. |
| `src/Utility/NumericValidation.{h,cpp}` | Rejects NaN/infinity at module boundaries so non-finite values cannot silently propagate through prices, wealth, and utility scores. |
| `src/Utility/OrderPricing.{h,cpp}` | Quantises limit prices to the tick grid, rounding buys down and sells up so rounding never makes an agent more aggressive than intended. |
| `src/Utility/TransactionCosts.h` | Proportional one-way cost rate and the per-side cash cost of an execution. |
| `src/Utility/SimulationConstants.h` | Shared numerical safeguards, notably the minimum admissible positive price. |
| `src/Utility/ConsoleProgressBar.{h,cpp}` | Terminal progress bar. Explicitly touches no model state, so console behaviour cannot affect results. |
| `src/Utility/ProcessMemoryUsage.{h,cpp}` | OS process-memory diagnostic for interactive reporting; never enters archived output. |

### 2.10 C++ tests (`tests/cpp/`)

Five separate CTest executables, each with its own `…TestMain.cpp`. All of them
share `TestSupport.{h,cpp}` (assertion helpers, temporary directories, config
fixtures).

| Executable | Sources | Covers |
| --- | --- | --- |
| `abm_model_tests` | `CoreModelTestMain.cpp` + `BuyAndHoldStrategyTests`, `ChartistStrategyTests`, `NoiseTraderStrategyTests`, `PortfolioOptimizerTests`, `ProspectTheoryTests`, `LimitOrderBookTests`, `RandomMarketRiskTests`, `SimulationComponentTests`, `SimulationIntegrationTests` | Strategy behaviour, CPT valuation, order-book matching, risk controls, engine collaborators, and an end-to-end simulation run. |
| `abm_config_parsing_tests` | `ConfigParsingTestMain.cpp`, `ConfigParsingTests.cpp` | Key parsing, the applier dispatch, `asset.*` keys, unknown-key rejection. |
| `abm_config_validation_tests` | `ConfigValidationTestMain.cpp`, `ConfigValidationTests.cpp` | Feasibility rules, independently of running a simulation. |
| `abm_archive_workflow_tests` | `ArchiveWorkflowTestMain.cpp`, `ArchiveWorkflowTests.cpp` | Run-id generation, folder layout, archive-schema completeness. |
| `abm_run_artifact_writer_tests` | `RunArtifactWriterTestMain.cpp`, `RunArtifactWriterTests.cpp` | CSV/JSON column layout and formatting of every artefact. |

---

## 3. The Python analysis package

Installed as `abm-analysis`; run as `python -m abm_analysis <command>` or via
the `abm-analysis` script.

### 3.1 Entry point and CLI

| File | Function |
| --- | --- |
| `__init__.py` | Package docstring stating the empirical-finance diagnostic workflow, plus public re-exports. |
| `__main__.py` | Makes `python -m abm_analysis` work; forwards to `cli.main`. |
| `cli.py` | The `main()` entry point named in `pyproject.toml`: builds the parser, dispatches to a handler. The only CLI module outside `commands/`. |
| `commands/__init__.py` | `build_parser()` — the top-level parser — and `COMMAND_MODULES`, whose order fixes the order subcommands appear in `--help`. Each module registers its own subcommand. |
| `commands/` | One module per subcommand (`run`, `compare`, `replicate`, `robustness`, `compress`, `calibrate`, `convert-benchmarks`, `db`, `web`), each pairing its parser with its handler. |
| `commands/shared_arguments.py` | Option groups shared by more than one command (`--benchmark-*`, `--source`, database URL, `--figure-formats`). |
| `commands/shared_helpers.py` | Helpers shared by more than one command handler: benchmark-directory resolution and the import/optional-output printers. |
| `environment.py` | Local environment setup for reproducible analysis runs. |

### 3.2 Reading simulator output (`archive/`)

Everything concerned with getting data off disk and into DataFrames; nothing
here computes results.

| File | Function |
| --- | --- |
| `archive/archives.py` | Discovery and validation of run archives on disk; resolves artefact paths (including `.gz` variants) and checks required columns. Every other module gets its data through here. |
| `archive/run_ids.py` | Parses the frozen run-id folder name back into parameters. Supports three historical variants — and, per `AGENTS.md`, must never need a fourth. |
| `archive/run_discovery.py` | Finds the run directory a simulator subprocess just created, by parsing the simulator's stdout rather than diffing the directory — which would mis-attribute runs under parallel seeds. |
| `archive/manifests.py` | Reads `experiment_manifest.csv` and builds the run index used by comparison reports. |
| `archive/timeseries.py` | Loads time-series artefacts and prepares return series (log returns, warm-up trimming). |
| `archive/data.py` | Compatibility facade re-exporting the loading/normalisation helpers under their older names. |
| `archive/compression.py` | In-place gzip of completed archives; the three big per-row CSVs compress ~5–10× and both pandas and the loaders read `.gz` transparently. |
| `archive/benchmarks.py` | Loads the empirical benchmark series named in `config/benchmarks/manifest.csv`. |

### 3.3 Statistics and diagnostics (`statistics/`)

These compute the numbers; the matching modules under `plots/` render them.
That separation is why `statistics/stress.py` and `plots/stress.py` can share
a name without ambiguity.

| File | Function |
| --- | --- |
| `statistics/diagnostics.py` | The core stylised-fact tests using `statsmodels`/`arch`: Ljung-Box, ARCH-LM, GARCH fits, tail-index and kurtosis estimates, autocorrelation of returns and absolute returns. |
| `statistics/comparisons.py` | Simulation-versus-benchmark return-distribution comparisons. |
| `statistics/stress.py` | Crisis and stress-regime diagnostics for both simulated and empirical series. |
| `statistics/robustness.py` | Per-condition seed-robustness summaries across replicated runs. |
| `statistics/robustness_tests.py` | The cross-seed inferential tests — distributional equality, moment stability, and stylised-fact reproduction — answering whether seed-only differences are statistically detectable. |
| `statistics/robustness_verdicts.py` | Turns those tests into pass / borderline / fail verdicts using fixed, named, literature-anchored thresholds so every verdict can be explained. |
| `statistics/seed_convergence.py` | Tracks how the ensemble mean and its 95% CI stabilise as seeds accumulate, following the sequential-precision argument in Law (2015, ch. 9) — this is what justifies the chosen replication count. |
| `parallel.py` | Ordered thread-pool execution of independent simulator subprocesses (the GIL is released inside `subprocess`, so threads give real parallelism). Backs `--jobs`. |
| `replication.py` | The `replicate` command: runs one fixed configuration across a seed list, then builds the seed-robustness report. |

### 3.4 Calibration (`calibration/`)

Optuna searches the parameter space; the C++ binary remains the simulator.

| File | Function |
| --- | --- |
| `__init__.py` | Package docstring on simulation-based minimum-distance calibration; public API. |
| `models.py` | Option and result dataclasses for a calibration study. |
| `constants.py` | Shared constants and defaults. |
| `config.py` | Patches a base `.cfg` with trial parameters and translates `search_space.json` into Optuna distributions. |
| `scoring.py` | The minimum-distance objective: distance between simulated and empirical return moments/statistics. |
| `execution.py` | Launches simulator subprocesses per trial and handles the isolated-worker payload protocol. |
| `robustness.py` | Re-runs top candidates across validation seeds inside a shared `simulation_runs/validation` directory, reusing the report's computations. |
| `study.py` | Orchestrates the whole study and writes `best_config.cfg`, `calibration_trials.csv`, and `settings.json`. |
| `worker.py` | The isolated worker process for one trial, launched as `python -m abm_analysis.calibration.worker`. It exists so pandas/NumPy/statsmodels allocations are reclaimed by process exit — a hard memory reset every trial. |

Candidates are ranked by **fit × seed-robustness pass rate**, not fit alone.

### 3.5 Figures (`plots/`)

| File | Function |
| --- | --- |
| `__init__.py` | Public figure API; the registry reports pull from. |
| `common.py` | Shared Plotly theme, colour scheme, and layout helpers. |
| `publication.py` | Print styling for static export: serif fonts, white background, LaTeX text-width sizing. |
| `market.py` | Price, volume, and return-path figures. |
| `returns.py` | Compatibility facade over the two modules below. |
| `return_distributions.py` | Histograms, QQ plots, tail plots of simulated returns. |
| `return_benchmarks.py` | Simulated-versus-empirical return comparison figures. |
| `return_attribution.py` | Decomposes return distributions by agent strategy. |
| `agents.py` | Agent wealth, portfolio, behaviour, and trading-activity figures. |
| `microstructure.py` | Order-book depth, spread, and order-flow figures. |
| `robustness.py` | Per-seed metric spread, convergence curves, and test-result figures. |
| `stress.py` | Stress-regime and crisis-window figures. |

### 3.6 Reports (`report/`)

| File | Function |
| --- | --- |
| `__init__.py`, `builders.py` | Public API and a compatibility facade. |
| `models.py` | Return objects describing generated report artefacts. |
| `paths.py` | Output path resolution and benchmark loading for a report. |
| `labels.py` | Human-readable simulation labels for tables and chart notes. |
| `rendering.py` | HTML rendering and table-preview helpers. |
| `sections.py` | Assembles numbered, manuscript-style sections from figures and tables. |
| `figures.py` | Figure assembly and `figure_index.csv` export. |
| `static_export.py` | Kaleido-backed PNG (300 DPI) / PDF / SVG export; handles the Chrome dependency and `--no-export-images`. |
| `evidence.py` | Quantitative stylised-fact evidence tables — the inferential content of the report. |
| `summaries.py` | Key-metric summary rows. |
| `run.py` | The single-run report (`abm_analysis run <run_dir>`). |
| `comparison.py` | The cross-run experiment comparison report (`abm_analysis compare <experiment_dir>`). |
| `seed_robustness.py` | The dedicated seed-robustness report: one question in depth — are headline results robust to the seed? |
| `calibration.py` | The cross-candidate calibration ranking report explaining *why* the winner won; writes CSV exports before rendering HTML. |
| `database_reports.py` | Wrappers that materialise a temporary file archive from the database so the file-based report builders can run unchanged. |
| `templates/report.html.j2` | The Jinja2 template every static report renders into. |

### 3.7 PostgreSQL layer (`database/`)

Optional. Simulator CSV/JSON are treated as staging artefacts; the database is
the queryable research store.

| File | Function |
| --- | --- |
| `__init__.py` | Package docstring and public API. |
| `schema.py` | Versioned schema migrations. |
| `constants.py` | Table/column definitions and import policy — the Python half of the cross-language column contract. |
| `sql.py` | SQLAlchemy connection and low-level query helpers. |
| `models.py` | Small DTOs used across the database workflows. |
| `normalisation.py` | Portable metadata and SQL value normalisation. |
| `provenance.py` | Content hashing so re-imports are detectable and reproducible. |
| `table_builders.py` | Builds and chunk-inserts normalised tables from staging files. |
| `run_imports.py` | Imports one run archive. |
| `benchmark_imports.py` | Imports empirical benchmark series. |
| `imports.py` | Compatibility facade over the two import modules. |
| `exports.py` | Queries and exports from the database back into analysis archives. |
| `inspection.py` | Read-only provenance inspection of imported runs. |
| `audit.py` | Records the import audit trail. |
| `validation.py` | Thesis-scale validation checks over imported data. |

### 3.8 Local dashboard (`web/`)

A read-only FastAPI application for browsing the archive without generating a
report first. It never simulates and never writes to `data/`; every statistic it
serves is recomputed by `statistics/diagnostics.py` and `statistics/multi_asset.py`,
so the dashboard and the citable static reports cannot disagree.

Statistics are reported **per traded asset**: a run configured with two assets
gets one column per market in every table and one line per market in every chart.

| File | Function |
| --- | --- |
| `web/__init__.py` | Package docstring and the `create_app` / `serve` public API. |
| `web/app.py` | The FastAPI application: the catalogue and run endpoints, the single-page interface, and the Plotly bundle served from the installed `plotly` package so the dashboard works offline. Caches each run's payload against a change stamp over all six artefacts it reads (`CACHE_KEY_ARTEFACTS`), because the GARCH fit dominates the cost of opening a run and `config.json` alone decides the asset universe. |
| `web/catalogue.py` | Walks the data root and treats any directory holding `step_timeseries.csv` as a run, grouping runs by their parent. This is why `data/experiments/<name>/`, `data/calibration/<study>/simulation_runs/`, and `data/latest` are all found without hard-coding the three layouts. Also performs the containment check on client-supplied run paths. |
| `web/run_view.py` | Assembles one run's payload: identity, parameters, the three metric tables (return moments, serial dependence, market outcomes) with a value per asset, and the stylised-fact verdicts with their evidence per asset. Delegates the asset and agent dimensions to the two modules below. |
| `web/asset_view.py` | The per-asset half. `resolve_asset_context()` is the **only** place that decides whether a run is read from `asset_timeseries.csv` or `step_timeseries.csv`, gating on `len(list_assets(run_dir)) >= 2` rather than on the artefact's presence — see its docstring for the inconsistent-archive case that distinction protects. Also builds the per-asset series, distributions, autocorrelations, and the cross-asset panel. |
| `web/agent_view.py` | The agent panel: the per-strategy table (via `plots.agents.build_agent_summary_statistics`, the same function behind the report's table) and the shared-bin final-wealth density per strategy. Reads the wealth Gini from `summary_metrics.csv`; the authoritative implementation is the simulator's. |
| `web/metrics.py` | Cell builders and column helpers shared by the two view modules. Keeping them here rather than in either view is what stops the three modules importing each other in a circle. |
| `web/serialisation.py` | Converts pandas/NumPy values to JSON primitives, mapping every non-finite value to `null` so an uncomputable diagnostic reads as absent rather than as a number. |
| `web/static/` | The single-page interface: `index.html`, `styles.css` (light and dark, with the asset colour key), `app.js` (formatting, run selection, the metric tables, and the Plotly charts). Holds no analysis logic; the price-scale and autocorrelation switches redraw from the payload already in memory and never refetch. |

### 3.9 Python tests (`tests/python/`)

| File | Covers |
| --- | --- |
| `abm_test_helpers.py` | Shared fixtures: synthetic run archives, fake simulator binaries, temp experiment trees. |
| `test_analysis_data.py` | Archive loading, normalisation, return preparation. |
| `test_analysis_diagnostics.py` | The econometric diagnostics. |
| `test_analysis_plots.py` | Figure construction. |
| `test_analysis_reports.py` | Report assembly and rendering. |
| `test_analysis_cli.py` | Argument parsing and command dispatch. |
| `test_analysis_benchmarks.py` | Benchmark loading. |
| `test_calibration.py` | The full calibration workflow — the largest suite. |
| `test_replication.py` | Seed replication and its report. |
| `test_robustness_statistics.py` | Cross-seed tests and verdict thresholds. |
| `test_seed_robustness_report.py` | The seed-robustness report end to end. |
| `test_run_discovery.py` | Race-free run discovery under parallel seeds. |
| `test_parallel.py` | The ordered thread pool. |
| `test_database.py` | Schema, imports, exports. |
| `test_archive_storage.py` | Drift guard, caching, compression, chunked inserts. |
| `test_static_export.py` | Kaleido figure export. |
| `test_schema_sync.py` | **Cross-language guard** — asserts the C++ writer header literals, the Python required-column sets, and the PostgreSQL column tuples all still agree. This is the test that fails when a C++ CSV column changes without a Python update. |
| `test_repository_hygiene.py` | **Structural guard** — asserts the conventions this document describes: every `src/*.cpp` is named in its directory's `target_sources()` (so a new file cannot silently go uncompiled), every domain with sources has a `CMakeLists.txt` and is `add_subdirectory`'d, every source shares a prefix with a header in its directory, and no `*.egg-info` is tracked. |
| `test_xlsx_conversion.py` | Builds minimal SpreadsheetML workbooks in-process and checks the benchmark conversion: shared/inline strings, booleans, date serials, padded gap rows, lock-file skipping, and the `convert-benchmarks` subcommand end to end. |
| `test_web_app.py` | Dashboard run discovery across all three archive layouts, the data-root containment check, per-asset reporting for multi-asset runs, the agent panel, and the guarantee that the served metrics equal `statistics/diagnostics.py`'s and `plots/agents.py`'s. Also pins the awkward archives: the warm-up phase falling back to the primary market, and an `asset_timeseries.csv` that disagrees with its own run. |

### 3.10 Empirical data ingestion

| File | Function |
| --- | --- |
| `archive/xlsx_conversion.py` | Dependency-free Excel → CSV converter that turns `data/stock_data/*.xlsx` into the CSVs `archive/benchmarks.py` reads. Built on `zipfile` plus SpreadsheetML rather than openpyxl, deliberately: the step runs only when new empirical data arrives, and this keeps openpyxl out of the runtime dependencies. Resolves shared strings, inline strings, booleans, and date-formatted serials; pads missing rows; skips Excel `~$` lock files. |
| `commands/convert_benchmarks.py` | Exposes it as `abm_analysis convert-benchmarks <path>`, so conversion is a documented pipeline step rather than a script run by hand. |

---

## 4. End-to-end flow

**A single simulation run:**

```
config/simulation.cfg
   │  SimulationConfigIO → Parsing → SettingAppliers → Validation
   ▼
SimulationApplication
   │  constructs
   ▼
SimulationEngine ── PopulationFactory ── Agent + strategies (+ ProspectTheory)
   │                MarketProcess (warm-up)
   │   per step:    AgentActivationScheduler → SocialInfluenceModel
   │                → OrderCollector (strategy → PortfolioOptimizer → OrderSizing
   │                   → OrderPricing → ShortSaleRiskControls)
   │                → MarketClearingEngine → LimitOrderBook
   │                → RiskControlService → DiagnosticsRecorder
   ▼
SimulationRunResult ──→ StylisedFactMetrics, AllocativeEfficiency
   │
   ▼
ExperimentDataWorkflow (ExperimentRunManager + RunArchiveSchema)
   │
   ▼
RunArtifactWriter → *.csv, config.json, metadata.json, experiment_manifest.csv
   │
   ▼
PythonAnalysisRunner → abm_analysis run → HTML report + figures
```

**A calibration study:**

```
search_space.json ─→ calibration/config.py ─→ Optuna (calibration/study.py)
        │                                            │
        │                     per trial: calibration/worker.py (fresh process)
        │                                → execution.py → build/release/simulate
        │                                → run_discovery.py → archives.py
        │                                → scoring.py (distance to benchmark)
        ▼
top candidates → calibration/robustness.py → validation seeds → robustness_verdicts.py
        ▼
best_config.cfg + calibration_trials.csv + calibration ranking report
```

**A seed-robustness study:**

```
replication.py → parallel.py → N × simulate (one per seed) → run_discovery.py
      → robustness.py (summaries) → robustness_tests.py → robustness_verdicts.py
      → seed_convergence.py → report/seed_robustness.py → HTML + figures
```

---

## 5. The contracts that hold it together

Four boundaries are load-bearing. Changing one without the others is where
breakage comes from:

1. **The config key set.** `config/simulation.cfg` ↔ the applier functions in
   `SimulationConfigSettingAppliers.cpp` and its four settings files. Unknown
   keys are rejected, so adding a key means adding an applier and a validation
   rule.
2. **The run-id folder name.** Written by `ExperimentRunManager`, parsed by
   `run_ids.py`. The schema is frozen — new parameters go into `metadata.json`
   and `summary_metrics.csv`, never into the folder name.
3. **The CSV column layout.** Written by the `src/Output/*CsvWriter` family,
   required by `archives.py`, and inserted by `database/constants.py`.
   `tests/python/test_schema_sync.py` exists specifically to fail when these
   three drift apart.
4. **The build source list.** A new `src/<Domain>/*.cpp` must be added to the
   `target_sources()` call in that directory's own `CMakeLists.txt`; the
   top-level `CMakeLists.txt` only changes when a module boundary genuinely
   changes.

Per `AGENTS.md`, when class responsibilities, build structure, data management,
or simulation flow change, the matching Mermaid diagram under `docs/` should be
updated alongside the code — and so should this file.
