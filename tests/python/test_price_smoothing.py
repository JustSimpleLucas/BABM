"""Tests for price smoothing: the moving averages drawn over the price line.

The averages are display aids, so what is pinned here is what could silently
mislead a reader of the chart: that the simple average is the engine's own
definition (the mean of the last ``h`` prices, the current one included), that
nothing is drawn before a full window exists, that the lag the page tells the
reader about is the lag the averages really have, that only the centred average
looks ahead, that a window is measured in steps even when the chart is thinned,
and that a window is offered only when the run is long enough to hold it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from abm_analysis.archive.timeseries import load_step_timeseries
from abm_analysis.statistics.multi_asset import load_asset_panel
from abm_analysis.statistics.smoothing import (
    DEFAULT_SMOOTHING_METHOD,
    PRICE_SMOOTHING_WINDOWS,
    SMOOTHING_ALIGNMENTS,
    SMOOTHING_METHODS,
    compute_centred_moving_average,
    compute_exponential_moving_average,
    compute_price_average,
    compute_simple_moving_average,
    usable_smoothing_windows,
)
from abm_analysis.web.asset_view import STEP_TIMESERIES_SOURCE, AssetContext, build_series
from abm_analysis.web.run_view import build_run_view

from abm_test_helpers import write_synthetic_asset_timeseries, write_synthetic_run


RUN_ID = "20260427143012_1_1_0_1_20_30_5_2_180_66"

ALL_AVERAGES: tuple[Callable[[pd.Series, int], pd.Series], ...] = (
    compute_simple_moving_average,
    compute_exponential_moving_average,
    compute_centred_moving_average,
)


@pytest.fixture()
def single_asset_run(tmp_path: Path) -> Path:
    """Return a synthetic run read through its primary-asset step series."""

    run_dir = tmp_path / RUN_ID
    write_synthetic_run(run_dir, RUN_ID, 66, 0.0)
    return run_dir


@pytest.fixture()
def two_asset_run(tmp_path: Path) -> Path:
    """Return a synthetic run with a per-asset artefact for two markets.

    Held in its own directory so a test may ask for both fixtures at once.
    """

    parent = tmp_path / "two_asset"
    parent.mkdir()
    run_dir = parent / RUN_ID
    write_synthetic_run(run_dir, RUN_ID, 66, 0.0)
    write_synthetic_asset_timeseries(run_dir, ["alpha", "beta"])
    return run_dir


def _as_array(values: list[float | None]) -> np.ndarray:
    """Return a payload list as floats, with its ``None`` gaps as ``NaN``."""

    return np.array([np.nan if value is None else value for value in values], dtype=float)


def _simulation_prices(run_dir: Path) -> pd.Series:
    """Return the single-asset run's price at every simulation step."""

    frame = load_step_timeseries(run_dir, price_column="market_price")
    simulation = frame[frame["phase"] == "simulation"].reset_index(drop=True)
    return pd.to_numeric(simulation["market_price"], errors="coerce")


def _blank_ends(values: pd.Series) -> tuple[int, int]:
    """Return how many positions at the start and at the end of a series are ``NaN``."""

    missing = values.isna().to_numpy()
    return int(missing.argmin()), int(missing[::-1].argmin())


# --------------------------------------------------------------------------
# The simple average: the engine's own definition
# --------------------------------------------------------------------------


def test_a_worked_example_matches_the_engines_formula() -> None:
    """``MA_t(h)`` is the mean of ``P_t, P_{t-1}, ..., P_{t-h+1}``."""

    averaged = compute_simple_moving_average(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 3)

    assert averaged.isna().tolist() == [True, True, False, False, False]
    assert averaged.dropna().tolist() == [2.0, 3.0, 4.0]


def test_the_average_is_the_mean_of_the_last_h_prices_including_the_current_one() -> None:
    prices = pd.Series(np.random.default_rng(3).normal(100.0, 5.0, size=60))
    window = 7

    averaged = compute_simple_moving_average(prices, window)

    for position in range(window - 1, len(prices)):
        expected = prices.iloc[position - window + 1 : position + 1].mean()
        assert averaged.iloc[position] == pytest.approx(expected)


def test_nothing_is_reported_before_a_full_window_exists() -> None:
    """Averaging the few prices available at the start would look smoother than the data."""

    prices = pd.Series(np.arange(1.0, 31.0))

    averaged = compute_simple_moving_average(prices, 10)

    assert averaged.iloc[:9].isna().all()
    assert averaged.iloc[9] == pytest.approx(prices.iloc[:10].mean())


