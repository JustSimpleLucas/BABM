"""Tests for the calibration explorer: study discovery, score decomposition, payload.

A calibration study's score is one number per trial, and the explorer exists to
take it apart. What is pinned here is therefore the arithmetic a reader would
otherwise have to trust — that the running best is the running minimum, that the
score really is distance plus penalty (and that a study for which it is not is
reported, not mis-drawn) — together with the awkward archives: a study still being
written, one written before score weights were recorded, and one with failed trials.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from abm_analysis.statistics.calibration_study import (
    build_calibration_progress,
    decompose_scores,
    read_calibration_study,
    search_trials,
)
from abm_analysis.web.app import create_app
from abm_analysis.web.calibration_view import build_calibration_view
from abm_analysis.web.catalogue import discover_calibration_studies, resolve_study_path

from abm_test_helpers import write_synthetic_calibration_study, write_synthetic_run


STUDY_NAME = "calibration_20260711000000"


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    """Return a data root holding one study beside the runs the study produced."""

    root = tmp_path / "data"
    study = root / "calibration" / STUDY_NAME
    write_synthetic_calibration_study(study)
    # Runs inside a study belong to the study; they must not make it look like
    # several, nor be mistaken for studies themselves.
    run_id = "20260427143012_1_1_0_1_20_30_5_2_180_66"
    (study / "simulation_runs").mkdir()
    write_synthetic_run(study / "simulation_runs" / run_id, run_id, 66, 0.0)
    return root


@pytest.fixture()
def study_dir(data_root: Path) -> Path:
    return data_root / "calibration" / STUDY_NAME


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


def test_discovery_finds_the_study_and_does_not_descend_into_it(data_root: Path) -> None:
    assert [path.name for path in discover_calibration_studies(data_root)] == [STUDY_NAME]


def test_discovery_of_a_missing_root_is_empty(tmp_path: Path) -> None:
    assert discover_calibration_studies(tmp_path / "absent") == []


def test_study_handles_are_confined_to_the_data_root(data_root: Path) -> None:
    resolved = resolve_study_path(f"calibration/{STUDY_NAME}", data_root)

    assert resolved.name == STUDY_NAME
    with pytest.raises(ValueError):
        resolve_study_path("../..", data_root)
    with pytest.raises(ValueError):
        resolve_study_path("calibration", data_root)


# --------------------------------------------------------------------------
# The statistics
# --------------------------------------------------------------------------


def test_the_running_best_is_the_running_minimum_of_the_search_scores(study_dir: Path) -> None:
    search = search_trials(read_calibration_study(study_dir))

    progress = build_calibration_progress(search)

    assert progress["best_so_far"].tolist() == pytest.approx(
        np.minimum.accumulate(search["score"].to_numpy())
    )
    assert progress["best_so_far"].is_monotonic_decreasing


def test_the_score_is_exactly_distance_plus_penalty_and_levels_count_failed_facts(
    study_dir: Path,
) -> None:
    study = read_calibration_study(study_dir)
    search = search_trials(study)

    decomposition = decompose_scores(search, study.score_weights)

    assert decomposition.identity_holds is True
    assert decomposition.penalty_per_fact == pytest.approx(0.75)
    expected = (search["component_stylised_penalty"] / 0.75).round().astype(int).value_counts()
    levels = decomposition.penalty_levels.set_index("failed_facts")["trials"]
    assert levels.to_dict() == expected.to_dict()


def test_unequal_penalty_weights_leave_the_failed_fact_count_unrecoverable(
    study_dir: Path,
) -> None:
    study = read_calibration_study(study_dir)
    uneven = {**study.score_weights, "fat_tail_penalty": 2.0}

    decomposition = decompose_scores(search_trials(study), uneven)

    assert decomposition.penalty_per_fact is None
    assert decomposition.penalty_levels["failed_facts"].isna().all()


def test_failed_trials_are_left_out_of_the_search(tmp_path: Path) -> None:
    study_dir = tmp_path / STUDY_NAME
    write_synthetic_calibration_study(study_dir, failed_trials=4)

    study = read_calibration_study(study_dir)

    assert len(search_trials(study)) == 26
    assert search_trials(study)["score"].max() < 1.0e6


# --------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------


def test_payload_reports_the_search_the_candidates_and_the_selected_one(study_dir: Path) -> None:
    view = build_calibration_view(study_dir, f"calibration/{STUDY_NAME}")

    assert view["progress"]["available"] is True
    assert len(view["progress"]["trial"]) == len(view["progress"]["best_so_far"]) == 30
    assert view["candidates"]["available"] is True
    assert len(view["candidates"]["rows"]) == 3
    assert sum(row["selected"] for row in view["candidates"]["rows"]) == 1
    assert view["parameters"]["selected_trial"] in view["parameters"]["candidate_trials"]
    assert len(view["parameters"]["series"]) == 3
    assert {entry["trial_number"] for entry in view["validation"]["candidates"]} == set(
        view["parameters"]["candidate_trials"]
    )
    for entry in view["validation"]["candidates"]:
        assert len(entry["score"]) == 5


def test_payload_parameter_series_are_aligned_with_the_scores(study_dir: Path) -> None:
    view = build_calibration_view(study_dir, "x")

    for entry in view["parameters"]["series"]:
        assert len(entry["value"]) == len(entry["score"]) == len(entry["trial"]) == 30
    labels = {entry["label"] for entry in view["parameters"]["series"]}
    assert "Loss aversion" in labels, "the control_ prefix is noise in a heading"


def test_payload_decomposition_matches_the_statistics_module(study_dir: Path) -> None:
    study = read_calibration_study(study_dir)
    expected = decompose_scores(search_trials(study), study.score_weights)

    decomposition = build_calibration_view(study_dir, "x")["decomposition"]

    assert decomposition["available"] is True
    assert decomposition["market_distance"] == pytest.approx(expected.market_distance.tolist())
    assert decomposition["stylised_penalty"] == pytest.approx(expected.stylised_penalty.tolist())
    assert decomposition["minimum_penalty"] == pytest.approx(0.75)


def test_a_study_with_no_zero_penalty_trial_says_so(study_dir: Path) -> None:
    notes = build_calibration_view(study_dir, "x")["notes"]

    assert any("No search trial reproduced all three stylised facts" in note for note in notes)


def test_a_study_whose_score_is_not_distance_plus_penalty_is_flagged_not_drawn(
    study_dir: Path,
) -> None:
    path = study_dir / "calibration_trials.csv"
    frame = pd.read_csv(path)
    frame.loc[frame["phase"] == "search", "score"] += 0.1
    frame.to_csv(path, index=False)

    view = build_calibration_view(study_dir, "x")

    assert view["decomposition"]["available"] is False
    assert view["decomposition"]["identity_holds"] is False
    assert any("not market distance plus stylised-fact penalty" in note for note in view["notes"])
    # The running best does not depend on the decomposition and must still draw.
    assert view["progress"]["available"] is True


def test_a_study_without_recorded_weights_falls_back_and_says_so(tmp_path: Path) -> None:
    study_dir = tmp_path / STUDY_NAME
    write_synthetic_calibration_study(study_dir, record_weights=False)

    view = build_calibration_view(study_dir, "x")

    assert view["decomposition"]["weights_recorded"] is False
    assert view["decomposition"]["penalty_per_fact"] == pytest.approx(0.75)
    assert {"label": "Score weights", "value": "library defaults assumed"} in view["chips"]
    assert any("did not record its score weights" in note for note in view["notes"])


def test_a_study_still_being_written_opens_with_what_it_has(tmp_path: Path) -> None:
    study_dir = tmp_path / STUDY_NAME
    study_dir.mkdir()
    (study_dir / "calibration_trials.csv").write_text(
        "trial_number,phase,seed,status,score,component_market_distance,"
        "component_stylised_penalty,param_control_loss_aversion\n",
        encoding="utf-8",
    )

    view = build_calibration_view(study_dir, "x")

    assert view["progress"]["available"] is False
    assert view["candidates"]["available"] is False
    assert view["validation"]["available"] is False
    assert view["name"] == STUDY_NAME


def test_failed_trials_are_reported_in_the_payload(tmp_path: Path) -> None:
    study_dir = tmp_path / STUDY_NAME
    write_synthetic_calibration_study(study_dir, failed_trials=4)

    view = build_calibration_view(study_dir, "x")

    tiles = {tile["label"]: tile["value"] for tile in view["metrics"]}
    assert tiles["Failed trials"] == 4
    assert tiles["Search trials"] == 26
    assert any("4 search trial(s) failed" in note for note in view["notes"])


def test_the_payload_is_json_serialisable(study_dir: Path) -> None:
    encoded = json.dumps(build_calibration_view(study_dir, "x"))

    assert "NaN" not in encoded
    assert "Infinity" not in encoded


# --------------------------------------------------------------------------
# The endpoints
# --------------------------------------------------------------------------


def test_catalogue_endpoint_lists_studies_and_survives_an_unreadable_one(data_root: Path) -> None:
    broken = data_root / "calibration" / "calibration_broken"
    broken.mkdir()
    (broken / "calibration_trials.csv").write_bytes(b"")
    client = TestClient(create_app(data_root))

    response = client.get("/api/calibration")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["studies"][0]["path"] == f"calibration/{STUDY_NAME}"
    assert body["studies"][0]["trial_count"] == 30


def test_study_endpoint_serves_the_payload_and_rejects_bad_handles(data_root: Path) -> None:
    client = TestClient(create_app(data_root))

    ok = client.get("/api/calibration/study", params={"path": f"calibration/{STUDY_NAME}"})
    escaped = client.get("/api/calibration/study", params={"path": "../.."})
    not_a_study = client.get("/api/calibration/study", params={"path": "calibration"})

    assert ok.status_code == 200
    assert ok.json()["name"] == STUDY_NAME
    assert escaped.status_code == 404
    assert not_a_study.status_code == 404
