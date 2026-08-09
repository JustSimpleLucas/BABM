"""Compatibility facade for static HTML ABM report builders."""

from __future__ import annotations

from .comparison import build_comparison_report
from .database_reports import _build_database_comparison_report, _build_database_run_report
from .run import build_run_report
from .seed_robustness import build_seed_robustness_report


__all__ = [
    "_build_database_comparison_report",
    "_build_database_run_report",
    "build_comparison_report",
    "build_run_report",
    "build_seed_robustness_report",
]