def test_a_missing_price_leaves_a_gap_until_it_leaves_the_window() -> None:
    prices = pd.Series(np.arange(1.0, 21.0))
    prices.iloc[10] = np.nan

    averaged = compute_simple_moving_average(prices, 5)

    # The windows ending at positions 10 to 14 are the ones that contain the gap.
    assert averaged.iloc[10:15].isna().all()
    assert averaged.iloc[9] == pytest.approx(prices.iloc[5:10].mean())
    assert averaged.iloc[15] == pytest.approx(prices.iloc[11:16].mean())


def test_non_finite_prices_are_treated_as_missing() -> None:
    prices = pd.Series([1.0, 2.0, np.inf, 4.0, 5.0, 6.0])

    averaged = compute_simple_moving_average(prices, 2)

    assert averaged.isna().tolist() == [True, False, True, True, False, False]


def test_a_numpy_integer_window_is_accepted() -> None:
    prices = pd.Series([1.0, 2.0, 3.0, 4.0])

    averaged = compute_simple_moving_average(prices, np.int64(2))

    assert averaged.dropna().tolist() == [1.5, 2.5, 3.5]


# --------------------------------------------------------------------------
# The exponential average
# --------------------------------------------------------------------------


@pytest.mark.parametrize("position", [19, 20, 45, 119])
def test_the_exponential_average_is_the_normalised_geometric_weighting(position: int) -> None:
    """Weights ``(1 - alpha)^k`` on the price ``k`` steps back, ``alpha = 2 / (h + 1)``."""

    prices = pd.Series(np.random.default_rng(1).normal(100.0, 5.0, size=120))
    window = 20
    decay = 1.0 - 2.0 / (window + 1)
    weights = decay ** np.arange(position + 1)
    newest_first = prices.iloc[: position + 1].to_numpy()[::-1]

    averaged = compute_exponential_moving_average(prices, window)

    assert averaged.iloc[position] == pytest.approx((weights * newest_first).sum() / weights.sum())


def test_the_exponential_average_reports_nothing_before_a_full_span() -> None:
    prices = pd.Series(np.arange(1.0, 41.0))

    averaged = compute_exponential_moving_average(prices, 8)

    assert averaged.iloc[:7].isna().all()
    assert averaged.iloc[7:].notna().all()


def test_a_step_with_no_price_has_no_exponential_average_and_the_next_one_resumes() -> None:
    """The average is not carried forward over a step with nothing to compare it to."""

    prices = pd.Series(np.arange(1.0, 41.0))
    prices.iloc[30] = np.nan

    averaged = compute_exponential_moving_average(prices, 5)

    assert np.flatnonzero(averaged.isna().to_numpy()).tolist() == [0, 1, 2, 3, 30]


def test_the_exponential_average_does_not_jump_when_a_large_move_leaves_the_window() -> None:
    """The reason to offer it: a spike lifts the simple average, then drops it all at once."""

    prices = pd.Series(np.full(100, 100.0))
    prices.iloc[40] = 200.0
    window = 10

    simple = compute_simple_moving_average(prices, window)
    exponential = compute_exponential_moving_average(prices, window)

    biggest_simple_drop = (-simple.diff()).max()
    biggest_exponential_drop = (-exponential.diff()).max()
    assert biggest_simple_drop == pytest.approx(10.0)  # 100 / window, in one step
    assert biggest_exponential_drop < 0.5 * biggest_simple_drop


# --------------------------------------------------------------------------
# The centred average
# --------------------------------------------------------------------------


def test_an_odd_centred_window_is_the_mean_of_the_prices_on_both_sides() -> None:
    prices = pd.Series(np.random.default_rng(5).normal(100.0, 5.0, size=40))
    half = 3

    averaged = compute_centred_moving_average(prices, 2 * half + 1)

    for position in range(half, len(prices) - half):
        expected = prices.iloc[position - half : position + half + 1].mean()
        assert averaged.iloc[position] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("window", "expected_blank_ends"), [(5, (2, 2)), (20, (10, 9)), (50, (25, 24))]
)
def test_the_centred_average_is_blank_at_both_ends(
    window: int, expected_blank_ends: tuple[int, int]
) -> None:
    """Without a full window on both sides the average would be of different prices."""

    averaged = compute_centred_moving_average(pd.Series(np.arange(100.0)), window)

    assert _blank_ends(averaged) == expected_blank_ends


