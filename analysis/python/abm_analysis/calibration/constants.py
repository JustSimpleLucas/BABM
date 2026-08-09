"""Calibration constants shared across the Optuna workflow."""

from __future__ import annotations

import re

CONFIG_KEY_PATTERN = re.compile(r"^(\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*)(.*)$")

FAILED_TRIAL_SCORE = 1.0e9

# Heavy per-run artefacts removed once a trial has been scored. asset_timeseries
# is the largest of them (one row per step *and* asset) and is the input the
# per-asset objective reads, so it is pruned only after scoring completes, and
# never for validation runs, whose robustness verdicts are recomputed from it.
RUN_CSV_ARTIFACT_FILENAMES = (
    "step_timeseries.csv",
    "asset_timeseries.csv",
    "agents_final.csv",
    "trade_ledger.csv",
    "summary_metrics.csv",
    "stylised_facts.csv",
)
