"""Dedicated seed-robustness report for replicated ABM experiments.

Unlike the experiment-comparison report, which surveys market dynamics,
microstructure, and agent outcomes, this report answers one question in
depth: are the simulation's headline results robust to the random seed? It
is built for experiments whose runs differ only in the seed (the output of
``abm_analysis replicate``) and can be regenerated from any archived
experiment folder without re-running the simulator.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from abm_analysis.archive.data import build_runs_index, discover_run_directories
from abm_analysis.statistics.diagnostics import (
    build_pairwise_ks_table,
    build_return_series_by_run,
    build_stylised_fact_diagnostics,
)
from abm_analysis.plots import (
    make_adf_pvalue_figure,
    make_ks_heatmap_figure,
    make_return_ecdf_figure,
    make_seed_convergence_figure,
    make_seed_metric_distribution_figure,
    make_seed_robustness_figure,
    make_stylised_fact_success_figure,
)
from abm_analysis.statistics.robustness import (
    build_seed_robustness_summary,
    merge_run_and_diagnostic_metrics,
)
from abm_analysis.statistics.robustness_tests import (
    build_adf_stationarity_table,
    build_cross_seed_distribution_tests,
    summarise_adf_rejections,
    summarise_pairwise_ks,
)
from abm_analysis.statistics.robustness_verdicts import (
    SUCCESS_RATE_PASS_THRESHOLD,
    build_robustness_verdicts,
    verdict_rows_for_report,
)
from abm_analysis.statistics.seed_convergence import build_seed_convergence_table

from .figures import _build_figure_index, _raise_on_export_failures
from .static_export import STATIC_EXPORT_FORMATS, ensure_static_export_ready
from .labels import _add_pairwise_simulation_labels, _add_simulation_labels, _simulation_label_table
from .models import SeedRobustnessReportResult
from .paths import _robustness_output_dir
from .rendering import _render_report, _table_preview
from .sections import _appendices, _seed_robustness_report_sections
from .summaries import _seed_robustness_key_metric_rows


def build_seed_robustness_report(
    experiment_dir: Path | str,
    *,
    output_dir: Path | str | None = None,
    phase: str = "simulation",
    price_column: str = "market_price",
    max_runs: int = 8,
    export_images: bool = False,
    figure_formats: tuple[str, ...] = STATIC_EXPORT_FORMATS,
) -> SeedRobustnessReportResult:
    """Create the dedicated seed-robustness HTML report for an experiment.

    The pipeline reuses the per-run diagnostics of the comparison report and
    adds the cross-seed statistical layer: k-sample distribution tests, a
    pairwise K-S summary, per-seed ADF stationarity, seed-count convergence,
    and the pass/borderline/fail verdict table. All intermediate tables are
    exported as CSV files beside ``index.html`` for thesis replication.
    """

    if export_images:
        ensure_static_export_ready()

    experiment_path = Path(experiment_dir).expanduser().resolve()
    run_dirs = discover_run_directories(experiment_path)
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found under {experiment_path}")

    report_dir = _robustness_output_dir(experiment_path, output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    runs_index = build_runs_index(experiment_path)
    diagnostics = build_stylised_fact_diagnostics(
        run_dirs,
        phase=phase,
        price_column=price_column,
    )
    return_series_by_run = build_return_series_by_run(
        run_dirs,
        phase=phase,
        price_column=price_column,
    )
    pairwise_ks = build_pairwise_ks_table(return_series_by_run)

    run_labels = _seed_run_labels(runs_index)
    seed_by_run = _seed_by_run(runs_index)
    seed_count = _distinct_seed_count(runs_index)

    seed_robustness = build_seed_robustness_summary(runs_index, diagnostics)
    ks_summary = summarise_pairwise_ks(pairwise_ks)
    distribution_tests = build_cross_seed_distribution_tests(return_series_by_run)
    adf_table = build_adf_stationarity_table(return_series_by_run, seed_by_run)
    adf_summary = summarise_adf_rejections(adf_table)
    convergence_table = build_seed_convergence_table(runs_index, diagnostics)
    verdicts = build_robustness_verdicts(
        seed_robustness,
        distribution_tests,
        ks_summary,
        adf_summary,
        convergence_table,
        seed_count=seed_count,
    )
    per_seed_metrics = merge_run_and_diagnostic_metrics(runs_index, diagnostics)

    labelled_runs_index = _add_simulation_labels(runs_index, run_labels)
    labelled_diagnostics = _add_simulation_labels(diagnostics, run_labels)
    labelled_pairwise_ks = _add_pairwise_simulation_labels(pairwise_ks, run_labels)
    labelled_adf = _add_simulation_labels(adf_table, run_labels)

    runs_index_csv_path = report_dir / "runs_index.csv"
    diagnostics_csv_path = report_dir / "stylised_fact_diagnostics.csv"
    pairwise_ks_csv_path = report_dir / "pairwise_ks_log_returns.csv"
    seed_robustness_csv_path = report_dir / "seed_robustness_summary.csv"
    distribution_tests_csv_path = report_dir / "cross_seed_distribution_tests.csv"
    adf_stationarity_csv_path = report_dir / "adf_stationarity_by_seed.csv"
    seed_convergence_csv_path = report_dir / "seed_convergence.csv"
    verdicts_csv_path = report_dir / "robustness_verdicts.csv"
    figure_index_csv_path = report_dir / "figure_index.csv"
    labelled_runs_index.to_csv(runs_index_csv_path, index=False)
    labelled_diagnostics.to_csv(diagnostics_csv_path, index=False)
    labelled_pairwise_ks.to_csv(pairwise_ks_csv_path, index=False)
    seed_robustness.to_csv(seed_robustness_csv_path, index=False)
    distribution_tests.to_csv(distribution_tests_csv_path, index=False)
    labelled_adf.to_csv(adf_stationarity_csv_path, index=False)
    convergence_table.to_csv(seed_convergence_csv_path, index=False)
    verdicts.to_csv(verdicts_csv_path, index=False)

    display_run_ids = _display_run_ids(runs_index, max_runs)
    figure_objects: dict[str, object] = {
        "return_ecdf": make_return_ecdf_figure(
            return_series_by_run,
            display_run_ids,
            run_labels,
        ),
        "ks_heatmap": make_ks_heatmap_figure(
            pairwise_ks,
            sorted(return_series_by_run),
            run_labels,
        ),
        "seed_metric_distribution": make_seed_metric_distribution_figure(per_seed_metrics),
        "seed_robustness": make_seed_robustness_figure(seed_robustness),
        "stylised_fact_success": make_stylised_fact_success_figure(
            seed_robustness,
            pass_threshold=SUCCESS_RATE_PASS_THRESHOLD,
        ),
        "adf_pvalues": make_adf_pvalue_figure(labelled_adf),
        "seed_convergence": make_seed_convergence_figure(convergence_table),
    }
    table_previews = {
        "distribution_tests": _table_preview(distribution_tests),
        "pairwise_ks": _table_preview(
            labelled_pairwise_ks,
            hidden_columns={"run_id_a", "run_id_b"},
        ),
        # The full key=value condition description stays in the CSV export;
        # on screen the short condition_id plus the individual parameter
        # columns carry the same information without a 200-character cell.
        "seed_robustness": _table_preview(
            seed_robustness,
            hidden_columns={"condition_description"},
        ),
        "stylised_fact_diagnostics": _table_preview(
            labelled_diagnostics,
            hidden_columns={"run_id"},
        ),
        "adf_stationarity": _table_preview(labelled_adf, hidden_columns={"run_id"}),
        "seed_convergence": _table_preview(convergence_table),
    }
    sections = _seed_robustness_report_sections(figure_objects, table_previews)

    report_path = report_dir / "index.html"
    _render_report(
        report_path,
        title=f"Seed Robustness Report: {experiment_path.name}",
        meta_line=(
            f"Experiment: {experiment_path.name} · {len(run_dirs)} run(s) · "
            f"{seed_count} seed(s) · phase: {phase} · price series: {price_column}"
        ),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        key_metrics=_seed_robustness_key_metric_rows(
            runs_index,
            diagnostics,
            ks_summary,
            adf_summary,
            verdicts,
        ),
        evidence_rows=verdict_rows_for_report(verdicts),
        evidence_title="Seed-Robustness Verdicts",
        evidence_intro=(
            "Each row states one robustness criterion, its fixed decision rule, "
            "and the measured cross-seed value. Verdicts flag criteria for "
            "inspection; a fail signals sensitivity to random initialisation, "
            "not necessarily a modelling error."
        ),
        evidence_caption="Seed-robustness criteria and verdicts.",
        evidence_fact_header="Criterion",
        sections=sections,
        appendices=_appendices(
            output_files=[
                "runs_index.csv",
                "stylised_fact_diagnostics.csv",
                "pairwise_ks_log_returns.csv",
                "seed_robustness_summary.csv",
                "cross_seed_distribution_tests.csv",
                "adf_stationarity_by_seed.csv",
                "seed_convergence.csv",
                "robustness_verdicts.csv",
            ],
            run_inventory_tables=[
                ("Seed-to-Run Mapping", _simulation_label_table(runs_index, run_labels)),
            ],
        ),
    )

    # Export after the HTML render so a Kaleido failure never costs the
    # user their report; _raise_on_export_failures still fails the command.
    figure_index = _build_figure_index(
        report_dir,
        figure_objects,
        export_images=export_images,
        figure_formats=figure_formats,
    )
    figure_index.to_csv(figure_index_csv_path, index=False)
    _raise_on_export_failures(figure_index)

    return SeedRobustnessReportResult(
        report_path=report_path,
        output_dir=report_dir,
        runs_index_csv_path=runs_index_csv_path,
        diagnostics_csv_path=diagnostics_csv_path,
        pairwise_ks_csv_path=pairwise_ks_csv_path,
        seed_robustness_csv_path=seed_robustness_csv_path,
        distribution_tests_csv_path=distribution_tests_csv_path,
        adf_stationarity_csv_path=adf_stationarity_csv_path,
        seed_convergence_csv_path=seed_convergence_csv_path,
        verdicts_csv_path=verdicts_csv_path,
        figure_index_csv_path=figure_index_csv_path,
    )


def _seed_run_labels(runs_index: pd.DataFrame) -> dict[str, str]:
    """Label each run by its seed, the natural chart label for replicates.

    Falls back to the run identifier when the seed is unavailable so that
    labels never collapse to an empty string.
    """

    labels: dict[str, str] = {}
    if runs_index.empty or "run_id" not in runs_index.columns:
        return labels
    seeds = runs_index.get("seed")
    for position, run_id in enumerate(runs_index["run_id"].astype(str)):
        seed = seeds.iloc[position] if seeds is not None else None
        seed_number = pd.to_numeric(pd.Series([seed]), errors="coerce").iloc[0]
        if pd.isna(seed_number):
            labels[run_id] = run_id
        else:
            labels[run_id] = f"Seed {int(seed_number)}"
    return labels


def _seed_by_run(runs_index: pd.DataFrame) -> dict[str, object]:
    if runs_index.empty or not {"run_id", "seed"}.issubset(runs_index.columns):
        return {}
    return dict(zip(runs_index["run_id"].astype(str), runs_index["seed"], strict=True))


def _distinct_seed_count(runs_index: pd.DataFrame) -> int:
    if runs_index.empty:
        return 0
    if "seed" not in runs_index.columns:
        return int(len(runs_index))
    return int(pd.to_numeric(runs_index["seed"], errors="coerce").nunique())


def _display_run_ids(runs_index: pd.DataFrame, max_runs: int) -> list[str]:
    """Choose the runs shown in dense overlay charts, ordered by seed.

    Ordering by ascending seed (rather than creation time) keeps the display
    subset stable across report regenerations of the same experiment.
    """

    if runs_index.empty or "run_id" not in runs_index.columns:
        return []
    ordered = runs_index.copy()
    if "seed" in ordered.columns:
        ordered["_seed_order"] = pd.to_numeric(ordered["seed"], errors="coerce")
        ordered = ordered.sort_values(["_seed_order", "run_id"], na_position="last")
    else:
        ordered = ordered.sort_values("run_id")
    return ordered["run_id"].astype(str).head(max_runs).tolist()
