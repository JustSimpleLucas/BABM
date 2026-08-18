"""Machine-readable analysis tables written beside an archived experiment.

The dashboard (``abm_analysis.web``) is where results are *read*; this package is
where they are *kept*. A thesis needs the numbers behind a claim to exist as
files that can be cited, diffed and re-derived years later, which a server
rendering statistics on demand cannot provide.

Every table here is computed by ``abm_analysis.statistics`` — this package
decides only what goes in which file and how runs are labelled, so an exported
CSV and the dashboard panel showing the same statistic are the same number.
"""

from __future__ import annotations

from .calibration import CalibrationTables, write_calibration_tables
from .holdout import HoldoutTables, write_holdout_validation
from .seed_robustness import SeedRobustnessTables, write_seed_robustness_tables

__all__ = [
    "CalibrationTables",
    "HoldoutTables",
    "SeedRobustnessTables",
    "write_calibration_tables",
    "write_holdout_validation",
    "write_seed_robustness_tables",
]
