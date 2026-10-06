"""Tests for price-path bands across seeds, and their place in the cohort payload.

The band is the cohort view's picture of "how much of this history is the draw",
so what matters is that it is described honestly: the median is the median of the
aligned paths, the band is a range while there are too few seeds for percentiles,
and a seed that is shorter than the rest shortens everyone rather than leaving a
band that silently narrows at the end.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from abm_analysis.statistics.path_bands import (
    MINIMUM_SEEDS_FOR_PERCENTILES,
    build_path_measures,
    load_run_price_paths,
    summarise_path_band,
)
from abm_analysis.web import cohort_view
from abm_analysis.web.cohort_view import build_cohort_view

from abm_test_helpers import write_synthetic_asset_timeseries, write_synthetic_run


#: Three seeds of one condition (prospect theory on, nothing else varying).
RUN_IDS = (
    ("20260501100001_1_0_0_0_20_30_5_2_180_11", 11),
    ("20260501100002_1_0_0_0_20_30_5_2_180_12", 12),
    ("20260501100003_1_0_0_0_20_30_5_2_180_13", 13),
)


def _paths(count: int, length: int = 50, seed: int = 0) -> list[pd.Series]:
    rng = np.random.default_rng(seed)
    return [
        pd.Series(rng.normal(size=length).cumsum(), index=np.arange(1, length + 1, dtype=float))
        for _ in range(count)
    ]


@pytest.fixture()
def cohort_dirs(tmp_path: Path) -> list[Path]:
    """Return three synthetic seeds of one condition."""

    directories = []
    for run_id, seed in RUN_IDS:
        run_dir = tmp_path / run_id
        write_synthetic_run(run_dir, run_id, seed, 0.0)
        directories.append(run_dir)
    return directories


# --------------------------------------------------------------------------
# The statistics
# --------------------------------------------------------------------------


def test_median_is_the_median_of_the_aligned_paths() -> None:
    paths = _paths(5)

    band = summarise_path_band(paths)

    assert band is not None
    assert band.seed_count == 5
    expected = np.median(np.vstack([path.to_numpy() for path in paths]), axis=0)
    assert band.median == pytest.approx(expected)


def test_the_band_is_a_range_below_ten_seeds_and_percentiles_from_ten() -> None:
    few = summarise_path_band(_paths(MINIMUM_SEEDS_FOR_PERCENTILES - 1))
    many = summarise_path_band(_paths(MINIMUM_SEEDS_FOR_PERCENTILES))

    assert few is not None and many is not None
    assert few.band_kind == "range"
    matrix = np.vstack([path.to_numpy() for path in _paths(MINIMUM_SEEDS_FOR_PERCENTILES - 1)])
    assert few.lower == pytest.approx(matrix.min(axis=0))
    assert few.upper == pytest.approx(matrix.max(axis=0))
    assert many.band_kind == "percentile"
    full = np.vstack([path.to_numpy() for path in _paths(MINIMUM_SEEDS_FOR_PERCENTILES)])
    assert many.lower == pytest.approx(np.quantile(full, 0.10, axis=0))
    assert many.upper == pytest.approx(np.quantile(full, 0.90, axis=0))
    assert np.all(many.lower <= many.median) and np.all(many.median <= many.upper)


def test_paths_are_cut_to_the_steps_every_seed_has() -> None:
    long_path = pd.Series(np.arange(10.0), index=np.arange(1, 11, dtype=float))
    short_path = pd.Series(np.arange(6.0), index=np.arange(1, 7, dtype=float))

    band = summarise_path_band([long_path, short_path])

    assert band is not None
    assert band.step.tolist() == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert all(len(member) == 6 for member in band.members)


def test_each_members_path_is_returned_with_the_band() -> None:
    paths = _paths(3)

    band = summarise_path_band(paths)

    assert band is not None
    assert len(band.members) == 3
    assert band.members[1] == pytest.approx(paths[1].to_numpy())


def test_no_usable_path_gives_no_band() -> None:
    assert summarise_path_band([]) is None
    assert summarise_path_band([pd.Series(dtype=float)]) is None


def test_indexed_price_starts_at_100_and_mispricing_vanishes_at_the_fundamental() -> None:
    frame = pd.DataFrame(
        {"price": [50.0, 55.0, 60.0], "fundamental": [50.0, 55.0, 120.0]},
        index=[1.0, 2.0, 3.0],
    )

    measures = build_path_measures(frame)

    assert measures["indexed_price"].tolist() == pytest.approx([100.0, 110.0, 120.0])
    assert measures["log_mispricing"].iloc[0] == 0.0
    assert measures["log_mispricing"].iloc[2] == pytest.approx(np.log(0.5))


def test_a_run_without_a_fundamental_still_has_an_indexed_price() -> None:
    frame = pd.DataFrame({"price": [10.0, 11.0], "fundamental": [np.nan, np.nan]}, index=[1.0, 2.0])

    measures = build_path_measures(frame)

    assert measures["indexed_price"].tolist() == pytest.approx([100.0, 110.0])
    assert measures["log_mispricing"].isna().all()


def test_a_single_market_run_is_filed_under_the_supplied_name(cohort_dirs: list[Path]) -> None:
    paths = load_run_price_paths(
        cohort_dirs[0], phase="simulation", price_column="market_price", single_asset_name="market"
    )

    assert list(paths) == ["market"]
    assert list(paths["market"].columns) == ["price", "fundamental"]
    assert len(paths["market"]) == 180


def test_a_multi_asset_run_contributes_each_market_under_its_own_name(tmp_path: Path) -> None:
    run_dir = tmp_path / RUN_IDS[0][0]
    write_synthetic_run(run_dir, RUN_IDS[0][0], 11, 0.0)
    write_synthetic_asset_timeseries(run_dir, ["alpha", "beta"])

    paths = load_run_price_paths(
        run_dir, phase="simulation", price_column="market_price", single_asset_name="market"
    )

    assert list(paths) == ["alpha", "beta"]


# --------------------------------------------------------------------------
# The cohort payload
# --------------------------------------------------------------------------


def test_cohort_payload_carries_a_band_per_condition_asset_and_measure(
    cohort_dirs: list[Path],
) -> None:
    paths = build_cohort_view(cohort_dirs)["paths"]

    assert paths["available"] is True
    assert {measure["key"] for measure in paths["measures"]} == {"indexed_price", "log_mispricing"}
    assert {(s["condition_id"], s["asset"], s["measure"]) for s in paths["series"]} == {
        ("condition_1", "market", "indexed_price"),
        ("condition_1", "market", "log_mispricing"),
    }
    for entry in paths["series"]:
        assert entry["seed_count"] == 3
        assert entry["band_kind"] == "range"
        assert len(entry["members"]) == 3
        assert len(entry["step"]) == len(entry["median"]) == len(entry["lower"]) == len(entry["upper"])


def test_cohort_median_equals_the_median_of_the_runs_own_paths(cohort_dirs: list[Path]) -> None:
    entry = next(
        s
        for s in build_cohort_view(cohort_dirs)["paths"]["series"]
        if s["measure"] == "indexed_price"
    )

    expected = np.median(
        np.vstack(
            [
                build_path_measures(
                    load_run_price_paths(
                        run_dir,
                        phase="simulation",
                        price_column="market_price",
                        single_asset_name="market",
                    )["market"]
                )["indexed_price"].to_numpy()
                for run_dir in cohort_dirs
            ]
        ),
        axis=0,
    )
    assert entry["median"] == pytest.approx(expected)
    assert entry["lower"][0] == pytest.approx(100.0)
    assert entry["upper"][0] == pytest.approx(100.0)


def test_individual_histories_are_dropped_once_there_are_too_many_to_tell_apart(
    cohort_dirs: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cohort_view, "MAXIMUM_MEMBER_PATHS", 2)

    entry = build_cohort_view(cohort_dirs)["paths"]["series"][0]

    assert entry["seed_count"] == 3
    assert entry["members"] == []


def test_long_paths_are_thinned_for_the_cohort_chart(
    cohort_dirs: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cohort_view, "MAXIMUM_PATH_POINTS", 40)

    entry = build_cohort_view(cohort_dirs)["paths"]["series"][0]

    assert entry["stride"] > 1
    assert len(entry["step"]) <= 40
    assert all(len(member) == len(entry["step"]) for member in entry["members"])


def test_cohort_paths_are_json_serialisable(cohort_dirs: list[Path]) -> None:
    encoded = json.dumps(build_cohort_view(cohort_dirs)["paths"])

    assert "NaN" not in encoded
    assert "Infinity" not in encoded
