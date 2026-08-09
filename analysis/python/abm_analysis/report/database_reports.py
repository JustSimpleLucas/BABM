"""Database-backed report wrappers that materialise temporary file archives."""

from __future__ import annotations

from pathlib import Path
import tempfile

from abm_analysis.database import (
    DEFAULT_DATABASE_URL_ENV,
    export_benchmarks_from_database,
    export_experiment_archive_from_database,
    export_run_archive_from_database,
)

from .models import ComparisonReportResult, RunReportResult
from .paths import _default_database_comparison_output_dir, _default_database_run_output_dir
from .static_export import STATIC_EXPORT_FORMATS, ensure_static_export_ready


def _build_database_comparison_report(
    experiment_identifier: str,
    *,
    output_dir: Path | str | None,
    phase: str,
    price_column: str,
    max_runs: int,
    benchmark_dir: Path | str | None,
    benchmark_series: str | list[str] | tuple[str, ...] | None,
    export_images: bool,
    figure_formats: tuple[str, ...] = STATIC_EXPORT_FORMATS,
    database_url: str | None,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> ComparisonReportResult:
    """Build a report from PostgreSQL while reusing the file report pipeline."""

    from .comparison import build_comparison_report

    if export_images:
        ensure_static_export_ready()

    experiment_name = Path(str(experiment_identifier)).name
    report_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else _default_database_comparison_output_dir(experiment_name)
    )
    with tempfile.TemporaryDirectory(prefix="abm_sql_experiment_") as temp_dir:
        temp_root = Path(temp_dir)
        materialised_experiment = export_experiment_archive_from_database(
            experiment_name,
            temp_root / "experiments",
            database_url,
            database_url_env=database_url_env,
        )
        effective_benchmark_dir = benchmark_dir
        if effective_benchmark_dir is None:
            effective_benchmark_dir = export_benchmarks_from_database(
                temp_root / "benchmarks",
                database_url,
                database_url_env=database_url_env,
                benchmark_series=benchmark_series,
            )
        return build_comparison_report(
            materialised_experiment,
            output_dir=report_dir,
            phase=phase,
            price_column=price_column,
            max_runs=max_runs,
            benchmark_dir=effective_benchmark_dir,
            benchmark_series=benchmark_series,
            export_images=export_images,
            figure_formats=figure_formats,
            source="files",
        )


def _build_database_run_report(
    run_identifier: str,
    *,
    output_dir: Path | str | None,
    phase: str,
    price_column: str,
    benchmark_dir: Path | str | None,
    benchmark_series: str | list[str] | tuple[str, ...] | None,
    export_images: bool,
    figure_formats: tuple[str, ...] = STATIC_EXPORT_FORMATS,
    database_url: str | None,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
) -> RunReportResult:
    """Build a single-run report from PostgreSQL."""

    from .run import build_run_report

    if export_images:
        ensure_static_export_ready()

    run_id = Path(str(run_identifier)).name
    report_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else _default_database_run_output_dir(run_id)
    )
    with tempfile.TemporaryDirectory(prefix="abm_sql_run_") as temp_dir:
        temp_root = Path(temp_dir)
        materialised_run = export_run_archive_from_database(
            run_id,
            temp_root / "experiments",
            database_url,
            database_url_env=database_url_env,
        )
        effective_benchmark_dir = benchmark_dir
        if effective_benchmark_dir is None:
            effective_benchmark_dir = export_benchmarks_from_database(
                temp_root / "benchmarks",
                database_url,
                database_url_env=database_url_env,
                benchmark_series=benchmark_series,
            )
        return build_run_report(
            materialised_run,
            output_dir=report_dir,
            phase=phase,
            price_column=price_column,
            benchmark_dir=effective_benchmark_dir,
            benchmark_series=benchmark_series,
            export_images=export_images,
            figure_formats=figure_formats,
            source="files",
        )
