"""Tests for the crisis lens: stress windows, the rows beneath the price chart.

The lens exists to show *when* a simulated market was in trouble, so what is
pinned here is the part that could silently mislead: that the shaded windows are
the statistics module's own flags (not a second rule), that a short stress window
survives the thinning a long series is put through, that the extra rows stay
aligned with the price chart, and that the warm-up the reader asks to see is
actually on the axis.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from abm_analysis.archive.timeseries import load_step_timeseries, step_axis_column
from abm_analysis.statistics.stress import (
    DEFAULT_STRESS_DRAWDOWN_THRESHOLD,
    annotate_stress_regimes,
    build_asset_stress_frames,
    compute_log_mispricing,
    find_stress_intervals,
)
from abm_analysis.web.crisis_view import REGIMES, STRESS_DEFINITIONS
from abm_analysis.web.metrics import MAXIMUM_SERIES_POINTS, stride_for
from abm_analysis.web.run_view import build_run_view

from abm_test_helpers import write_synthetic_asset_timeseries, write_synthetic_run


RUN_ID = "20260427143012_1_1_0_1_20_30_5_2_180_66"


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


# --------------------------------------------------------------------------
# The statistics helpers
# --------------------------------------------------------------------------


def test_stress_intervals_cover_edges_and_single_rows() -> None:
    flags = np.array([1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 1], dtype=bool)

    assert find_stress_intervals(flags, np.arange(100, 111)) == [
        (100.0, 101.0),
        (104.0, 104.0),
        (108.0, 110.0),
    ]
    assert find_stress_intervals(np.zeros(4, dtype=bool), np.arange(4)) == []
    assert find_stress_intervals(np.ones(4, dtype=bool), np.arange(4)) == [(0.0, 3.0)]


def test_a_one_step_stress_window_survives_thinning() -> None:
    """Thinning the flag would drop exactly the brief episodes a crisis lens is for."""

    observations = 20_000
    position = 12_346
    flags = np.zeros(observations, dtype=bool)
    flags[position] = True
    stride = stride_for(observations)

    assert stride > 1
    assert position % stride != 0
    assert not flags[::stride].any(), "the fixture must be one a naive thinning would lose"
    assert find_stress_intervals(flags, np.arange(observations)) == [
        (float(position), float(position))
    ]


def test_stress_intervals_reject_misaligned_inputs() -> None:
    with pytest.raises(ValueError):
        find_stress_intervals(np.array([True, False]), np.arange(3))


def test_log_mispricing_is_symmetric_and_tolerates_a_crashed_price() -> None:
    mispricing = compute_log_mispricing(
        pd.Series([50.0, 200.0, 0.0, 100.0]),
        pd.Series([100.0, 100.0, 10.0, 100.0]),
    )

    assert mispricing.iloc[0] == pytest.approx(-mispricing.iloc[1])
    assert np.isnan(mispricing.iloc[2])
    assert mispricing.iloc[3] == 0.0


def test_step_axis_falls_back_to_row_index_when_steps_have_gaps() -> None:
    complete = pd.DataFrame({"row_index": [0, 1, 2], "simulation_step": [1.0, 2.0, 3.0]})
    gapped = pd.DataFrame({"row_index": [0, 1, 2], "simulation_step": [np.nan, np.nan, 1.0]})

    assert step_axis_column(complete) == "simulation_step"
    assert step_axis_column(gapped) == "row_index"


def test_asset_stress_frames_are_empty_without_a_per_asset_artefact(
    single_asset_run: Path,
) -> None:
    assert build_asset_stress_frames(single_asset_run) == {}


# --------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------


def test_stress_windows_are_the_statistics_modules_own_flags(single_asset_run: Path) -> None:
    """The page must not become a second implementation of the stress rule."""

    view = build_run_view(single_asset_run)
    crisis = view["crisis"]
    market = crisis["assets"]["market"]["definitions"]

    series = load_step_timeseries(single_asset_run)
    series = series[series["phase"] == "simulation"]
    annotated = annotate_stress_regimes(series, price_column="market_price")
    expected_either = find_stress_intervals(
        annotated["stress_regime"], annotated["simulation_step"]
    )
    volatility_flags = (
        annotated["rolling_volatility"] >= annotated["stress_volatility_threshold"].iloc[0]
    ).fillna(False)
    drawdown_flags = (annotated["drawdown"] >= DEFAULT_STRESS_DRAWDOWN_THRESHOLD).fillna(False)

    assert crisis["available"] is True
    assert market["either"]["intervals"] == [list(pair) for pair in expected_either]
    assert market["volatility"]["intervals"] == [
        list(pair) for pair in find_stress_intervals(volatility_flags, annotated["simulation_step"])
    ]
    assert market["drawdown"]["intervals"] == [
        list(pair) for pair in find_stress_intervals(drawdown_flags, annotated["simulation_step"])
    ]


def test_the_combined_definition_is_the_union_of_the_two_triggers(
    single_asset_run: Path,
) -> None:
    definitions = build_run_view(single_asset_run)["crisis"]["assets"]["market"]["definitions"]

    assert definitions["either"]["share"] >= max(
        definitions["volatility"]["share"], definitions["drawdown"]["share"]
    )
    either = [tuple(pair) for pair in definitions["either"]["intervals"]]
    for trigger in ("volatility", "drawdown"):
        for first, last in definitions[trigger]["intervals"]:
            assert any(low <= first and last <= high for low, high in either), trigger


def test_volatility_stress_is_a_minority_of_rows_by_construction(
    single_asset_run: Path,
) -> None:
    """The top-quintile rule flags about a fifth of any series, however calm."""

    share = build_run_view(single_asset_run)["crisis"]["assets"]["market"]["definitions"][
        "volatility"
    ]["share"]

    assert 0.0 < share <= 0.25


def test_normal_and_stress_rows_partition_the_observations(two_asset_run: Path) -> None:
    crisis = build_run_view(two_asset_run)["crisis"]

    for asset in crisis["assets"].values():
        for definition in STRESS_DEFINITIONS:
            regimes = asset["definitions"][definition]["regimes"]
            assert set(regimes) == set(REGIMES)
            assert (
                regimes["normal"]["observation_count"] + regimes["stress"]["observation_count"]
                == regimes["all"]["observation_count"]
            )


def test_crisis_tracks_stay_index_aligned_with_the_price_series(
    single_asset_run: Path,
    two_asset_run: Path,
) -> None:
    for run_dir in (single_asset_run, two_asset_run):
        view = build_run_view(run_dir)
        point_count = view["series"]["point_count"]

        assert view["crisis"]["tracks"], run_dir
        for name, track in view["crisis"]["tracks"].items():
            assert set(track) == {"log_mispricing", "rolling_volatility", "drawdown"}
            for key, values in track.items():
                assert len(values) == point_count, (name, key)


def test_a_two_asset_run_reports_each_market_with_its_own_threshold(
    two_asset_run: Path,
) -> None:
    crisis = build_run_view(two_asset_run)["crisis"]

    assert list(crisis["assets"]) == ["alpha", "beta"]
    assert set(crisis["rule"]["volatility_threshold"]) == {"alpha", "beta"}
    assert crisis["rule"]["rolling_window"] == 30
    assert crisis["default_definition"] == "volatility"


def test_all_phase_keeps_the_warmup_rows_on_a_single_asset_axis(
    single_asset_run: Path,
) -> None:
    """Regression: warm-up rows have no ``simulation_step`` and were silently dropped."""

    simulation = build_run_view(single_asset_run, phase="simulation")
    everything = build_run_view(single_asset_run, phase="all")

    assert simulation["series"]["step_axis"] == "simulation_step"
    assert simulation["crisis"]["warmup_end"] is None

    series = everything["series"]
    assert series["step_axis"] == "row_index"
    assert None not in series["step"]
    assert series["point_count"] == 190
    assert series["step"][0] == 0.0
    # Rows 0-9 are the initial row and nine warm-up rows; the simulation starts at 10.
    assert everything["crisis"]["warmup_end"] == pytest.approx(9.5)
    assert len(everything["crisis"]["tracks"]["market"]["drawdown"]) == 190


def test_missing_liquidity_columns_leave_regime_cells_unavailable(
    single_asset_run: Path,
) -> None:
    path = single_asset_run / "step_timeseries.csv"
    frame = pd.read_csv(path).drop(columns=["bid_depth", "ask_depth", "bid_ask_spread"])
    frame.to_csv(path, index=False)

    crisis = build_run_view(single_asset_run)["crisis"]
    regimes = crisis["assets"]["market"]["definitions"]["volatility"]["regimes"]

    assert crisis["available"] is True
    assert regimes["all"]["mean_total_depth"] is None
    assert regimes["all"]["mean_bid_ask_spread"] is None
    assert regimes["all"]["log_return_std_dev"] is not None


def test_a_run_with_no_observations_reports_the_lens_unavailable(
    single_asset_run: Path,
) -> None:
    crisis = build_run_view(single_asset_run, phase="no_such_phase")["crisis"]

    assert crisis["available"] is False
    assert crisis["message"]


@pytest.mark.parametrize("phase", ["simulation", "all", "warmup"])
def test_crisis_payload_is_json_serialisable(
    two_asset_run: Path, single_asset_run: Path, phase: str
) -> None:
    for run_dir in (single_asset_run, two_asset_run):
        encoded = json.dumps(build_run_view(run_dir, phase=phase)["crisis"])

        assert "NaN" not in encoded
        assert "Infinity" not in encoded


def test_series_cap_is_unchanged_by_the_crisis_rows() -> None:
    """The crisis tracks are thinned with the price series' own stride."""

    assert MAXIMUM_SERIES_POINTS == 8000
