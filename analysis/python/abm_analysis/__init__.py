"""Python analysis tools for behavioural-finance ABM experiment archives.

The package reads the C++ simulator's reproducible experiment folders and
produces Python-only diagnostics, exported as CSV tables by
``abm_analysis.exports`` and browsable in the local dashboard served by
``abm_analysis.web``. The statistical workflow follows common empirical-finance
diagnostics for stylised facts: Cont-style return distribution checks,
Ljung-Box autocorrelation tests, Jarque-Bera normality tests, Engle ARCH tests,
Bollerslev GARCH volatility estimation, and Kolmogorov-Smirnov distribution
comparison.
"""

from abm_analysis.environment import configure_analysis_environment

configure_analysis_environment()

from abm_analysis.archive.data import discover_run_directories, parse_run_id
from abm_analysis.statistics.diagnostics import run_stylised_fact_diagnostics

__all__ = [
    "discover_run_directories",
    "parse_run_id",
    "run_stylised_fact_diagnostics",
]
