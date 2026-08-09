"""Cross-candidate calibration ranking report.

Answers "why did the winning configuration win?" in one page: the candidate
ranking table with fit and robustness columns, the winner's verdict cards, and
the full per-candidate verdict table. The CSV exports are written before the
HTML render so the machine-readable record survives a rendering failure.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from abm_analysis.robustness_verdicts import verdict_rows_for_report

from .rendering import _render_report, _table_preview
from .sections import _appendices, _section


def build_calibration_report(
    output_dir: Path | str,
    *,
    calibration_name: str,
    candidate_summary: pd.DataFrame,
    candidate_verdicts: pd.DataFrame,
    best_trial_number: int,
    robustness_penalty_weight: float,
    borderline_credit: float,
    validation_seed_count: int,
    estimated_total_runs: int,
) -> Path:
    """Write the cross-candidate calibration report and return its path.

    ``candidate_summary`` holds one row per validated candidate (fit scores,
    robustness counts, ``robust_ranking_score``, ``selected``);
    ``candidate_verdicts`` concatenates every candidate's verdict table with a
    leading ``trial_number`` column.
    """

    report_dir = Path(output_dir).expanduser().resolve() / "calibration_report"
    report_dir.mkdir(parents=True, exist_ok=True)

    summary_csv_path = report_dir / "candidate_validation_summary.csv"
    verdicts_csv_path = report_dir / "candidate_robustness_verdicts.csv"
    candidate_summary.to_csv(summary_csv_path, index=False)
    candidate_verdicts.to_csv(verdicts_csv_path, index=False)

    winner_verdicts = (
        candidate_verdicts[candidate_verdicts["trial_number"] == best_trial_number]
        if not candidate_verdicts.empty and "trial_number" in candidate_verdicts.columns
        else candidate_verdicts
    )
    best_rows = (
        candidate_summary[candidate_summary["trial_number"] == best_trial_number]
        if not candidate_summary.empty
        else candidate_summary
    )
    best_row = best_rows.iloc[0] if not best_rows.empty else pd.Series(dtype=object)

    sections = [
        _section(
            "candidate-ranking",
            "Candidate Ranking",
            "Each top candidate from the Optuna search was re-run across the "
            "validation seeds. The legacy fit ranking is "
            "ranking_score = mean_validation_score + validation_score_std; the "
            "final ranking multiplies it by the robustness shortfall, "
            f"robust_ranking_score = ranking_score × (1 + "
            f"{robustness_penalty_weight:g} × (1 − pass_rate)), where "
            f"borderline verdicts earn {borderline_credit:g} of a pass. Lower "
            "is better; the selected row is the calibration winner.",
            {},
            table_entries=[
                ("Validated Candidates", _table_preview(candidate_summary)),
            ],
            footnote=(
                "A NaN pass rate means no robustness criterion could be "
                "evaluated for that candidate; when no candidate has verdicts "
                "the ranking falls back to the fit-only rule."
            ),
        ),
        _section(
            "candidate-verdicts",
            "Robustness Verdicts by Candidate",
            "Every seed-robustness criterion evaluated for every candidate. "
            "Verdicts flag criteria for inspection; a fail signals sensitivity "
            "to random initialisation at those parameter settings, not "
            "necessarily a modelling error.",
            {},
            table_entries=[
                (
                    "Per-Candidate Verdicts",
                    _table_preview(
                        candidate_verdicts,
                        max_rows=120,
                        hidden_columns={"hypothesis", "metric_value"},
                    ),
                ),
            ],
        ),
    ]

    report_path = report_dir / "index.html"
    _render_report(
        report_path,
        title=f"Calibration Report: {calibration_name}",
        meta_line=(
            f"Calibration: {calibration_name} · "
            f"{_candidate_count(candidate_summary)} validated candidate(s) · "
            f"{validation_seed_count} validation seed(s) · "
            f"≈{estimated_total_runs} simulator runs"
        ),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        key_metrics=_calibration_key_metric_rows(best_row, validation_seed_count),
        evidence_rows=verdict_rows_for_report(winner_verdicts),
        evidence_title="Winner Robustness Verdicts",
        evidence_intro=(
            "Seed-robustness criteria for the selected configuration, computed "
            "across its validation seeds with the same decision rules as the "
            "seed-robustness report."
        ),
        evidence_caption="Robustness verdicts for the winning candidate.",
        evidence_fact_header="Criterion",
        sections=sections,
        appendices=_appendices(
            output_files=[
                "candidate_validation_summary.csv",
                "candidate_robustness_verdicts.csv",
            ],
        ),
    )
    return report_path


def _candidate_count(candidate_summary: pd.DataFrame) -> int:
    if candidate_summary.empty or "trial_number" not in candidate_summary.columns:
        return 0
    return int(candidate_summary["trial_number"].nunique())


def _calibration_key_metric_rows(
    best_row: pd.Series,
    validation_seed_count: int,
) -> list[dict[str, str]]:
    return [
        {
            "metric": "Winning Trial",
            "value": _display(best_row.get("trial_number"), "{:.0f}"),
            "note": "Optuna trial number of the selected configuration.",
        },
        {
            "metric": "Mean Validation Score",
            "value": _display(best_row.get("mean_validation_score"), "{:.4f}"),
            "note": "Fit distance to the empirical benchmarks (lower is better).",
        },
        {
            "metric": "Robustness Pass Rate",
            "value": _display(best_row.get("robustness_pass_rate"), "{:.0%}"),
            "note": "Share of evaluated criteria passed, borderline part-credited.",
        },
        {
            "metric": "Robust Ranking Score",
            "value": _display(best_row.get("robust_ranking_score"), "{:.4f}"),
            "note": "Fit score scaled by the robustness shortfall (lower is better).",
        },
        {
            "metric": "Validation Seeds",
            "value": f"{validation_seed_count:,}",
            "note": "Distinct seeds used to validate each top candidate.",
        },
    ]


def _display(value: object, template: str) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return "Not available"
    return template.format(float(numeric))
