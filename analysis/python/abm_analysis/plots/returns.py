"""Compatibility facade for return-distribution and benchmark-comparison figures."""

from __future__ import annotations

from .return_attribution import (
    _agent_strategy_participation_by_step,
    _histogram_bin_edges,
    _long_returns_by_agent_strategy,
    _make_agent_stacked_return_histogram,
    _return_step_column,
)
from .return_benchmarks import (
    make_return_tail_figure,
    make_simulation_benchmark_ecdf_figure,
    make_simulation_benchmark_qq_figure,
)
from .return_distributions import (
    _long_returns,
    make_acf_figure,
    make_ks_heatmap_figure,
    make_return_ecdf_figure,
    make_return_histogram_figure,
)


__all__ = [
    "_agent_strategy_participation_by_step",
    "_histogram_bin_edges",
    "_long_returns",
    "_long_returns_by_agent_strategy",
    "_make_agent_stacked_return_histogram",
    "_return_step_column",
    "make_acf_figure",
    "make_ks_heatmap_figure",
    "make_return_ecdf_figure",
    "make_return_histogram_figure",
    "make_return_tail_figure",
    "make_simulation_benchmark_ecdf_figure",
    "make_simulation_benchmark_qq_figure",
]