# --------------------------------------------------------------------------
# What the page tells the reader about lag and look-ahead
# --------------------------------------------------------------------------


@pytest.mark.parametrize("window", [5, 20, 50])
def test_trailing_averages_trail_a_steady_trend_by_half_a_window_less_one(window: int) -> None:
    """The note says "about (h - 1) / 2 steps"; this is that sentence, measured."""

    trend = pd.Series(np.arange(1000.0))
    position = 900

    for average in (compute_simple_moving_average, compute_exponential_moving_average):
        lag = trend.iloc[position] - average(trend, window).iloc[position]
        assert lag == pytest.approx((window - 1) / 2, abs=1e-6), average.__name__


@pytest.mark.parametrize(("window", "expected_lag"), [(5, 0.0), (7, 0.0), (20, 0.5), (50, 0.5)])
def test_the_centred_average_does_not_trail_a_steady_trend(
    window: int, expected_lag: float
) -> None:
    """Exactly none for an odd window, half a step for an even one."""

    trend = pd.Series(np.arange(1000.0))

    lag = trend.iloc[500] - compute_centred_moving_average(trend, window).iloc[500]

    assert lag == pytest.approx(expected_lag)


@pytest.mark.parametrize("method", SMOOTHING_METHODS)
def test_only_the_centred_average_looks_ahead(method: str) -> None:
    """The ``alignment`` the payload reports must be what the average actually does."""

    base = pd.Series(np.random.default_rng(9).normal(100.0, 5.0, size=80))
    later_price_changed = base.copy()
    later_price_changed.iloc[41] += 50.0

    before = compute_price_average(method, base, 10).iloc[:41]
    after = compute_price_average(method, later_price_changed, 10).iloc[:41]

    uses_only_the_past = np.allclose(before, after, equal_nan=True)
    assert uses_only_the_past == (SMOOTHING_ALIGNMENTS[method] == "trailing")


# --------------------------------------------------------------------------
# Every average
# --------------------------------------------------------------------------


@pytest.mark.parametrize("average", ALL_AVERAGES)
def test_an_average_keeps_the_index_of_the_series_it_smooths(
    average: Callable[[pd.Series, int], pd.Series],
) -> None:
    """The chart reindexes the average onto its own steps, so the index must survive."""

    prices = pd.Series(
        np.arange(10.0, 30.0), index=pd.Index(np.arange(1, 21), name="simulation_step")
    )

    averaged = average(prices, 3)

    assert averaged.index.equals(prices.index)
    assert averaged.index.name == "simulation_step"


@pytest.mark.parametrize("average", ALL_AVERAGES)
def test_a_one_observation_window_is_the_series_itself(
    average: Callable[[pd.Series, int], pd.Series],
) -> None:
    prices = pd.Series([3.0, 1.0, 4.0, 1.0, 5.0])

    np.testing.assert_allclose(average(prices, 1).to_numpy(), prices.to_numpy())


@pytest.mark.parametrize("average", ALL_AVERAGES)
def test_a_constant_price_is_its_own_average(
    average: Callable[[pd.Series, int], pd.Series],
) -> None:
    averaged = average(pd.Series(np.full(60, 42.0)), 10).dropna()

    assert len(averaged) > 0
    np.testing.assert_allclose(averaged.to_numpy(), 42.0)


@pytest.mark.parametrize("average", ALL_AVERAGES)
@pytest.mark.parametrize("window", [0, -3, 2.5, "5", None])
def test_a_window_must_be_a_positive_integer(
    average: Callable[[pd.Series, int], pd.Series], window: object
) -> None:
    with pytest.raises(ValueError):
        average(pd.Series([1.0, 2.0, 3.0]), window)  # type: ignore[arg-type]


@pytest.mark.parametrize("method", SMOOTHING_METHODS)
def test_an_average_can_be_chosen_by_name(method: str) -> None:
    prices = pd.Series(np.random.default_rng(2).normal(100.0, 5.0, size=50))
    direct = {
        "simple": compute_simple_moving_average,
        "exponential": compute_exponential_moving_average,
        "centred": compute_centred_moving_average,
    }[method]

    pd.testing.assert_series_equal(
        compute_price_average(method, prices, 10), direct(prices, 10)
    )


