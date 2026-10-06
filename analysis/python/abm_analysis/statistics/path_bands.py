"""Price-path bands across seeds: how much of a market's history is the draw.

A single run is one history. Whether its crash is a property of the model or an
accident of the random seed is a question about the *spread of histories*, and
the cohort view's tables answer it with moments. This module answers it with the
histories themselves: for each experimental condition, the median path across
seeds and the band the individual paths stay inside.

Two measures are summarised, chosen because they can be compared across seeds:

``indexed_price``
    The price divided by its first value in the window, times one hundred. Seeds
    that start at the same price but draw different fundamentals still share a
    starting point, so the fan opens from one place.
``log_mispricing``
    ``ln(price / fundamental)``. Each seed's fundamental is its own random walk,
    so raw price paths differ partly because the *target* they track differs;
    the log gap removes that and isolates what the traders did with it.

**The band is a range, not a confidence interval.** With a handful of seeds there
are too few paths for percentiles to mean anything, so the band is the minimum
and maximum across seeds until there are enough for the 10th–90th percentile
band, and the payload says which one it is. Neither is an interval for the
median: it describes where histories went, not how well the median is known.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from abm_analysis.archive.timeseries import load_step_timeseries, step_axis_column
from abm_analysis.statistics.multi_asset import list_assets, load_asset_panel
from abm_analysis.statistics.stress import compute_log_mispricing


#: The measures summarised, in the order the interface offers them.
PATH_MEASURES = ("indexed_price", "log_mispricing")

#: Seeds needed before the band switches from min–max to percentiles. Percentiles
#: of fewer than ten paths are interpolations between neighbours, not estimates.
MINIMUM_SEEDS_FOR_PERCENTILES = 10

#: Percentile band used once there are enough seeds.
PERCENTILE_BAND = (0.10, 0.90)


@dataclass(frozen=True)
class PathBand:
    """The median path and spread band of one measure across seeds.

    ``band_kind`` is ``"range"`` (minimum to maximum) or ``"percentile"`` (10th
    to 90th). ``members`` holds each seed's own path on the same steps, so the
    interface can draw the individual histories behind the band.
    """

    step: np.ndarray
    median: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    members: tuple[np.ndarray, ...]
    seed_count: int
    band_kind: str


def load_run_price_paths(
    run_dir: Path | str,
    *,
    phase: str,
    price_column: str,
    single_asset_name: str,
) -> dict[str, pd.DataFrame]:
    """Read one run's price and fundamental paths, per traded asset.

    Args:
        run_dir: Archived run directory.
        phase: Step phase analysed; ``"all"`` includes warm-up on a single-asset run.
        price_column: Price column the paths are drawn from.
        single_asset_name: Name to file a single-market run's one path under. Such
            a run records no asset name of its own, so the caller supplies the one
            the rest of its cohort uses.

    Returns:
        ``{asset: frame}`` where each frame is indexed by step and has ``price``
        and ``fundamental`` columns. A run with several markets contributes each
        under its recorded name.
    """

    recorded = list_assets(run_dir)
    if len(recorded) >= 2:
        prices = load_asset_panel(run_dir, price_column, phase=phase)
        fundamentals = load_asset_panel(run_dir, "fundamental_price", phase=phase)
        if not prices.empty and prices.shape[1] >= 2:
            return {
                str(asset): pd.DataFrame(
                    {
                        "price": prices[asset],
                        "fundamental": (
                            fundamentals[asset]
                            if asset in fundamentals.columns
                            else pd.Series(np.nan, index=prices.index)
                        ),
                    }
                )
                for asset in prices.columns
            }

    series = load_step_timeseries(run_dir, price_column=price_column)
    if phase.lower() != "all" and "phase" in series.columns:
        series = series[series["phase"] == phase]
    if series.empty:
        return {}
    axis = step_axis_column(series)
    frame = pd.DataFrame(
        {
            "price": pd.to_numeric(series[price_column], errors="coerce").to_numpy(),
            "fundamental": (
                pd.to_numeric(series["fundamental_price"], errors="coerce").to_numpy()
                if "fundamental_price" in series.columns
                else np.nan
            ),
        },
        index=pd.Index(pd.to_numeric(series[axis], errors="coerce").to_numpy(), name=axis),
    )
    return {single_asset_name: frame[~frame.index.duplicated(keep="last")]}


def build_path_measures(paths: pd.DataFrame) -> dict[str, pd.Series]:
    """Turn one run's price and fundamental paths into the comparable measures."""

    price = pd.to_numeric(paths["price"], errors="coerce")
    usable = price[np.isfinite(price) & (price > 0)]
    indexed = (
        100.0 * price / float(usable.iloc[0])
        if not usable.empty
        else pd.Series(np.nan, index=price.index)
    )
    return {
        "indexed_price": indexed,
        "log_mispricing": compute_log_mispricing(price, paths["fundamental"]),
    }


def summarise_path_band(paths: Sequence[pd.Series]) -> PathBand | None:
    """Summarise several seeds' paths of one measure as a median and a band.

    The paths are aligned on the steps *every* seed has, so the band at a step is
    always taken over the same set of seeds. A longer path is cut to the shortest
    rather than padded, because a band over fewer seeds at the end of the chart
    would silently narrow and read as convergence.

    Returns:
        ``None`` when no path is usable or the seeds share no step.
    """

    usable = [pd.to_numeric(path, errors="coerce") for path in paths if len(path)]
    if not usable:
        return None
    # Keyed explicitly: every seed's series carries the same name, and duplicate
    # column labels would make selecting one seed's path return all of them.
    aligned = pd.concat(usable, axis=1, join="inner", keys=range(len(usable))).sort_index()
    aligned = aligned.dropna(how="all")
    if aligned.empty:
        return None

    seed_count = int(aligned.shape[1])
    if seed_count >= MINIMUM_SEEDS_FOR_PERCENTILES:
        lower = aligned.quantile(PERCENTILE_BAND[0], axis=1)
        upper = aligned.quantile(PERCENTILE_BAND[1], axis=1)
        band_kind = "percentile"
    else:
        lower, upper = aligned.min(axis=1), aligned.max(axis=1)
        band_kind = "range"

    return PathBand(
        step=aligned.index.to_numpy(dtype=float),
        median=aligned.median(axis=1).to_numpy(dtype=float),
        lower=lower.to_numpy(dtype=float),
        upper=upper.to_numpy(dtype=float),
        members=tuple(aligned[column].to_numpy(dtype=float) for column in aligned.columns),
        seed_count=seed_count,
        band_kind=band_kind,
    )
