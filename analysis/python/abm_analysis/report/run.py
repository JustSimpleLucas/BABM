"""Single-run report construction for file-backed ABM archives."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from abm_analysis.benchmarks import build_benchmark_diagnostics, build_benchmark_return_series
from abm_analysis.comparisons import build_simulation_benchmark_comparison
from abm_analysis.data import build_run_archive, build_runs_index, prepare_return_series
from abm_analysis.database import DEFAULT_DATABASE_URL_ENV
from abm_analysis.diagnostics import run_asset_stylised_fact_diagnostics
from abm_analysis.multi_asset import asset_series_id, build_asset_return_series
from abm_analysis.plots import (
    build_agent_summary_statistics,
    build_asset_configuration_table,
    build_simulation_labels,
)
from abm_analysis.robustness import build_seed_robustness_summary
from abm_analysis.stress import build_benchmark_stress_diagnostics, build_simulation_stress_diagnostics

from .evidence import build_run_evidence_assessment
from .figures import (
    _build_figure_index,
    _raise_on_export_failures,
    _run_figures,
    multi_asset_figures,
    per_asset_core_figures,
)
from .static_export import STATIC_EXPORT_FORMATS, ensure_static_export_ready
from .labels import _add_simulation_labels
from .models import RunReportResult
from .paths import _concat_frames, _load_benchmarks
from .rendering import _render_report, _table_preview
from .sections import _appendices, _run_report_sections
from .summaries import _run_key_metric_rows


def _returns_export_frame(
    returns_by_asset: dict[str, pd.Series],
    fallback_returns: pd.Series,
) -> pd.DataFrame:
    """Assemble the exported log-return table, one long row per (asset, return).

    A long format is used rather than one column per asset because the assets'
    return series need not be the same length: an asset whose book never trades
    contributes fewer finite returns, and padding it to a common index would
    invent observations.

    Archives without a per-asset artefact fall back to the single-asset series
    and keep the original ``log_return`` column, so previously generated exports
    remain readable by the same tooling.
    """

    if not returns_by_asset:
        return pd.DataFrame({"log_return": fallback_returns})

    frames = [
        pd.DataFrame({"asset": asset, "log_return": series.to_numpy()})
        for asset, series in returns_by_asset.items()
    ]
    return pd.concat(frames, ignore_index=True)


def build_run_report(
    run_dir: Path | str,
    *,
    output_dir: Path | str | None = None,
    phase: str = "simulation",
    price_column: str = "market_price",
    benchmark_dir: Path | str | None = None,
    benchmark_series: str | list[str] | tuple[str, ...] | None = None,
    export_images: bool = False,
    figure_formats: tuple[str, ...] = STATIC_EXPORT_FORMATS,
    source: str = "files",
    database_url: str | None = None,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> RunReportResult:
    """Create diagnostics and a compact HTML report for one run directory."""

    if source == "database":
        from .database_reports import _build_database_run_report

        return _build_database_run_report(
            str(run_dir),
            output_dir=output_dir,
            phase=phase,
            price_column=price_column,
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

    archive = build_run_archive(run_dir)
    run_labels = build_simulation_labels([archive.run_id])
    display_label = run_labels[archive.run_id]
    report_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else archive.run_dir / "python_analysis"
    )
    report_dir.mkdir(parents=True, exist_ok=True)

    # One diagnostic row per traded asset. Every market is screened with the
    # same tests, so a two-asset run reports two verdicts rather than the
    # primary asset's verdict standing in for both.
    diagnostics = pd.DataFrame(
        run_asset_stylised_fact_diagnostics(
            archive.run_dir,
            phase=phase,
            price_column=price_column,
        )
    )
    labelled_diagnostics = _add_simulation_labels(diagnostics, run_labels)
    returns_by_asset = build_asset_return_series(archive.run_dir, phase=phase)
    agent_summary = build_agent_summary_statistics(
        archive.run_dir.parent,
        [archive.run_id],
        run_labels,
    )
    diagnostics_csv_path = report_dir / "stylised_fact_diagnostics.csv"
    returns_csv_path = report_dir / "computed_log_returns.csv"
    agent_summary_csv_path = report_dir / "agent_summary_statistics.csv"
    labelled_diagnostics.to_csv(diagnostics_csv_path, index=False)
    _returns_export_frame(
        returns_by_asset,
        prepare_return_series(archive.run_dir, phase=phase, price_column=price_column),
    ).to_csv(returns_csv_path, index=False)
    agent_summary.to_csv(agent_summary_csv_path, index=False)

    # Distribution figures are keyed by series, not by run, so each asset is
    # plotted as its own series instead of being folded into the primary one.
    if returns_by_asset:
        return_series_by_run = {
            asset_series_id(archive.run_id, asset): series
            for asset, series in returns_by_asset.items()
        }
        series_labels = {
            **run_labels,
            **{
                asset_series_id(archive.run_id, asset): f"{display_label} · {asset}"
                for asset in returns_by_asset
            },
        }
    else:
        return_series_by_run = {
            archive.run_id: prepare_return_series(
                archive.run_dir,
                phase=phase,
                price_column=price_column,
            )
        }
        series_labels = dict(run_labels)
    single_run_index = build_runs_index(archive.run_dir.parent)
    single_run_index = single_run_index[
        single_run_index["run_id"].astype(str) == archive.run_id
    ]
    if single_run_index.empty:
        single_run_index = pd.DataFrame([{"run_id": archive.run_id}])
    benchmarks = _load_benchmarks(benchmark_dir, benchmark_series)
    benchmark_returns = build_benchmark_return_series(benchmarks)
    benchmark_diagnostics = build_benchmark_diagnostics(benchmarks)
    simulation_vs_benchmark = build_simulation_benchmark_comparison(
        return_series_by_run,
        benchmark_returns,
        run_labels=series_labels,
    )
    seed_robustness = build_seed_robustness_summary(single_run_index, diagnostics)
    simulation_stress = build_simulation_stress_diagnostics(
        archive.run_dir.parent,
        [archive.run_id],
        phase=phase,
        price_column=price_column,
    )
    benchmark_stress = build_benchmark_stress_diagnostics(benchmarks)
    stress_diagnostics = _concat_frames([simulation_stress, benchmark_stress])

    benchmark_diagnostics_csv_path = report_dir / "benchmark_diagnostics.csv"
    simulation_vs_benchmark_csv_path = report_dir / "simulation_vs_benchmark.csv"
    seed_robustness_csv_path = report_dir / "seed_robustness_summary.csv"
    stress_regime_csv_path = report_dir / "stress_regime_diagnostics.csv"
    figure_index_csv_path = report_dir / "figure_index.csv"
    benchmark_diagnostics.to_csv(benchmark_diagnostics_csv_path, index=False)
    simulation_vs_benchmark.to_csv(simulation_vs_benchmark_csv_path, index=False)
    seed_robustness.to_csv(seed_robustness_csv_path, index=False)
    stress_diagnostics.to_csv(stress_regime_csv_path, index=False)

    figure_objects = _run_figures(
        archive.run_dir.parent,
        archive.run_id,
        run_labels,
        return_series_by_run,
        benchmark_returns,
        phase=phase,
        price_column=price_column,
        series_labels=series_labels,
    )
    # On a multi-asset run the core price, liquidity, order-flow, and efficiency
    # figures are rebuilt per asset under the same names, and the cross-asset
    # section is added. Both return nothing for a single-asset run, so every
    # pre-existing view renders exactly as before.
    figure_objects.update(per_asset_core_figures(archive.run_dir, phase=phase))
    figure_objects.update(multi_asset_figures(archive.run_dir, phase=phase))
    asset_configuration = build_asset_configuration_table(archive.run_dir)
    table_previews = {
        "stylised_fact_diagnostics": _table_preview(
            labelled_diagnostics,
            hidden_columns={"run_id"},
        ),
        "agent_summary": _table_preview(
            agent_summary,
            hidden_columns={"run_id"},
        ),
        # The benchmark scorecard drops source_file; the simulation-vs-benchmark
        # table keeps its per-series rows, which are now per-asset.
        "benchmark_scorecard": _table_preview(
            benchmark_diagnostics,
            hidden_columns={"source_file"},
        ),
        "simulation_vs_benchmark": _table_preview(
            simulation_vs_benchmark,
            hidden_columns={"run_id"},
        ),
    }
    if not asset_configuration.empty:
        table_previews["asset_configuration"] = _table_preview(asset_configuration)
    sections = _run_report_sections(
        figure_objects,
        table_previews,
        has_benchmarks=bool(benchmarks),
    )

    report_path = report_dir / "index.html"
    _render_report(
        report_path,
        title=f"ABM Run Analysis: {display_label}",
        meta_line=(
            f"Run: {archive.run_id} · phase: {phase} · price series: {price_column}"
        ),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        key_metrics=_run_key_metric_rows(single_run_index, diagnostics),
        evidence_rows=build_run_evidence_assessment(diagnostics),
        sections=sections,
        appendices=_appendices(
            output_files=[
                "stylised_fact_diagnostics.csv",
                "computed_log_returns.csv",
                "benchmark_diagnostics.csv",
                "simulation_vs_benchmark.csv",
                "seed_robustness_summary.csv",
                "agent_summary_statistics.csv",
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

    return RunReportResult(
        report_path=report_path,
        output_dir=report_dir,
        diagnostics_csv_path=diagnostics_csv_path,
        returns_csv_path=returns_csv_path,
        benchmark_diagnostics_csv_path=benchmark_diagnostics_csv_path,
        simulation_vs_benchmark_csv_path=simulation_vs_benchmark_csv_path,
        seed_robustness_csv_path=seed_robustness_csv_path,
        stress_regime_csv_path=stress_regime_csv_path,
        figure_index_csv_path=figure_index_csv_path,
        agent_summary_csv_path=agent_summary_csv_path,
    )
