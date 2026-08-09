"""Experiment-comparison report construction for file-backed ABM archives."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from abm_analysis.benchmarks import build_benchmark_diagnostics, build_benchmark_return_series
from abm_analysis.comparisons import build_simulation_benchmark_comparison
from abm_analysis.data import build_runs_index, discover_run_directories
from abm_analysis.database import DEFAULT_DATABASE_URL_ENV
from abm_analysis.diagnostics import (
    build_asset_stylised_fact_diagnostics,
    build_pairwise_ks_table,
    build_return_series_by_asset,
)
from abm_analysis.plots import (
    build_agent_summary_statistics,
    build_simulation_labels,
    select_display_run_ids,
)
from abm_analysis.robustness import build_seed_robustness_summary
from abm_analysis.stress import build_benchmark_stress_diagnostics, build_simulation_stress_diagnostics

from .evidence import build_comparison_evidence_assessment
from .figures import _build_figure_index, _comparison_figures, _raise_on_export_failures
from .static_export import STATIC_EXPORT_FORMATS, ensure_static_export_ready
from .labels import _add_pairwise_simulation_labels, _add_simulation_labels, _simulation_label_table
from .models import ComparisonReportResult
from .paths import _comparison_output_dir, _concat_frames, _load_benchmarks
from .rendering import _render_report, _table_preview
from .sections import _appendices, _comparison_report_sections
from .summaries import _comparison_key_metric_rows


def _asset_series_labels(
    run_labels: dict[str, str],
    return_series_by_run: dict[str, pd.Series],
) -> dict[str, str]:
    """Extend run labels with a display label for each (run, asset) series.

    A series id is either a bare run id, for archives with no per-asset
    artefact, or ``"<run id> · <asset>"``. The run part is translated through
    the short chart labels so legends stay readable, and the asset part is kept
    verbatim because it is already the name the configuration uses.
    """

    labels = dict(run_labels)
    for series_id in return_series_by_run:
        if series_id in labels:
            continue
        run_id, separator, asset = series_id.partition(" · ")
        base = run_labels.get(run_id, run_id)
        labels[series_id] = f"{base} · {asset}" if separator else base
    return labels


def _series_ids_for_runs(
    run_ids: list[str],
    return_series_by_run: dict[str, pd.Series],
) -> list[str]:
    """Select every series belonging to the given runs, in series order."""

    wanted = set(run_ids)
    return [
        series_id
        for series_id in return_series_by_run
        if series_id.partition(" · ")[0] in wanted
    ]


def build_comparison_report(
    experiment_dir: Path | str,
    *,
    output_dir: Path | str | None = None,
    phase: str = "simulation",
    price_column: str = "market_price",
    max_runs: int = 8,
    benchmark_dir: Path | str | None = None,
    benchmark_series: str | list[str] | tuple[str, ...] | None = None,
    export_images: bool = False,
    figure_formats: tuple[str, ...] = STATIC_EXPORT_FORMATS,
    source: str = "files",
    database_url: str | None = None,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> ComparisonReportResult:
    """Create a static interactive HTML report for an experiment directory."""

    if source == "database":
        from .database_reports import _build_database_comparison_report

        return _build_database_comparison_report(
            str(experiment_dir),
            output_dir=output_dir,
            phase=phase,
            price_column=price_column,
            max_runs=max_runs,
            benchmark_dir=benchmark_dir,
            benchmark_series=benchmark_series,
            export_images=export_images,
            figure_formats=figure_formats,
            database_url=database_url,
            database_url_env=database_url_env,
        )
    if source != "files":
        raise ValueError("Report source must be either 'database' or 'files'.")
    if export_images:
        ensure_static_export_ready()

    experiment_path = Path(experiment_dir).expanduser().resolve()
    run_dirs = discover_run_directories(experiment_path)
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found under {experiment_path}")

    report_dir = _comparison_output_dir(experiment_path, output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    runs_index = build_runs_index(experiment_path)
    # Diagnostics and return series are keyed by (run, asset), so a comparison
    # across runs is simultaneously a comparison across markets: every asset of
    # every run is screened and plotted, not just the nominated primary one.
    diagnostics = build_asset_stylised_fact_diagnostics(
        run_dirs,
        phase=phase,
        price_column=price_column,
    )
    return_series_by_run = build_return_series_by_asset(
        run_dirs,
        phase=phase,
        price_column=price_column,
    )
    pairwise_ks = build_pairwise_ks_table(return_series_by_run)
    all_run_ids = runs_index["run_id"].astype(str).tolist()
    run_labels = build_simulation_labels(all_run_ids)
    series_labels = _asset_series_labels(run_labels, return_series_by_run)
    labelled_runs_index = _add_simulation_labels(runs_index, run_labels)
    labelled_diagnostics = _add_simulation_labels(diagnostics, run_labels)
    labelled_pairwise_ks = _add_pairwise_simulation_labels(pairwise_ks, series_labels)
    selected_run_ids = select_display_run_ids(runs_index, max_runs=max_runs)
    selected_series_ids = _series_ids_for_runs(selected_run_ids, return_series_by_run)
    agent_summary = build_agent_summary_statistics(experiment_path, selected_run_ids, run_labels)
    simulation_label_note = _simulation_label_table(runs_index, run_labels)
    benchmarks = _load_benchmarks(benchmark_dir, benchmark_series)
    benchmark_returns = build_benchmark_return_series(benchmarks)
    benchmark_diagnostics = build_benchmark_diagnostics(benchmarks)
    simulation_vs_benchmark = build_simulation_benchmark_comparison(
        return_series_by_run,
        benchmark_returns,
        run_labels=series_labels,
    )
    seed_robustness = build_seed_robustness_summary(runs_index, diagnostics)
    simulation_stress = build_simulation_stress_diagnostics(
        experiment_path,
        all_run_ids,
        phase=phase,
        price_column=price_column,
    )
    benchmark_stress = build_benchmark_stress_diagnostics(benchmarks)
    stress_diagnostics = _concat_frames([simulation_stress, benchmark_stress])

    runs_index_csv_path = report_dir / "runs_index.csv"
    diagnostics_csv_path = report_dir / "stylised_fact_diagnostics.csv"
    pairwise_ks_csv_path = report_dir / "pairwise_ks_log_returns.csv"
    agent_summary_csv_path = report_dir / "agent_summary_statistics.csv"
    benchmark_diagnostics_csv_path = report_dir / "benchmark_diagnostics.csv"
    simulation_vs_benchmark_csv_path = report_dir / "simulation_vs_benchmark.csv"
    seed_robustness_csv_path = report_dir / "seed_robustness_summary.csv"
    stress_regime_csv_path = report_dir / "stress_regime_diagnostics.csv"
    figure_index_csv_path = report_dir / "figure_index.csv"
    labelled_runs_index.to_csv(runs_index_csv_path, index=False)
    labelled_diagnostics.to_csv(diagnostics_csv_path, index=False)
    labelled_pairwise_ks.to_csv(pairwise_ks_csv_path, index=False)
    agent_summary.to_csv(agent_summary_csv_path, index=False)
    benchmark_diagnostics.to_csv(benchmark_diagnostics_csv_path, index=False)
    simulation_vs_benchmark.to_csv(simulation_vs_benchmark_csv_path, index=False)
    seed_robustness.to_csv(seed_robustness_csv_path, index=False)
    stress_diagnostics.to_csv(stress_regime_csv_path, index=False)

    figure_objects = _comparison_figures(
        experiment_path,
        selected_run_ids,
        run_labels,
        return_series_by_run,
        pairwise_ks,
        benchmark_returns,
        seed_robustness,
        phase=phase,
        price_column=price_column,
        series_ids=selected_series_ids,
        series_labels=series_labels,
    )
    table_previews = {
        "stylised_fact_diagnostics": _table_preview(
            labelled_diagnostics,
            hidden_columns={"run_id"},
        ),
        "pairwise_ks": _table_preview(
            labelled_pairwise_ks,
            hidden_columns={"run_id_a", "run_id_b"},
        ),
        "agent_summary": _table_preview(
            agent_summary,
            hidden_columns={"run_id"},
        ),
        "seed_robustness": _table_preview(
            seed_robustness,
            hidden_columns={"condition_description"},
        ),
        "benchmark_scorecard": _table_preview(
            benchmark_diagnostics,
            hidden_columns={"source_file"},
        ),
        "simulation_vs_benchmark": _table_preview(
            simulation_vs_benchmark,
            hidden_columns={"run_id"},
        ),
    }
    sections = _comparison_report_sections(
        figure_objects,
        table_previews,
        has_benchmarks=bool(benchmarks),
    )

    report_path = report_dir / "index.html"
    _render_report(
        report_path,
        title=f"ABM Experiment Comparison: {experiment_path.name}",
        meta_line=(
            f"Experiment: {experiment_path.name} · {len(run_dirs)} run(s) "
            f"· phase: {phase} · price series: {price_column}"
        ),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        key_metrics=_comparison_key_metric_rows(runs_index, diagnostics),
        evidence_rows=build_comparison_evidence_assessment(diagnostics),
        sections=sections,
        appendices=_appendices(
            output_files=[
                "runs_index.csv",
                "stylised_fact_diagnostics.csv",
                "pairwise_ks_log_returns.csv",
                "benchmark_diagnostics.csv",
                "simulation_vs_benchmark.csv",
                "seed_robustness_summary.csv",
                "agent_summary_statistics.csv",
            ],
            run_inventory_tables=[
                (
                    "Runs Index",
                    _table_preview(
                        labelled_runs_index,
                        hidden_columns={"run_id", "run_directory"},
                    ),
                ),
                ("Data Label Notes", simulation_label_note),
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

    return ComparisonReportResult(
        report_path=report_path,
        output_dir=report_dir,
        runs_index_csv_path=runs_index_csv_path,
        diagnostics_csv_path=diagnostics_csv_path,
        pairwise_ks_csv_path=pairwise_ks_csv_path,
        benchmark_diagnostics_csv_path=benchmark_diagnostics_csv_path,
        simulation_vs_benchmark_csv_path=simulation_vs_benchmark_csv_path,
        seed_robustness_csv_path=seed_robustness_csv_path,
        stress_regime_csv_path=stress_regime_csv_path,
        figure_index_csv_path=figure_index_csv_path,
        agent_summary_csv_path=agent_summary_csv_path,
    )