def test_an_unknown_average_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown smoothing method"):
        compute_price_average("median", pd.Series([1.0, 2.0, 3.0]), 2)


@pytest.mark.parametrize(
    ("observations", "expected"),
    [
        (0, ()),
        (9, ()),
        (10, (5,)),
        (39, (5,)),
        (40, (5, 20)),
        (99, (5, 20)),
        (100, (5, 20, 50)),
        (5000, (5, 20, 50)),
    ],
)
def test_a_window_is_offered_only_when_the_series_is_two_windows_long(
    observations: int, expected: tuple[int, ...]
) -> None:
    """A window that fills most of the series leaves a line blank for most of the chart."""

    assert PRICE_SMOOTHING_WINDOWS == (5, 20, 50)
    assert usable_smoothing_windows(observations) == expected


def test_windows_may_be_supplied_and_keep_their_order() -> None:
    assert usable_smoothing_windows(60, windows=(30, 10, 40)) == (30, 10)


# --------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------


def test_the_payload_describes_the_smoothing_on_offer(
    single_asset_run: Path, two_asset_run: Path
) -> None:
    """The interface builds its controls from this, so it never holds a list of its own."""

    assert DEFAULT_SMOOTHING_METHOD == "simple"
    for run_dir in (single_asset_run, two_asset_run):
        smoothing = build_run_view(run_dir)["series"]["smoothing"]

        assert smoothing == {
            "default_method": "simple",
            "methods": [
                {"key": "simple", "alignment": "trailing"},
                {"key": "exponential", "alignment": "trailing"},
                {"key": "centred", "alignment": "centred"},
            ],
            "windows": [5, 20, 50],
        }, run_dir


def test_every_market_carries_every_average_for_every_window_on_the_chart_axis(
    single_asset_run: Path, two_asset_run: Path
) -> None:
    for run_dir in (single_asset_run, two_asset_run):
        series = build_run_view(run_dir)["series"]

        assert series["assets"], run_dir
        for name, track in series["assets"].items():
            assert set(track["price_moving_average"]) == set(SMOOTHING_METHODS), name
            for method, by_window in track["price_moving_average"].items():
                assert set(by_window) == {"5", "20", "50"}, (name, method)
                for window, values in by_window.items():
                    assert len(values) == series["point_count"], (name, method, window)


@pytest.mark.parametrize("method", SMOOTHING_METHODS)
def test_a_single_market_average_is_the_statistics_modules_own(
    single_asset_run: Path, method: str
) -> None:
    view = build_run_view(single_asset_run)
    prices = _simulation_prices(single_asset_run)
    track = view["series"]["assets"][view["assets"]["names"][0]]

    for window in PRICE_SMOOTHING_WINDOWS:
        np.testing.assert_allclose(
            _as_array(track["price_moving_average"][method][str(window)]),
            compute_price_average(method, prices, window).to_numpy(),
            equal_nan=True,
            err_msg=f"{method} window {window}",
        )


@pytest.mark.parametrize("method", SMOOTHING_METHODS)
def test_each_market_of_a_two_asset_run_is_averaged_on_its_own_prices(
    two_asset_run: Path, method: str
) -> None:
    view = build_run_view(two_asset_run)
    panel = load_asset_panel(two_asset_run, "market_price", phase="simulation")

    for name in view["assets"]["names"]:
        track = view["series"]["assets"][name]
        for window in PRICE_SMOOTHING_WINDOWS:
            np.testing.assert_allclose(
                _as_array(track["price_moving_average"][method][str(window)]),
                compute_price_average(method, panel[name], window).to_numpy(),
                equal_nan=True,
                err_msg=f"{name} {method} window {window}",
            )

    alpha = view["series"]["assets"]["alpha"]["price_moving_average"][method]["20"]
    beta = view["series"]["assets"]["beta"]["price_moving_average"][method]["20"]
    assert alpha != beta


def test_the_centred_average_ends_before_the_chart_does_and_the_trailing_ones_do_not(
    single_asset_run: Path,
) -> None:
    """The page says the centred line is blank at the end; the payload must agree."""

    by_window = build_run_view(single_asset_run)["series"]["assets"]["market"][
        "price_moving_average"
    ]

    assert by_window["simple"]["20"][-1] is not None
    assert by_window["exponential"]["20"][-1] is not None
    assert by_window["centred"]["20"][-9:] == [None] * 9
    assert by_window["centred"]["20"][-10] is not None


