"""Figure assembly and figure-index export helpers for reports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from abm_analysis.archive.data import build_runs_index
from abm_analysis.statistics.multi_asset import list_assets
from abm_analysis.plots import (
    make_acf_figure,
    make_asset_allocative_efficiency_figure,
    make_asset_microstructure_liquidity_figure,
    make_asset_microstructure_quotes_figure,
    make_asset_order_flow_figure,
    make_asset_price_fundamental_figure,
    make_asset_return_path_figure,
    make_asset_volume_volatility_figure,
    make_cross_asset_figure,
    make_portfolio_composition_figure,
    make_allocative_efficiency_timeseries_figure,
    make_agent_behavioural_outcome_figure,
    make_agent_portfolio_distribution_figure,
    make_agent_reference_point_figure,
    make_agent_return_lorenz_figure,
    make_agent_trading_activity_figure,
    make_agent_wealth_figure,
    make_ks_heatmap_figure,
    make_market_fundamental_log_return_figure,
    make_metric_comparison_figure,
    make_microstructure_liquidity_figure,
    make_microstructure_quotes_figure,
    make_order_flow_microstructure_figure,
    make_price_timeseries_figure,
    make_return_ecdf_figure,
    make_return_histogram_figure,
    make_return_tail_figure,
    make_seed_robustness_figure,
    make_simulation_benchmark_ecdf_figure,
    make_simulation_benchmark_qq_figure,
    make_trade_volume_figure,
    make_wealth_gini_timeseries_figure,
)

from .static_export import (
    STATIC_EXPORT_FORMATS,
    StaticFigureExportError,
    export_publication_figures,
)

@dataclass(frozen=True)
class FigureContext:
    """Inputs shared by every run-level figure builder.

    Two id spaces are in play. ``run_ids`` names run directories and drives the
    figures that read archives from disk. ``series_ids`` keys ``return_series``
    and drives the distribution figures; on a multi-asset run it names one
    series per (run, asset) so each market is plotted in its own right.
    """

    experiment_path: Path
    run_ids: list[str]
    run_labels: dict[str, str]
    return_series: dict[str, pd.Series]
    series_ids: list[str]
    series_labels: dict[str, str]
    benchmark_returns: dict[str, pd.Series]
    phase: str
    price_column: str
    pairwise_ks: pd.DataFrame | None = None
    seed_robustness: pd.DataFrame | None = None

    @property
    def benchmark_ids(self) -> list[str]:
        """Benchmark series in a stable order for legends and comparisons."""

        return sorted(self.benchmark_returns)


@dataclass(frozen=True)
class FigureSpec:
    """One report figure: the name it is indexed under and how to build it.

    Declaring the two together is the point. The builders take deliberately
    different arguments — some read archives, some take pre-computed return
    series — so the call sites used to be a long dict literal in which each
    entry spelled out its own inputs, and "which figures exist, and what does
    each need?" could only be answered by reading all of them.
    """

    name: str
    build: Callable[[FigureContext], object]

    #: Skip this figure when the report has no benchmark series to compare against.
    requires_benchmarks: bool = False


_SHARED_RUN_FIGURES: tuple[FigureSpec, ...] = (
    FigureSpec(
        "price_timeseries",
        lambda c: make_price_timeseries_figure(
            c.experiment_path, c.run_ids, price_column=c.price_column, run_labels=c.run_labels
        ),
    ),
    FigureSpec(
        "market_fundamental_log_returns",
        lambda c: make_market_fundamental_log_return_figure(
            c.experiment_path,
            c.run_ids,
            price_column=c.price_column,
            phase=c.phase,
            run_labels=c.run_labels,
        ),
    ),
    FigureSpec(
        "trade_volume",
        lambda c: make_trade_volume_figure(c.experiment_path, c.run_ids, c.run_labels),
    ),
    FigureSpec(
        "microstructure_quotes",
        lambda c: make_microstructure_quotes_figure(
            c.experiment_path, c.run_ids, run_labels=c.run_labels
        ),
    ),
    FigureSpec(
        "microstructure_liquidity",
        lambda c: make_microstructure_liquidity_figure(
            c.experiment_path, c.run_ids, c.run_labels
        ),
    ),
    FigureSpec(
        "order_flow_microstructure",
        lambda c: make_order_flow_microstructure_figure(
            c.experiment_path, c.run_ids, c.run_labels
        ),
    ),
    FigureSpec(
        "allocative_efficiency_timeseries",
        lambda c: make_allocative_efficiency_timeseries_figure(
            c.experiment_path, c.run_ids, c.run_labels
        ),
    ),
    FigureSpec(
        "return_histogram",
        lambda c: make_return_histogram_figure(
            c.return_series,
            c.series_ids,
            c.series_labels,
            experiment_dir=c.experiment_path,
            phase=c.phase,
            price_column=c.price_column,
            agent_run_ids=c.run_ids,
        ),
    ),
    FigureSpec(
        "return_ecdf",
        lambda c: make_return_ecdf_figure(c.return_series, c.series_ids, c.series_labels),
    ),
    FigureSpec(
        "acf",
        lambda c: make_acf_figure(c.return_series, c.series_ids, run_labels=c.series_labels),
    ),
    FigureSpec(
        "agent_wealth",
        lambda c: make_agent_wealth_figure(c.experiment_path, c.run_ids, c.run_labels),
    ),
    FigureSpec(
        "agent_return_lorenz",
        lambda c: make_agent_return_lorenz_figure(c.experiment_path, c.run_ids, c.run_labels),
    ),
    FigureSpec(
        "wealth_gini_timeseries",
        lambda c: make_wealth_gini_timeseries_figure(c.experiment_path, c.run_ids, c.run_labels),
    ),
    FigureSpec(
        "agent_portfolio_distribution",
        lambda c: make_agent_portfolio_distribution_figure(
            c.experiment_path, c.run_ids, c.run_labels
        ),
    ),
    FigureSpec(
        "agent_trading_activity",
        lambda c: make_agent_trading_activity_figure(c.experiment_path, c.run_ids, c.run_labels),
    ),
    FigureSpec(
        "agent_reference_points",
        lambda c: make_agent_reference_point_figure(c.experiment_path, c.run_ids, c.run_labels),
    ),
    FigureSpec(
        "agent_behavioural_outcomes",
        lambda c: make_agent_behavioural_outcome_figure(
            c.experiment_path, c.run_ids, c.run_labels
        ),
    ),
    FigureSpec(
        "simulation_benchmark_ecdf",
        lambda c: make_simulation_benchmark_ecdf_figure(
            c.return_series,
            c.benchmark_returns,
            c.series_ids,
            benchmark_ids=c.benchmark_ids,
            run_labels=c.series_labels,
        ),
        requires_benchmarks=True,
    ),
    FigureSpec(
        "simulation_benchmark_qq",
        lambda c: make_simulation_benchmark_qq_figure(
            c.return_series,
            c.benchmark_returns,
            c.series_ids,
            benchmark_ids=c.benchmark_ids,
            run_labels=c.series_labels,
        ),
        requires_benchmarks=True,
    ),
    FigureSpec(
        "return_tail_quantiles",
        lambda c: make_return_tail_figure(
            c.return_series,
            c.benchmark_returns,
            c.series_ids,
            benchmark_ids=c.benchmark_ids,
            run_labels=c.series_labels,
        ),
        requires_benchmarks=True,
    ),
)


#: Comparison reports add cross-run figures the single-run report has no inputs
#: for: the runs index, pairwise KS statistics, and repeated-seed conditions.
#: Order matters — the figure index is written in build order.
_COMPARISON_FIGURES: tuple[FigureSpec, ...] = (
    FigureSpec(
        "metric_comparison",
        lambda c: make_metric_comparison_figure(
            build_runs_index(c.experiment_path), c.run_labels
        ),
    ),
    *_SHARED_RUN_FIGURES,
    FigureSpec(
        "ks_heatmap",
        lambda c: make_ks_heatmap_figure(
            c.pairwise_ks, sorted(c.return_series), c.series_labels
        ),
    ),
    FigureSpec(
        "seed_robustness",
        lambda c: make_seed_robustness_figure(c.seed_robustness),
    ),
)


def _build_figures(
    specs: tuple[FigureSpec, ...], context: FigureContext
) -> dict[str, object]:
    """Build every applicable spec, preserving declaration order."""

    return {
        spec.name: spec.build(context)
        for spec in specs
        if context.benchmark_returns or not spec.requires_benchmarks
    }


def _make_context(
    experiment_path: Path,
    run_ids: list[str],
    run_labels: dict[str, str],
    return_series_by_run: dict[str, pd.Series],
    benchmark_returns: dict[str, pd.Series],
    *,
    phase: str,
    price_column: str,
    series_ids: list[str] | None = None,
    series_labels: dict[str, str] | None = None,
    pairwise_ks: pd.DataFrame | None = None,
    seed_robustness: pd.DataFrame | None = None,
) -> FigureContext:
    return FigureContext(
        experiment_path=experiment_path,
        run_ids=run_ids,
        run_labels=run_labels,
        return_series=return_series_by_run,
        series_ids=list(run_ids) if series_ids is None else series_ids,
        series_labels=run_labels if series_labels is None else series_labels,
        benchmark_returns=benchmark_returns,
        phase=phase,
        price_column=price_column,
        pairwise_ks=pairwise_ks,
        seed_robustness=seed_robustness,
    )


def _comparison_figures(
    experiment_path: Path,
    selected_run_ids: list[str],
    run_labels: dict[str, str],
    return_series_by_run: dict[str, pd.Series],
    pairwise_ks: pd.DataFrame,
    benchmark_returns: dict[str, pd.Series],
    seed_robustness: pd.DataFrame,
    *,
    phase: str,
    price_column: str,
    series_ids: list[str] | None = None,
    series_labels: dict[str, str] | None = None,
) -> dict[str, object]:
    return _build_figures(
        _COMPARISON_FIGURES,
        _make_context(
            experiment_path,
            selected_run_ids,
            run_labels,
            return_series_by_run,
            benchmark_returns,
            phase=phase,
            price_column=price_column,
            series_ids=series_ids,
            series_labels=series_labels,
            pairwise_ks=pairwise_ks,
            seed_robustness=seed_robustness,
        ),
    )


def multi_asset_figures(run_dir: Path, *, phase: str) -> dict[str, object]:
    """Build the cross-asset figures for one run.

    Returns an empty mapping unless the run actually traded two or more risky
    assets. That keeps single-asset reports byte-for-byte unchanged: no extra
    figures are built, none are exported, and the report layer drops the whole
    section rather than rendering empty panels.

    Only genuinely cross-asset content lives here. The per-asset price,
    liquidity, order-flow, and efficiency panels are not an appendix to the
    report — they replace their primary-asset counterparts in the core sections
    through :func:`per_asset_core_figures`.
    """

    if len(list_assets(run_dir)) < 2:
        return {}

    return {
        "cross_asset_dependence": make_cross_asset_figure(run_dir, phase=phase),
        "portfolio_composition": make_portfolio_composition_figure(run_dir, phase=phase),
    }


def per_asset_core_figures(run_dir: Path, *, phase: str) -> dict[str, object]:
    """Build per-asset replacements for the run-level core figures.

    A multi-asset run has one price path, one order book, and one efficiency
    series *per asset*, so the run-level figures — which read the single-asset
    ``step_timeseries.csv`` projection of whichever asset is nominated primary —
    would show only part of the market. These replacements keep the same figure
    names, so section layout, the figure index, and static exports are unchanged
    while every asset is drawn.

    Returns an empty mapping for single-asset runs, where the run-level figures
    already describe the whole market.
    """

    if len(list_assets(run_dir)) < 2:
        return {}

    return {
        "price_timeseries": make_asset_price_fundamental_figure(run_dir, phase=phase),
        "market_fundamental_log_returns": make_asset_return_path_figure(run_dir, phase=phase),
        "trade_volume": make_asset_volume_volatility_figure(run_dir, phase=phase),
        "microstructure_quotes": make_asset_microstructure_quotes_figure(run_dir, phase=phase),
        "microstructure_liquidity": make_asset_microstructure_liquidity_figure(
            run_dir,
            phase=phase,
        ),
        "order_flow_microstructure": make_asset_order_flow_figure(run_dir, phase=phase),
        "allocative_efficiency_timeseries": make_asset_allocative_efficiency_figure(
            run_dir,
            phase=phase,
        ),
    }


def _run_figures(
    experiment_path: Path,
    run_id: str,
    run_labels: dict[str, str],
    return_series_by_run: dict[str, pd.Series],
    benchmark_returns: dict[str, pd.Series],
    *,
    phase: str,
    price_column: str,
    series_labels: dict[str, str] | None = None,
) -> dict[str, object]:
    return _build_figures(
        _SHARED_RUN_FIGURES,
        _make_context(
            experiment_path,
            [run_id],
            run_labels,
            return_series_by_run,
            benchmark_returns,
            phase=phase,
            price_column=price_column,
            series_ids=list(return_series_by_run),
            series_labels=series_labels,
        ),
    )


def _figure_display_title(figure_name: str, figure: object) -> str:
    return str(getattr(figure.layout.title, "text", "") or figure_name)

def _build_figure_index(
    report_dir: Path,
    figure_objects: dict[str, object],
    *,
    export_images: bool,
    figure_formats: tuple[str, ...] = STATIC_EXPORT_FORMATS,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    figure_dir = report_dir / "figures"
    export_rows: dict[str, dict[str, object]] = {}
    if export_images:
        figure_dir.mkdir(parents=True, exist_ok=True)
        export_rows = {
            str(row["figure_name"]): row
            for row in export_publication_figures(
                figure_dir,
                figure_objects,
                formats=tuple(figure_formats),
            )
        }

    for figure_name, figure in figure_objects.items():
        row: dict[str, object] = {
            "figure_name": figure_name,
            "figure_title": _figure_display_title(figure_name, figure),
            "html_report": "index.html",
            "png_file": "",
            "pdf_file": "",
            "svg_file": "",
            "export_status": "html_only",
            "export_message": "",
        }
        if export_images:
            row.update(export_rows[figure_name])
        rows.append(row)
    return pd.DataFrame(rows)

def _raise_on_export_failures(figure_index: pd.DataFrame) -> None:
    """Fail loudly (after the HTML report is safely on disk) if exports failed."""

    failed = figure_index[figure_index["export_status"] == "export_failed"]
    if failed.empty:
        return
    names = ", ".join(failed["figure_name"].astype(str))
    first_message = str(failed["export_message"].iloc[0])
    raise StaticFigureExportError(
        f"Static image export failed for {len(failed)} figure(s): {names}. "
        f"First error: {first_message}. The HTML report and figure_index.csv "
        "were still written; rerun with --no-export-images to skip static figures."
    )
