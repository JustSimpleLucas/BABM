"""Cross-candidate calibration tables.

A calibration study ends by ranking its top candidates on fit *and* on seed
robustness, and the ranking is only auditable if the inputs survive the run.
These two CSVs are that record: one row per validated candidate with its fit
scores, robustness counts and final ranking score, and every robustness verdict
evaluated for every candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CalibrationTables:
    """Paths written by one calibration export."""

    output_dir: Path
    candidate_summary_csv_path: Path
    candidate_verdicts_csv_path: Path


def write_calibration_tables(
    output_dir: Path | str,
    *,
    candidate_summary: pd.DataFrame,
    candidate_verdicts: pd.DataFrame,
) -> CalibrationTables:
    """Write the candidate ranking and per-candidate verdict tables.

    ``candidate_summary`` holds one row per validated candidate (fit scores,
    robustness counts, ``robust_ranking_score``, ``selected``);
    ``candidate_verdicts`` concatenates every candidate's verdict table with a
    leading ``trial_number`` column.
    """

    tables_dir = Path(output_dir).expanduser().resolve() / "calibration_report"
    tables_dir.mkdir(parents=True, exist_ok=True)

    tables = CalibrationTables(
        output_dir=tables_dir,
        candidate_summary_csv_path=tables_dir / "candidate_validation_summary.csv",
        candidate_verdicts_csv_path=tables_dir / "candidate_robustness_verdicts.csv",
    )
    candidate_summary.to_csv(tables.candidate_summary_csv_path, index=False)
    candidate_verdicts.to_csv(tables.candidate_verdicts_csv_path, index=False)
    return tables