def test_the_all_phase_average_runs_through_the_warmup_rows(single_asset_run: Path) -> None:
    """With warm-up shown the axis is the row index and the average spans every row."""

    view = build_run_view(single_asset_run, phase="all")
    series = view["series"]
    values = series["assets"]["market"]["price_moving_average"]["simple"]["5"]
    every_row = pd.to_numeric(
        load_step_timeseries(single_asset_run, price_column="market_price")["market_price"],
        errors="coerce",
    )

    assert series["step_axis"] == "row_index"
    assert series["point_count"] == len(values) == 190
    assert values[:4] == [None] * 4
    assert values[4] == pytest.approx(every_row.iloc[:5].mean())


def test_a_series_too_short_for_any_window_offers_none(single_asset_run: Path) -> None:
    """The warm-up phase is nine rows, which holds no window of the offered set."""

    series = build_run_view(single_asset_run, phase="warmup")["series"]

    assert series["smoothing"]["windows"] == []
    assert series["assets"]["market"]["price_moving_average"] == {}


def test_a_truncated_two_asset_run_drops_the_windows_it_cannot_hold(tmp_path: Path) -> None:
    run_dir = tmp_path / RUN_ID
    write_synthetic_run(run_dir, RUN_ID, 66, 0.0)
    # Sixty rows are ten initial and warm-up rows and fifty simulation steps, which
    # hold the 5 and 20 windows twice over but not the 50.
    write_synthetic_asset_timeseries(run_dir, ["alpha", "beta"], observations=60)

    series = build_run_view(run_dir)["series"]

    assert series["point_count"] == 50
    assert series["smoothing"]["windows"] == [5, 20]
    for track in series["assets"].values():
        for method in SMOOTHING_METHODS:
            assert set(track["price_moving_average"][method]) == {"5", "20"}


def test_a_frame_without_the_price_column_offers_no_average() -> None:
    context = AssetContext(
        names=("market",),
        primary="market",
        source=STEP_TIMESERIES_SOURCE,
        return_source="computed from market_price",
    )
    analysed = pd.DataFrame(
        {
            "row_index": np.arange(100),
            "phase": "simulation",
            "simulation_step": np.arange(1, 101),
        }
    )

    series = build_series(
        Path("unused"), analysed, phase="simulation", price_column="market_price", context=context
    )

    assert series["smoothing"]["windows"] == []
    assert series["assets"]["market"]["price_moving_average"] == {}


# --------------------------------------------------------------------------
# Thinning
# --------------------------------------------------------------------------


@pytest.mark.parametrize("method", SMOOTHING_METHODS)
def test_thinning_samples_the_average_instead_of_averaging_the_thinned_series(
    single_asset_run: Path, two_asset_run: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    """A window is steps. Averaging thinned points would silently make it ``window * stride``."""

    # A cap of 40 points thins the 180 simulation steps to every fifth.
    monkeypatch.setattr("abm_analysis.web.metrics.MAXIMUM_SERIES_POINTS", 40)
    window = 20
    cases = (
        (single_asset_run, "market", _simulation_prices(single_asset_run)),
        (
            two_asset_run,
            "alpha",
            load_asset_panel(two_asset_run, "market_price", phase="simulation")["alpha"],
        ),
    )

    for run_dir, name, prices in cases:
        series = build_run_view(run_dir)["series"]
        stride = series["stride"]
        served = _as_array(series["assets"][name]["price_moving_average"][method][str(window)])
        sampled_from_every_step = compute_price_average(method, prices, window).to_numpy()[::stride]
        averaged_after_thinning = compute_price_average(
            method, prices.iloc[::stride], window
        ).to_numpy()

        assert series["downsampled"] and stride == 5, run_dir
        assert series["smoothing"]["windows"] == [5, 20, 50], "windows follow the run's length"
        np.testing.assert_allclose(served, sampled_from_every_step, equal_nan=True)
        assert not np.allclose(served, averaged_after_thinning, equal_nan=True), run_dir


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("phase", ["simulation", "all", "warmup"])
def test_the_smoothing_payload_is_strict_json(
    single_asset_run: Path, two_asset_run: Path, phase: str
) -> None:
    """Gaps must reach the browser as ``null``; ``NaN`` is not valid JSON."""

    for run_dir in (single_asset_run, two_asset_run):
        series = build_run_view(run_dir, phase=phase)["series"]

        json.dumps(series, allow_nan=False)
