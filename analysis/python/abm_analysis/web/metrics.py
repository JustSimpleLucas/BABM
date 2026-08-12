"""Cell builders and column helpers shared by the dashboard's view modules.

``asset_view`` and ``agent_view`` both need the same small vocabulary — a
metric cell, a finite-numbers view of a DataFrame column, a density histogram —
and ``run_view`` imports both. Keeping that vocabulary here rather than in
either view is what stops the three modules importing each other in a circle.

Nothing in this module computes a research statistic. The moments, tests and
verdicts all come from ``abm_analysis.statistics``; these are presentation
helpers and array plumbing.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from abm_analysis.web.serialisation import numeric_or_none


#: Points per chart series before stride sampling kicks in. Runs in this
#: project are a few thousand steps, so the cap is a guard against pathological
#: archives rather than a routine transformation; when it does bite, the
#: payload reports the stride so the interface can say the chart is thinned.
MAXIMUM_SERIES_POINTS = 8000

#: Provenance label for numbers this layer recomputes from a run's artefacts,
#: as opposed to scalars read straight out of ``summary_metrics.csv``.
PYTHON_DIAGNOSTICS_SOURCE = "python diagnostics"

#: Provenance label for scalars the C++ simulator wrote.
SIMULATOR_SUMMARY_SOURCE = "simulator summary"


def metric(
    label: str,
    value: Any,
    *,
    format: str,
    source: str = PYTHON_DIAGNOSTICS_SOURCE,
    emphasis: bool = False,
) -> dict[str, Any]:
    """Build one single-value cell, carrying the provenance of its number.

    Used by the agent and cross-asset panels, where a statistic describes the
    run as a whole rather than one traded asset.
    """

    return {
        "label": label,
        "value": numeric_or_none(value),
        "format": format,
        "source": source,
        "emphasis": emphasis,
    }


def asset_metric(
    label: str,
    values: dict[str, Any],
    *,
    format: str,
    source: str = PYTHON_DIAGNOSTICS_SOURCE,
    emphasis: bool = False,
    scope: str = "asset",
) -> dict[str, Any]:
    """Build one row of the per-asset metrics table.

    ``scope`` is ``"asset"`` when the statistic is computed per traded asset and
    ``"primary"`` when the archive only records it for the primary asset. The
    interface renders the missing cells of a ``"primary"`` row as absent rather
    than repeating the primary asset's number under another asset's heading,
    which would read as a measurement that was never made.
    """

    return {
        "label": label,
        "values": {name: numeric_or_none(value) for name, value in values.items()},
        "format": format,
        "source": source,
        "emphasis": emphasis,
        "scope": scope,
    }


def evidence(label: str, value: Any, format: str) -> dict[str, Any]:
    """Build one supporting statistic beneath a stylised-fact verdict."""

    if format == "flag":
        number = numeric_or_none(value)
        return {"label": label, "value": None if number is None else bool(number), "format": "flag"}
    return {"label": label, "value": numeric_or_none(value), "format": format}


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return one column coerced to finite numbers, or an empty series."""

    if column not in frame.columns:
        return pd.Series(dtype="float64")
    values = pd.to_numeric(frame[column], errors="coerce")
    return values[np.isfinite(values)]


def column_sum(frame: pd.DataFrame, column: str) -> float | None:
    """Return the sum of one column's finite values, or ``None`` if there are none."""

    values = numeric_column(frame, column)
    return float(values.sum()) if not values.empty else None


def column_mean(frame: pd.DataFrame, column: str, *, absolute: bool = False) -> float | None:
    """Return the mean of one column's finite values, or ``None`` if there are none."""

    values = numeric_column(frame, column)
    if values.empty:
        return None
    return float(values.abs().mean() if absolute else values.mean())


def finite_values(values: Any) -> pd.Series:
    """Return the finite numeric entries of a series-like object."""

    numbers = pd.to_numeric(pd.Series(values), errors="coerce")
    return numbers[np.isfinite(numbers)]


def maximum_drawdown(prices: pd.Series) -> float | None:
    """Return the largest peak-to-trough decline of a price path, as a fraction.

    Reported as a positive number: 0.32 means the path fell 32% below its
    running maximum at the worst point of the analysed window.
    """

    if prices.empty:
        return None
    running_peak = prices.cummax()
    valid_peak = running_peak > 0
    if not valid_peak.any():
        return None
    drawdown = 1.0 - (prices[valid_peak] / running_peak[valid_peak])
    return float(drawdown.max())


def stride_for(count: int) -> int:
    """Return the sampling stride that keeps a chart series under the point cap."""

    if count <= 0:
        return 1
    return max(1, math.ceil(count / MAXIMUM_SERIES_POINTS))


def series_values(frame: pd.DataFrame, column: str) -> list[float | None]:
    """Return one column as a JSON-safe list, with gaps preserved as ``null``.

    Gaps are kept rather than dropped so every series stays index-aligned with
    the step axis; a chart must not silently shift a missing observation.
    """

    if column not in frame.columns:
        return []
    return values_of(frame[column])


def values_of(values: Any) -> list[float | None]:
    """Return a series-like object as a JSON-safe list, gaps preserved as ``null``."""

    numbers = pd.to_numeric(pd.Series(values), errors="coerce")
    return [None if not np.isfinite(number) else float(number) for number in numbers]


def first_finite(values: Any) -> float | None:
    """Return the first finite value of a series-like object, or ``None``."""

    finite = finite_values(values)
    return None if finite.empty else float(finite.iloc[0])


def density_histogram(values: np.ndarray, *, maximum_bins: int = 80) -> dict[str, Any]:
    """Build a normalised histogram, with a bin count scaled to the sample size.

    Returns the bin centres and densities rather than the raw observations, so
    the payload stays a fixed size whether the sample is 200 log returns or the
    wealth of 100,000 agents.
    """

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 2:
        return {"available": False}

    bin_count = int(min(maximum_bins, max(20, round(math.sqrt(finite.size)))))
    density, edges = np.histogram(finite, bins=bin_count, density=True)
    centres = (edges[:-1] + edges[1:]) / 2.0
    return {
        "available": True,
        "bin_centre": [float(value) for value in centres],
        "bin_edges": [float(value) for value in edges],
        "bin_width": float(edges[1] - edges[0]),
        "density": [float(value) for value in density],
    }


def density_on_edges(values: Any, bin_edges: list[float]) -> list[float]:
    """Return a normalised density for ``values`` over already-chosen bin edges.

    Sharing one set of edges across groups is what makes several densities
    comparable on a single axis; each group binned to its own range would put
    differently-scaled curves on top of each other.
    """

    finite = finite_values(values).to_numpy(dtype=float)
    if finite.size == 0 or len(bin_edges) < 2:
        return [0.0] * max(0, len(bin_edges) - 1)
    density, _ = np.histogram(finite, bins=np.asarray(bin_edges, dtype=float), density=True)
    return [float(value) for value in density]
