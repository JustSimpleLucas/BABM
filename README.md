# Agent-Based Stock Market Simulation

This project simulates a stock market populated by artificial traders. Each trader follows rules inspired by behavioural finance theory (such as prospect theory and herding), and the goal is to reproduce the well-known statistical patterns of real stock markets.

The traders follow one of four strategies — fundamentalist, chartist, noise trader, or buy-and-hold — and talk to their neighbours through a communication network:

<p align="center">
  <img src="/pictures/communication_topology.png" alt="Communication topology" width="500">
</p>

You do not need to know how to code to run the simulation. Just follow the steps below.

## What you need first

Before you start, make sure these are installed on your computer (macOS or Linux):

- **Python 3** — runs the analysis and reports
- **CMake** (version 3.25 or newer) and a **C++ compiler** — build the simulator

On a Mac, the easiest way is to open the **Terminal** app and run:

```bash
xcode-select --install        # installs the C++ compiler
brew install cmake python3    # requires Homebrew (https://brew.sh)
```

## One-time setup

You only need to do this once. Copy each block into your terminal and press Enter.

**1. Download the code and open the project folder**

Download this repository (green "Code" button → "Download ZIP", then unzip), or use git. Then move into the folder in your terminal:

```bash
cd path/to/ABMs_code
```

**2. Set up Python**

This creates a private Python workspace for the project so nothing else on your computer is affected:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

If it worked, your terminal prompt now starts with `(.venv)`.

Then install the required libraries:

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

**3. Build the simulator**

This turns the C++ source code into a program you can run:

```bash
cmake --preset debug
cmake --build --preset debug
```

This can take a few minutes the first time. When it finishes without red error messages, you're ready.

## Run a simple simulation

```bash
build/debug/simulate --config config/simulation.cfg
```

That's it! When the run finishes, a report opens automatically in your web browser showing prices, returns, and agent behaviour:

<p align="center">
  <img src="/pictures/outPut.png" alt="Simulation output report" width="400" height="300">
</p>

All results are also saved as files in `data/experiments/`, one folder per run.

## Change the settings

All simulation settings (number of agents, number of time steps, strategy mix, and so on) live in one plain text file: `config/simulation.cfg`. Open it with any text editor, change the numbers, save, and run the simulation again.

<p align="center">
  <img src="/pictures/simulation_pic.png" alt="Simulation configuration" width="300" height="300">
</p>

## Calibrate the model against real market data

Instead of guessing parameter values by hand, calibration tries many combinations automatically and finds the ones whose simulated returns look most like real stock-market data (stored in `data/stock_data/candle_chart`).

**1. Build the fast version of the simulator** (one time only — calibration runs hundreds of simulations, so it uses the optimised build):

```bash
cmake --preset release
cmake --build --preset release
```

**2. Start the calibration.** A ready-made search space (the list of parameters to vary and their allowed ranges) is included in `config/calibration/search_space.json`:

```bash
.venv/bin/python -m abm_analysis calibrate \
  --base-config config/simulation.cfg \
  --search-space config/calibration/search_space.json \
  --trials 50 \
  --validation-seeds 55,101:109
```

Be patient — this runs one simulation per trial and can take a while. The `--validation-seeds` list re-tests the best candidates across 10 different random seeds, so the winner is robust rather than a one-seed fluke (use at least 5 seeds; 10 or more is recommended).

**3. Look at the results** in `data/calibration/<study_name>/`:

- `best_config.cfg` — the best parameter values found, saved as a ready-to-run config file
- `calibration_trials.csv` — every combination tried and its score
- `best_runs_robustness_report/` — a web report checking how stable the top candidates are across seeds

**4. Run the simulation with the tuned settings:**

```bash
build/debug/simulate --config data/calibration/<study_name>/best_config.cfg
```

## Tips

- **Coming back later?** Reactivate the Python workspace first: `source .venv/bin/activate`
- **"Command not found"?** Make sure you are inside the project folder (`cd path/to/ABMs_code`).
- **Changed the C++ code?** Rebuild with `cmake --build --preset debug` before running again.

## For researchers: checking robustness

To test whether results hold across many random seeds (rather than being a fluke of one run), replicate the same configuration across 30 seeds:

```bash
.venv/bin/python -m abm_analysis replicate \
  --base-config config/simulation.cfg \
  --simulator build/release/simulate \
  --seeds 1:30
```

Seeds run in parallel across CPU cores by default; pass `--jobs 1` for sequential execution with the live progress bar, or `--jobs N` to cap the worker count.

This creates a `seed_robustness_...` folder in `data/experiments/` with one run per seed, plus a web-based robustness report (`robustness_reports/latest_seed_robustness/index.html`) containing cross-seed distribution tests, stylised-fact success rates, and a pass/fail verdict table. The report can be regenerated for any archived experiment without re-running:

```bash
.venv/bin/python -m abm_analysis robustness data/experiments/<experiment_name>
```

## Publication-ready figures

Every report also saves each chart as standalone image files in a `figures/` folder next to `index.html`: a 300 DPI PNG plus vector PDF and SVG, styled for print (serif fonts, white background, sized for a full LaTeX text width). In a thesis or paper, include the PDF directly:

```latex
\includegraphics[width=\textwidth]{.../python_analysis/figures/price_timeseries.pdf}
```

Rendering the images needs Google Chrome. If it is missing, the report command stops with instructions — either install Chrome, download a private copy with `.venv/bin/python -c "import kaleido; kaleido.get_chrome_sync()"`, or skip image export with `--no-export-images` (the interactive HTML report is always generated either way). `figure_index.csv` in the report folder lists every exported file.

To export only the formats you need (saving time and disk space), pass `--figure-formats`, for example `--figure-formats pdf` for LaTeX-only output or `--figure-formats png,pdf` to drop the editable SVG copies.

**Note on data:** the `data/` folder is not stored in git — your simulation results exist only on your computer. Back up `data/experiments/` regularly if you need the results for your research. Finished experiments can be compressed to save disk space with `.venv/bin/python -m abm_analysis compress data/experiments/<experiment_name>`.
