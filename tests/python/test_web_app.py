"""Tests for the read-only market-statistics web application.

The dashboard's research value depends on three guarantees: that it finds every
archived run regardless of where in ``data/`` it sits, that it reports **every**
traded market rather than only the primary asset's projection, and that the
numbers it serves are the statistics modules' numbers rather than a second,
divergent implementation. All three are asserted here, alongside the containment
check that keeps a client-supplied path from reaching outside the archive.

The multi-asset tests use their own fixture rather than joining ``data_root``:
the run counts asserted for the catalogue are load-bearing, and every
single-asset test would otherwise pay for a fixture it does not use.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from abm_analysis.statistics.agents import build_agent_summary_statistics
from abm_analysis.statistics.diagnostics import (
    run_asset_stylised_fact_diagnostics,
    run_stylised_fact_diagnostics,
)
from abm_analysis.web.app import _archive_generation, create_app
from abm_analysis.web.catalogue import build_catalogue, discover_runs, resolve_run_path
from abm_analysis.web.run_view import build_run_view

from abm_test_helpers import (
    make_synthetic_experiment,
    write_synthetic_asset_timeseries,
    write_synthetic_protagonist,
    write_synthetic_run,
)


#: The four tokens ``_classify_conclusion`` can produce. The synthetic fixtures
#: draw returns independently of price, so a test may assert membership here but
#: never a particular verdict.
VERDICT_TOKENS = {"supported", "partial", "not-supported", "unavailable"}

SYNTHETIC_RUN_ID = "20260427143012_1_1_0_1_20_30_5_2_180_66"


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    """Build an archive that mirrors the three real layouts under ``data/``.

    Runs appear inside an experiment directory, inside a calibration study, and
    directly under the root — the shape ``data/latest`` takes.
    """

    root = tmp_path / "data"
    experiments_dir = root / "experiments"
    experiments_dir.mkdir(parents=True)

    experiment_dir = make_synthetic_experiment(experiments_dir)

    study_runs_dir = root / "calibration" / "study_20260101000000" / "simulation_runs"
    study_runs_dir.mkdir(parents=True)
    write_synthetic_run(
        study_runs_dir / "20260427143212_1_0_0_1_20_30_5_2_180_68",
        "20260427143212_1_0_0_1_20_30_5_2_180_68",
        68,
        0.01,
    )

    write_synthetic_run(root / "latest", "20260427143312_1_0_0_1_20_30_5_2_180_69", 69, 0.0)

    # Report output written beside a run must never be mistaken for a run.
    report_dir = experiment_dir / "20260427143012_1_1_0_1_20_30_5_2_180_66" / "python_analysis"
    (report_dir / "figures").mkdir(parents=True)
    (report_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    return root


@pytest.fixture()
def client(data_root: Path) -> TestClient:
    """Return a test client bound to the synthetic archive."""

    return TestClient(create_app(data_root))


def test_discovery_finds_runs_at_every_archive_depth(data_root: Path) -> None:
    discovered = {path.name for path in discover_runs(data_root)}

    assert "20260427143012_1_1_0_1_20_30_5_2_180_66" in discovered
    assert "20260427143212_1_0_0_1_20_30_5_2_180_68" in discovered
    assert "latest" in discovered
    assert len(discovered) == 4


def test_discovery_ignores_report_output_beside_a_run(data_root: Path) -> None:
    discovered = {path.name for path in discover_runs(data_root)}

    assert "python_analysis" not in discovered
    assert "figures" not in discovered


def test_catalogue_groups_runs_by_containing_directory(data_root: Path) -> None:
    catalogue = build_catalogue(data_root)
    names = {experiment.name: experiment for experiment in catalogue}

    assert "synthetic_experiment" in names
    assert names["synthetic_experiment"].relative_path == "experiments/synthetic_experiment"
    assert len(names["synthetic_experiment"].runs) == 2
    # A calibration study keeps its full path as its label, because those runs
    # come from a parameter search rather than a deliberate experiment.
    assert "calibration/study_20260101000000/simulation_runs" in names


def test_catalogue_entry_exposes_run_id_parameters(data_root: Path) -> None:
    catalogue = build_catalogue(data_root)
    experiment = next(entry for entry in catalogue if entry.name == "synthetic_experiment")
    first_run = experiment.runs[0].to_dict()

    assert first_run["run_id"] == "20260427143012_1_1_0_1_20_30_5_2_180_66"
    assert first_run["seed"] == 66
    assert first_run["time_steps"] == 180
    assert first_run["population"]["chartists"] == 30


def test_resolve_run_path_rejects_paths_outside_the_data_root(data_root: Path) -> None:
    with pytest.raises(ValueError, match="outside the data root"):
        resolve_run_path("../secrets", data_root)


def test_resolve_run_path_rejects_directories_that_are_not_runs(data_root: Path) -> None:
    with pytest.raises(ValueError, match="Not an archived run"):
        resolve_run_path("experiments", data_root)


def test_run_view_matches_the_diagnostics_module(data_root: Path) -> None:
    """The dashboard must not become a second implementation of the statistics."""

    run_dir = data_root / "experiments" / "synthetic_experiment" / "20260427143012_1_1_0_1_20_30_5_2_180_66"
    view = build_run_view(run_dir)
    diagnostics = run_stylised_fact_diagnostics(run_dir)

    primary = view["assets"]["names"][0]
    returns_group = next(group for group in view["metric_groups"] if group["key"] == "returns")
    metrics = {metric["label"]: metric["values"][primary] for metric in returns_group["metrics"]}

    assert view["observation_count"] == diagnostics["observation_count"]
    assert metrics["Excess kurtosis"] == pytest.approx(diagnostics["excess_kurtosis"])
    assert metrics["Skewness"] == pytest.approx(diagnostics["skewness"])
    assert metrics["Jarque–Bera p"] == pytest.approx(diagnostics["jarque_bera_p_value"])


def test_run_view_pairs_every_stylised_fact_with_its_evidence(data_root: Path) -> None:
    run_dir = data_root / "experiments" / "synthetic_experiment" / "20260427143012_1_1_0_1_20_30_5_2_180_66"
    view = build_run_view(run_dir)

    primary = view["assets"]["names"][0]
    facts = {fact["fact"]: fact for fact in view["stylised_facts"]}
    assert set(facts) == {
        "Absence of linear autocorrelation",
        "Fat tails",
        "Volatility clustering",
    }
    for fact in facts.values():
        entry = fact["assets"][primary]
        assert entry["verdict"] in VERDICT_TOKENS
        assert entry["conclusion"]
        assert len(entry["evidence"]) == 2


def test_run_view_series_stay_index_aligned(data_root: Path) -> None:
    run_dir = data_root / "experiments" / "synthetic_experiment" / "20260427143012_1_1_0_1_20_30_5_2_180_66"
    view = build_run_view(run_dir)
    series = view["series"]
    track = series["assets"][view["assets"]["names"][0]]

    assert series["point_count"] > 0
    assert len(track["price"]) == series["point_count"]
    assert len(track["log_return"]) == series["point_count"]
    assert len(series["step"]) == series["point_count"]


def test_run_view_payload_is_json_serialisable(data_root: Path) -> None:
    """Missing pandas values must leave as ``null``, never as ``NaN`` tokens."""

    run_dir = data_root / "latest"
    encoded = json.dumps(build_run_view(run_dir))

    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_run_view_reports_insufficient_observations_instead_of_failing(data_root: Path) -> None:
    run_dir = data_root / "latest"
    view = build_run_view(run_dir, phase="warmup")

    primary = view["assets"]["names"][0]
    assert view["diagnostic_status"] == "insufficient_observations"
    assert view["diagnostic_message"]
    verdicts = {fact["assets"][primary]["verdict"] for fact in view["stylised_facts"]}
    assert verdicts == {"unavailable"}


def test_catalogue_endpoint_lists_every_run(client: TestClient) -> None:
    payload = client.get("/api/catalogue").json()

    assert payload["run_count"] == 4
    assert payload["data_root_exists"] is True
    assert payload["experiment_count"] == len(payload["experiments"])


def test_run_endpoint_returns_the_statistics_payload(client: TestClient) -> None:
    response = client.get(
        "/api/run",
        params={"path": "experiments/synthetic_experiment/20260427143012_1_1_0_1_20_30_5_2_180_66"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "20260427143012_1_1_0_1_20_30_5_2_180_66"
    assert payload["phase"] == "simulation"
    assert len(payload["metric_groups"]) == 3
    assert payload["assets"]["count"] == 1
    assert payload["autocorrelation"]["available"] is True


def test_run_endpoint_rejects_a_path_outside_the_archive(client: TestClient) -> None:
    response = client.get("/api/run", params={"path": "../../etc"})

    assert response.status_code == 404


def test_run_endpoint_reports_an_unknown_price_column(client: TestClient) -> None:
    response = client.get(
        "/api/run",
        params={
            "path": "experiments/synthetic_experiment/20260427143012_1_1_0_1_20_30_5_2_180_66",
            "price_column": "not_a_column",
        },
    )

    assert response.status_code == 422
    assert "not_a_column" in response.json()["detail"]


def test_index_page_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Market statistics" in response.text


# --------------------------------------------------------------------------
# The asset dimension
# --------------------------------------------------------------------------


@pytest.fixture()
def multi_asset_root(tmp_path: Path) -> Path:
    """Build an archive holding one two-asset run.

    ``write_synthetic_asset_timeseries`` is additive and ``write_synthetic_run``
    creates the directory, so the order matters. The root sits beside, not
    inside, ``data_root``'s, because a test may request both fixtures.
    """

    root = tmp_path / "multi_asset_data"
    experiment_dir = root / "experiments" / "two_asset"
    experiment_dir.mkdir(parents=True)
    run_dir = experiment_dir / SYNTHETIC_RUN_ID
    write_synthetic_run(run_dir, SYNTHETIC_RUN_ID, 66, 0.0)
    write_synthetic_asset_timeseries(run_dir, ["alpha", "beta"])
    return root


@pytest.fixture()
def multi_asset_run(multi_asset_root: Path) -> Path:
    """Return the two-asset run directory."""

    return multi_asset_root / "experiments" / "two_asset" / SYNTHETIC_RUN_ID


def single_asset_run(data_root: Path) -> Path:
    """Return the standard single-asset synthetic run."""

    return data_root / "experiments" / "synthetic_experiment" / SYNTHETIC_RUN_ID


def test_multi_asset_run_reports_every_traded_market(multi_asset_run: Path) -> None:
    assets = build_run_view(multi_asset_run)["assets"]

    assert assets["names"] == ["alpha", "beta"]
    assert assets["count"] == 2
    assert assets["is_multi_asset"] is True
    assert assets["source"] == "asset_timeseries"
    assert assets["primary"] == "alpha"
    assert assets["fundamental_correlation"] == pytest.approx(0.3)


def test_single_asset_run_reports_one_column(data_root: Path) -> None:
    assets = build_run_view(single_asset_run(data_root))["assets"]

    assert assets["count"] == 1
    assert assets["is_multi_asset"] is False
    assert assets["source"] == "step_timeseries"


def test_every_metric_carries_a_value_for_every_asset(multi_asset_run: Path) -> None:
    view = build_run_view(multi_asset_run)
    names = set(view["assets"]["names"])

    for group in view["metric_groups"]:
        for metric in group["metrics"]:
            if metric["scope"] == "primary":
                # A primary-only statistic must not be repeated under another
                # market's heading, so its row carries exactly one value.
                assert set(metric["values"]) == {view["assets"]["primary"]}
            else:
                assert set(metric["values"]) == names


def test_asset_metric_values_match_the_diagnostics_module(multi_asset_run: Path) -> None:
    """The per-asset columns must not become a second implementation either."""

    view = build_run_view(multi_asset_run)
    rows = {
        str(row["asset"]): row
        for row in run_asset_stylised_fact_diagnostics(multi_asset_run)
    }
    returns_group = next(group for group in view["metric_groups"] if group["key"] == "returns")
    metrics = {metric["label"]: metric["values"] for metric in returns_group["metrics"]}

    for asset in view["assets"]["names"]:
        assert metrics["Excess kurtosis"][asset] == pytest.approx(rows[asset]["excess_kurtosis"])
        assert metrics["Skewness"][asset] == pytest.approx(rows[asset]["skewness"])
        assert metrics["Jarque–Bera p"][asset] == pytest.approx(rows[asset]["jarque_bera_p_value"])


def test_metrics_no_longer_explain_themselves(multi_asset_run: Path) -> None:
    """The tables show numbers; the prose that used to sit under each was removed."""

    view = build_run_view(multi_asset_run)

    for group in view["metric_groups"]:
        for metric in group["metrics"]:
            assert "description" not in metric


def test_stylised_facts_report_a_verdict_per_asset(multi_asset_run: Path) -> None:
    view = build_run_view(multi_asset_run)
    names = set(view["assets"]["names"])

    assert len(view["stylised_facts"]) == 3
    for fact in view["stylised_facts"]:
        assert set(fact["assets"]) == names
        for entry in fact["assets"].values():
            assert entry["verdict"] in VERDICT_TOKENS
            assert len(entry["evidence"]) == 2


def test_series_expose_one_track_per_asset(multi_asset_run: Path) -> None:
    view = build_run_view(multi_asset_run)
    series = view["series"]

    assert set(series["assets"]) == set(view["assets"]["names"])
    for track in series["assets"].values():
        assert len(track["price"]) == series["point_count"]
        assert len(track["log_return"]) == series["point_count"]
        assert track["base_price"] is not None
    assert len(series["step"]) == series["point_count"]


def test_autocorrelation_reports_one_function_per_asset(multi_asset_run: Path) -> None:
    autocorrelation = build_run_view(multi_asset_run)["autocorrelation"]

    assert autocorrelation["available"] is True
    bands = []
    for entry in autocorrelation["assets"].values():
        assert len(entry["raw"]) == len(entry["lag"])
        assert len(entry["absolute"]) == len(entry["lag"])
        assert len(entry["squared"]) == len(entry["lag"])
        bands.append(entry["confidence_band"])
    # One shaded region is drawn, so the shared band must be the widest.
    assert autocorrelation["confidence_band"] == pytest.approx(max(bands))


def test_return_distribution_reports_one_density_per_asset(multi_asset_run: Path) -> None:
    distribution = build_run_view(multi_asset_run)["return_distribution"]

    assert distribution["available"] is True
    for entry in distribution["assets"].values():
        assert entry["available"] is True
        assert len(entry["density"]) == len(entry["bin_centre"])


def test_cross_asset_panel_requires_two_markets(multi_asset_run: Path, data_root: Path) -> None:
    cross_asset = build_run_view(multi_asset_run)["cross_asset"]

    assert cross_asset["available"] is True
    assert cross_asset["asset_a"] == "alpha"
    assert cross_asset["asset_b"] == "beta"
    assert cross_asset["configured_correlation"] == pytest.approx(0.3)
    assert len(cross_asset["rolling_correlation"]) == len(cross_asset["step"])
    assert len(cross_asset["price_ratio"]) == len(cross_asset["step"])

    assert build_run_view(single_asset_run(data_root))["cross_asset"]["available"] is False


def test_multi_asset_payload_is_json_serialisable(multi_asset_run: Path) -> None:
    encoded = json.dumps(build_run_view(multi_asset_run))

    assert "NaN" not in encoded
    assert "Infinity" not in encoded


# --------------------------------------------------------------------------
# The awkward archives
# --------------------------------------------------------------------------


def test_warmup_phase_falls_back_to_the_primary_market(multi_asset_run: Path) -> None:
    """The per-asset artefact has no warm-up index, so the page must not blank.

    ``asset_timeseries.csv`` leaves ``simulation_step`` empty for initial and
    warm-up rows, and the panel loader indexes on that column, so asking for the
    warm-up phase yields nothing per asset.
    """

    view = build_run_view(multi_asset_run, phase="warmup")

    assert view["assets"]["source"] == "step_timeseries"
    assert view["assets"]["count"] == 1
    assert view["assets"]["notes"]
    assert view["cross_asset"]["available"] is False
    assert len(view["metric_groups"]) == 3


def test_all_phase_notes_the_per_asset_step_index_limitation(multi_asset_run: Path) -> None:
    view = build_run_view(multi_asset_run, phase="all")

    assert view["assets"]["source"] == "asset_timeseries"
    assert any("simulation phase only" in note for note in view["assets"]["notes"])


def test_a_truncated_asset_artefact_keeps_the_full_statistics(tmp_path: Path) -> None:
    """One inconsistent artefact must not silently truncate a run's statistics.

    Gating on the presence of ``asset_timeseries.csv`` rather than on the number
    of assets it records would drop this run from a full return series to a
    handful of rows, and report "insufficient observations" for a run that has
    plenty. This is ``data/latest``'s shape in the project's own archive.
    """

    run_dir = tmp_path / "truncated" / SYNTHETIC_RUN_ID
    run_dir.parent.mkdir(parents=True)
    write_synthetic_run(run_dir, SYNTHETIC_RUN_ID, 66, 0.0)
    write_synthetic_asset_timeseries(run_dir, ["alpha"], observations=20)

    view = build_run_view(run_dir)
    expected = run_stylised_fact_diagnostics(run_dir)

    assert view["assets"]["source"] == "step_timeseries"
    assert view["observation_count"] == expected["observation_count"]
    assert view["diagnostic_status"] == "completed"


def test_an_asset_artefact_naming_another_asset_is_reported(tmp_path: Path) -> None:
    """When the artefact and the config disagree on names, say so."""

    run_dir = tmp_path / "mismatch" / SYNTHETIC_RUN_ID
    run_dir.parent.mkdir(parents=True)
    write_synthetic_run(run_dir, SYNTHETIC_RUN_ID, 66, 0.0)
    write_synthetic_asset_timeseries(run_dir, ["test_asset"], observations=20)

    configuration = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    configuration["assets"]["primary"] = "asset"
    (run_dir / "config.json").write_text(json.dumps(configuration), encoding="utf-8")

    view = build_run_view(run_dir)

    assert view["assets"]["source"] == "step_timeseries"
    assert any("test_asset" in note for note in view["assets"]["notes"])


# --------------------------------------------------------------------------
# Agents
# --------------------------------------------------------------------------


def test_agent_panel_summarises_each_strategy(data_root: Path) -> None:
    agents = build_run_view(single_asset_run(data_root))["agents"]

    assert agents["available"] is True
    assert agents["agent_count"] == 12
    assert agents["strategy_column"] == "current_strategy_type"
    counts = {row["strategy"]: row["agent_count"] for row in agents["rows"]}
    assert counts == {"chartist": 7, "fundamentalist": 5}


def test_agent_summary_matches_the_statistics_module(data_root: Path) -> None:
    run_dir = single_asset_run(data_root)
    agents = build_run_view(run_dir)["agents"]
    expected = build_agent_summary_statistics(run_dir.parent, [run_dir.name])

    by_strategy = expected.set_index("current_strategy_type")
    for row in agents["rows"]:
        assert row["final_wealth_mean"] == pytest.approx(
            by_strategy.loc[row["strategy"], "final_wealth_mean"]
        )


def test_agent_wealth_distribution_uses_shared_bins(data_root: Path) -> None:
    distribution = build_run_view(single_asset_run(data_root))["agents"]["wealth_distribution"]

    assert distribution["available"] is True
    assert len(distribution["strategies"]) == 2
    for entry in distribution["strategies"]:
        assert len(entry["density"]) == len(distribution["bin_centre"])


def test_wealth_gini_moved_from_the_market_table_to_the_agent_panel(data_root: Path) -> None:
    view = build_run_view(single_asset_run(data_root))

    market = next(group for group in view["metric_groups"] if group["key"] == "market")
    assert all(metric["label"] != "Wealth Gini (final)" for metric in market["metrics"])

    gini = next(
        metric for metric in view["agents"]["metrics"] if metric["label"] == "Wealth Gini (final)"
    )
    assert gini["source"] == "simulator summary"
    assert gini["value"] is not None


def test_agent_panel_reports_absence_without_failing(data_root: Path) -> None:
    """A missing snapshot must say so, not make the panel vanish."""

    run_dir = single_asset_run(data_root)
    (run_dir / "agents_final.csv").unlink()

    agents = build_run_view(run_dir)["agents"]

    assert agents["available"] is False
    assert agents["message"]
    assert agents["rows"] == []
    assert agents["wealth_distribution"]["available"] is False
    # The Gini is a simulator scalar, so it survives the snapshot's absence.
    assert any(metric["label"] == "Wealth Gini (final)" for metric in agents["metrics"])


def test_protagonist_panel_locates_him_in_the_wealth_distribution(data_root: Path) -> None:
    """His standing must be recomputed from the snapshot, not taken on trust."""

    run_dir = single_asset_run(data_root)
    expected = write_synthetic_protagonist(run_dir)

    panel = build_run_view(run_dir)["protagonist"]

    assert panel["available"] is True
    assert panel["message"] is None
    assert panel["identity"]["agent_id"] == expected["agent_id"]
    assert panel["standing"]["percentile"] == pytest.approx(expected["percentile"])
    assert panel["standing"]["rank"] == expected["rank"]
    assert panel["standing"]["population"] == expected["population"]
    assert panel["wealth_marker"] == pytest.approx(expected["final_wealth"])


def test_protagonist_rank_matches_a_rank_computed_from_the_snapshot(data_root: Path) -> None:
    """The panel and a direct count over agents_final.csv must not disagree."""

    run_dir = single_asset_run(data_root)
    write_synthetic_protagonist(run_dir)

    panel = build_run_view(run_dir)["protagonist"]
    agents = pd.read_csv(run_dir / "agents_final.csv")
    protagonist_wealth = float(agents.loc[agents["is_protagonist"] == 1, "final_wealth"].iloc[0])
    poorer = int((agents["final_wealth"] < protagonist_wealth).sum())

    assert panel["standing"]["percentile"] == pytest.approx(poorer / len(agents))
    assert panel["standing"]["rank"] == len(agents) - poorer


def test_protagonist_trajectory_series_stay_index_aligned(data_root: Path) -> None:
    run_dir = single_asset_run(data_root)
    expected = write_synthetic_protagonist(run_dir)

    trajectory = build_run_view(run_dir)["protagonist"]["trajectory"]

    assert trajectory["available"] is True
    assert len(trajectory["step"]) == expected["steps"]
    for values in trajectory["series"].values():
        assert len(values) == len(trajectory["step"])


def test_protagonist_panel_reports_absence_without_failing(data_root: Path) -> None:
    """No protagonist is a modelling choice, so the panel says which absence it is."""

    panel = build_run_view(single_asset_run(data_root))["protagonist"]

    assert panel["available"] is False
    assert panel["message"]
    assert panel["standing"] is None
    assert panel["wealth_marker"] is None
    assert panel["trajectory"]["available"] is False


def test_protagonist_is_counted_in_his_own_strategy_group(data_root: Path) -> None:
    """He is an ordinary trader, so the agent panel must not treat him apart."""

    run_dir = single_asset_run(data_root)
    write_synthetic_protagonist(run_dir)

    agents = build_run_view(run_dir)["agents"]

    counts = {row["strategy"]: row["agent_count"] for row in agents["rows"]}
    assert counts == {"chartist": 7, "fundamentalist": 6}
    assert agents["agent_count"] == 13


def test_protagonist_payload_is_json_serialisable(data_root: Path) -> None:
    run_dir = single_asset_run(data_root)
    write_synthetic_protagonist(run_dir)

    json.dumps(build_run_view(run_dir)["protagonist"])


def test_single_strategy_population_still_renders(data_root: Path) -> None:
    run_dir = single_asset_run(data_root)
    agents = pd.read_csv(run_dir / "agents_final.csv")
    agents["current_strategy_type"] = "noise_trader"
    agents.to_csv(run_dir / "agents_final.csv", index=False)

    panel = build_run_view(run_dir)["agents"]

    assert len(panel["rows"]) == 1
    assert panel["rows"][0]["strategy"] == "noise_trader"
    assert panel["rows"][0]["agent_count"] == 12
    assert len(panel["wealth_distribution"]["strategies"]) == 1


def _write_chartist_variants(run_dir: Path) -> None:
    """Split the synthetic chartists into two rules, as the simulator records them."""

    agents = pd.read_csv(run_dir / "agents_final.csv")
    agents["current_strategy_type"] = (
        ["fundamentalist"] * 5 + ["chartist_momentum"] * 4 + ["chartist_breakout"] * 3
    )
    agents.to_csv(run_dir / "agents_final.csv", index=False)


def test_wealth_densities_are_offered_by_family_on_the_same_bins(data_root: Path) -> None:
    """Six overlaid curves cannot be told apart; three families can."""

    run_dir = single_asset_run(data_root)
    _write_chartist_variants(run_dir)

    distribution = build_run_view(run_dir)["agents"]["wealth_distribution"]

    by_label = {entry["strategy"]: entry for entry in distribution["strategies"]}
    by_family = {entry["strategy"]: entry for entry in distribution["families"]}
    assert set(by_label) == {"fundamentalist", "chartist_momentum", "chartist_breakout"}
    assert set(by_family) == {"fundamentalist", "chartist"}
    assert by_family["chartist"]["count"] == 7
    assert by_label["chartist_momentum"]["family"] == "chartist"
    for entry in distribution["families"]:
        assert len(entry["density"]) == len(distribution["bin_centre"])


def test_social_map_ships_every_agent_with_its_colourings(data_root: Path) -> None:
    run_dir = single_asset_run(data_root)
    agents = pd.read_csv(run_dir / "agents_final.csv")
    agents["x_coordinate"] = [index / 12 for index in range(12)]
    agents["y_coordinate"] = [(index * 5 % 12) / 12 for index in range(12)]
    agents["final_opinion"] = [(-1) ** index * 0.01 * index for index in range(12)]
    agents.to_csv(run_dir / "agents_final.csv", index=False)

    social_map = build_run_view(run_dir)["agents"]["social_map"]

    assert social_map["available"] is True
    for key in ("agent_id", "x", "y", "opinion", "wealth_change", "loss_aversion", "family"):
        assert len(social_map[key]) == 12, key
    assert social_map["family"].count("chartist") == 7
    # The fixture records no loss aversion, so that colouring must read as absent.
    assert all(value is None for value in social_map["loss_aversion"])
    assert not any(social_map["is_protagonist"])


def test_social_map_is_unavailable_without_coordinates(data_root: Path) -> None:
    social_map = build_run_view(single_asset_run(data_root))["agents"]["social_map"]

    assert social_map == {"available": False}


def test_social_map_marks_the_protagonist(data_root: Path) -> None:
    run_dir = single_asset_run(data_root)
    write_synthetic_protagonist(run_dir)
    agents = pd.read_csv(run_dir / "agents_final.csv")
    agents["x_coordinate"] = np.linspace(0.0, 1.0, len(agents))
    agents["y_coordinate"] = np.linspace(1.0, 0.0, len(agents))
    agents.to_csv(run_dir / "agents_final.csv", index=False)

    social_map = build_run_view(run_dir)["agents"]["social_map"]

    assert sum(social_map["is_protagonist"]) == 1
    flagged = social_map["is_protagonist"].index(True)
    assert social_map["agent_id"][flagged] == int(agents["agent_id"].max())


# --------------------------------------------------------------------------
# Application wiring
# --------------------------------------------------------------------------


def test_archive_generation_tracks_every_artefact_the_view_reads(multi_asset_run: Path) -> None:
    """A stale cache key would serve numbers from a superseded archive."""

    baseline = _archive_generation(multi_asset_run)

    for filename in ("agents_final.csv", "asset_timeseries.csv", "config.json", "trade_ledger.csv"):
        path = multi_asset_run / filename
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        assert _archive_generation(multi_asset_run) != baseline, filename
        baseline = _archive_generation(multi_asset_run)


def test_run_endpoint_serves_the_multi_asset_payload(multi_asset_root: Path) -> None:
    client = TestClient(create_app(multi_asset_root))

    response = client.get(
        "/api/run", params={"path": f"experiments/two_asset/{SYNTHETIC_RUN_ID}"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assets"]["count"] == 2
    assert payload["cross_asset"]["available"] is True
    assert payload["agents"]["available"] is True
    assert len(payload["metric_groups"]) == 3


# --------------------------------------------------------------------------
# The cohort dimension
# --------------------------------------------------------------------------
#
# A cohort is the dashboard's answer to the two questions a single run cannot
# settle: whether a result survives the seed, and whether it differs between
# conditions. Both are served by one aggregation, so the tests below check the
# split it makes — seeds collapse, controls separate — and that the numbers it
# shows are the ones the CSV export writes.


#: Six runs: three seeds with prospect theory on, three with it off, identical
#: in every other control. The run-id schema is
#: ``<stamp>_<cpt>_<heterogeneity>_<social>_<short>_<fund>_<chart>_<noise>_<bh>_<steps>_<seed>``.
COHORT_RUN_IDS = (
    ("20260501100001_1_0_0_0_20_30_5_2_180_11", 11),
    ("20260501100002_1_0_0_0_20_30_5_2_180_12", 12),
    ("20260501100003_1_0_0_0_20_30_5_2_180_13", 13),
    ("20260501100004_0_0_0_0_20_30_5_2_180_14", 14),
    ("20260501100005_0_0_0_0_20_30_5_2_180_15", 15),
    ("20260501100006_0_0_0_0_20_30_5_2_180_16", 16),
)

PROSPECT_ON_RUN_IDS = tuple(run_id for run_id, _ in COHORT_RUN_IDS[:3])
PROSPECT_OFF_RUN_IDS = tuple(run_id for run_id, _ in COHORT_RUN_IDS[3:])


@pytest.fixture()
def cohort_root(tmp_path: Path) -> Path:
    """Build an archive holding two conditions of three seeds each."""

    root = tmp_path / "cohort_data"
    experiment_dir = root / "experiments" / "treatment"
    experiment_dir.mkdir(parents=True)
    for run_id, seed in COHORT_RUN_IDS:
        write_synthetic_run(experiment_dir / run_id, run_id, seed, 0.0)
    return root


def cohort_paths(run_ids: tuple[str, ...]) -> list[tuple[str, str]]:
    """Return repeated ``path`` query parameters for the cohort endpoint."""

    return [("path", f"experiments/treatment/{run_id}") for run_id in run_ids]


def cohort_dirs(cohort_root: Path, run_ids: tuple[str, ...]) -> list[Path]:
    """Return the run directories behind a set of run ids."""

    return [cohort_root / "experiments" / "treatment" / run_id for run_id in run_ids]


def test_seeds_of_one_configuration_collapse_into_one_condition(cohort_root: Path) -> None:
    """Seed is the replication device, so varying it must not split conditions."""

    client = TestClient(create_app(cohort_root))

    payload = client.get("/api/cohort", params=cohort_paths(PROSPECT_ON_RUN_IDS)).json()

    assert payload["condition_count"] == 1
    assert payload["run_count"] == 3
    assert payload["seed_count"] == 3
    assert payload["conditions"][0]["seed_count"] == 3


def test_a_changed_control_separates_conditions(cohort_root: Path) -> None:
    """The comparison the thesis makes has to survive as two columns."""

    client = TestClient(create_app(cohort_root))
    every_run = PROSPECT_ON_RUN_IDS + PROSPECT_OFF_RUN_IDS

    payload = client.get("/api/cohort", params=cohort_paths(every_run)).json()

    assert payload["condition_count"] == 2
    assert payload["run_count"] == 6
    labels = {condition["label"] for condition in payload["conditions"]}
    assert labels == {"Prospect theory on", "Prospect theory off"}
    # Only the control that actually varies is offered as the distinguishing
    # parameter; listing all fifteen would bury the contrast.
    for condition in payload["conditions"]:
        assert [entry["label"] for entry in condition["parameters"]] == ["Prospect theory"]


def test_cohort_numbers_are_the_exported_numbers(cohort_root: Path) -> None:
    """The panel and ``robustness_reports/`` must not be able to disagree.

    The dashboard asks for per-asset diagnostics and the CSV export does not, so
    the two are compared through the frame builder they share rather than by
    reading the files: same runs, same call, same aggregate cells.
    """

    from abm_analysis.exports.seed_robustness import build_seed_robustness_frames
    from abm_analysis.web.cohort_view import build_cohort_view

    run_dirs = cohort_dirs(cohort_root, PROSPECT_ON_RUN_IDS)
    frames = build_seed_robustness_frames(run_dirs, per_asset=True)
    payload = build_cohort_view(run_dirs)

    summary_row = frames.seed_robustness.iloc[0]
    condition_id = payload["conditions"][0]["condition_id"]
    asset = payload["assets"]["names"][0]

    checked = 0
    for group in payload["metric_groups"]:
        for metric in group["metrics"]:
            cell = metric["values"][asset][condition_id]
            if cell is None:
                continue
            assert cell["mean"] == pytest.approx(summary_row[f"{metric['key']}_mean"])
            assert cell["std"] == pytest.approx(summary_row[f"{metric['key']}_std"])
            assert cell["ci_low"] == pytest.approx(summary_row[f"{metric['key']}_ci95_lower"])
            checked += 1
    assert checked >= 5, "the comparison table reported almost nothing"


def test_export_still_writes_the_shared_frames(cohort_root: Path) -> None:
    """Splitting compute from write must not have changed what is written."""

    from abm_analysis.exports.seed_robustness import (
        build_seed_robustness_frames,
        write_seed_robustness_tables,
    )

    experiment_dir = cohort_root / "experiments" / "treatment"
    tables = write_seed_robustness_tables(experiment_dir)
    frames = build_seed_robustness_frames(
        cohort_dirs(cohort_root, tuple(run_id for run_id, _ in COHORT_RUN_IDS)),
        manifest_dir=experiment_dir,
    )

    written = pd.read_csv(tables.seed_robustness_csv_path)
    assert len(written) == len(frames.seed_robustness)
    assert written["condition_id"].tolist() == frames.seed_robustness["condition_id"].tolist()
    assert pd.read_csv(tables.verdicts_csv_path)["criterion"].tolist() == (
        frames.verdicts["criterion"].tolist()
    )


def test_success_rates_count_seeds_not_percentages(cohort_root: Path) -> None:
    """A rate without its denominator is not evidence; 4/5 and 80/100 differ."""

    client = TestClient(create_app(cohort_root))

    payload = client.get("/api/cohort", params=cohort_paths(PROSPECT_ON_RUN_IDS)).json()

    condition_id = payload["conditions"][0]["condition_id"]
    asset = payload["assets"]["names"][0]
    assert len(payload["success_rates"]) == 3
    for fact in payload["success_rates"]:
        entry = fact["assets"][asset][condition_id]
        assert entry["runs"] == 3
        assert entry["verdict"] in VERDICT_TOKENS
        if entry["rate"] is not None:
            assert entry["successes"] == pytest.approx(entry["rate"] * entry["runs"], abs=0.5)


def test_verdicts_are_labelled_by_condition_not_by_summary_row(cohort_root: Path) -> None:
    """``Condition 3`` would name a row the reader was never shown."""

    client = TestClient(create_app(cohort_root))
    every_run = PROSPECT_ON_RUN_IDS + PROSPECT_OFF_RUN_IDS

    payload = client.get("/api/cohort", params=cohort_paths(every_run)).json()

    assert payload["verdicts"], "no robustness criteria were evaluated"
    scopes = {card["scope"] for card in payload["verdicts"] if card["scope"]}
    assert scopes, "multi-condition verdicts lost their condition labels"
    assert not any(str(scope).startswith("Condition ") for scope in scopes)
    for card in payload["verdicts"]:
        assert card["token"] in VERDICT_TOKENS
        assert not card["criterion"].startswith("Condition ")


def test_interface_files_are_revalidated_on_every_load(tmp_path: Path) -> None:
    """A cached app.js against a newer index.html breaks the page on upgrade."""

    client = TestClient(create_app(tmp_path))

    for path in ("/", "/static/app.js", "/static/styles.css"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "no-cache", path
    assert "cache-control" not in client.get("/api/catalogue").headers


def test_index_references_assets_by_content_version(tmp_path: Path) -> None:
    """A changed script must be a new URL, so no browser can keep the old one."""

    import re

    from abm_analysis.web.app import STATIC_DIRECTORY, _asset_version

    client = TestClient(create_app(tmp_path))

    html = client.get("/").text
    for name in ("styles.css", "app.js"):
        match = re.search(rf'/static/{re.escape(name)}\?v=([0-9a-f]+)', html)
        assert match, f"{name} is not versioned in the page"
        assert match.group(1) == _asset_version(STATIC_DIRECTORY / name)
        assert client.get(f"/static/{name}?v={match.group(1)}").status_code == 200
    assert "/static/app.js\"" not in html


def test_verdict_cards_expose_the_rule_as_numbers(cohort_root: Path) -> None:
    """The verdict table prints a value against its cut-offs, not a sentence."""

    from abm_analysis.statistics.robustness_verdicts import MINIMUM_SEEDS_FOR_VERDICTS
    from abm_analysis.web.cohort_view import VERDICT_CATEGORY_LABELS

    client = TestClient(create_app(cohort_root))

    payload = client.get("/api/cohort", params=cohort_paths(PROSPECT_ON_RUN_IDS)).json()

    assert payload["verdict_minimum_seeds"] == MINIMUM_SEEDS_FOR_VERDICTS
    assert payload["verdicts"], "no robustness criteria were evaluated"
    for card in payload["verdicts"]:
        assert card["statistic"]
        assert card["category_label"] == VERDICT_CATEGORY_LABELS[card["category"]]
        assert card["value_format"] in {"ratio", "share", "p_value"}
        assert card["comparison"] in {"<=", ">="}
        assert isinstance(card["pass_threshold"], float)
        assert isinstance(card["borderline_threshold"], float)
        assert card["value"] is None or isinstance(card["value"], float)
        assert card["sample_size"] is None or isinstance(card["sample_size"], int)
        # Prose survives for the tooltips.
        assert card["hypothesis"] and card["interpretation"]


def test_cohort_payload_is_json_serialisable(cohort_root: Path) -> None:
    """NaN dispersion at n = 1 must reach the browser as null, not NaN."""

    from abm_analysis.web.cohort_view import build_cohort_view

    payload = build_cohort_view(cohort_dirs(cohort_root, PROSPECT_ON_RUN_IDS))
    encoded = json.dumps(payload)

    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_cohort_rejects_a_selection_that_is_too_small(cohort_root: Path) -> None:
    client = TestClient(create_app(cohort_root))

    response = client.get("/api/cohort", params=cohort_paths(PROSPECT_ON_RUN_IDS[:1]))

    assert response.status_code == 422
    assert "at least" in response.json()["detail"]


def test_cohort_collapses_a_run_selected_twice(cohort_root: Path) -> None:
    """Counting one run twice would halve every dispersion statistic."""

    client = TestClient(create_app(cohort_root))
    duplicated = cohort_paths(PROSPECT_ON_RUN_IDS) + cohort_paths(PROSPECT_ON_RUN_IDS[:1])

    payload = client.get("/api/cohort", params=duplicated).json()

    assert payload["run_count"] == 3
    assert payload["seed_count"] == 3


def test_cohort_rejects_a_traversal_in_any_position(cohort_root: Path) -> None:
    """A list of paths is no more trusted than a single one."""

    client = TestClient(create_app(cohort_root))
    params = cohort_paths(PROSPECT_ON_RUN_IDS[:2]) + [("path", "../outside")]

    response = client.get("/api/cohort", params=params)

    assert response.status_code == 404


def test_experiment_cohort_endpoint_gathers_the_whole_group(cohort_root: Path) -> None:
    client = TestClient(create_app(cohort_root))

    payload = client.get(
        "/api/cohort/experiment", params={"path": "experiments/treatment"}
    ).json()

    assert payload["run_count"] == len(COHORT_RUN_IDS)
    assert payload["condition_count"] == 2


def test_cohort_convergence_never_pools_two_conditions(cohort_root: Path) -> None:
    """A path mixing conditions would show the contrast as dispersion."""

    client = TestClient(create_app(cohort_root))
    every_run = PROSPECT_ON_RUN_IDS + PROSPECT_OFF_RUN_IDS

    payload = client.get("/api/cohort", params=cohort_paths(every_run)).json()

    assert payload["convergence"]["available"] is True
    for entry in payload["convergence"]["series"]:
        assert entry["condition_id"] is not None
        # Three seeds per condition, so no path may claim more.
        assert max(entry["seed_count"]) <= 3


def test_per_run_diagnostics_are_reused_across_cohorts(cohort_root: Path) -> None:
    """A cohort must cost only its uncached runs, not a refit of every run.

    Each run carries a GARCH(1,1) fit. Without this, adding one run to a
    selection would refit every run already in it, and the dashboard would be
    unusable at the replication counts the thesis actually needs.
    """

    from abm_analysis.web.app import _cached_run_diagnostics

    client = TestClient(create_app(cohort_root))
    every_run = PROSPECT_ON_RUN_IDS + PROSPECT_OFF_RUN_IDS
    _cached_run_diagnostics.cache_clear()

    client.get("/api/cohort", params=cohort_paths(every_run))
    after_first = _cached_run_diagnostics.cache_info()
    assert after_first.misses == len(every_run)
    assert after_first.hits == 0

    # A different cohort over the same archives: nothing may be refitted.
    client.get("/api/cohort", params=cohort_paths(every_run[:-1]))
    after_second = _cached_run_diagnostics.cache_info()
    assert after_second.misses == after_first.misses
    assert after_second.hits == len(every_run) - 1


def test_touching_an_artefact_invalidates_the_cohort(cohort_root: Path) -> None:
    """A cohort must never show numbers from a superseded archive."""

    from abm_analysis.web.app import _cached_cohort_view

    client = TestClient(create_app(cohort_root))
    params = cohort_paths(PROSPECT_ON_RUN_IDS)
    _cached_cohort_view.cache_clear()

    client.get("/api/cohort", params=params)
    # The same request again is a hit, which is what makes the miss below
    # evidence of invalidation rather than of an ineffective cache.
    client.get("/api/cohort", params=params)
    assert _cached_cohort_view.cache_info().hits == 1
    misses = _cached_cohort_view.cache_info().misses

    summary = cohort_dirs(cohort_root, PROSPECT_ON_RUN_IDS)[0] / "summary_metrics.csv"
    summary.write_text(summary.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert client.get("/api/cohort", params=params).status_code == 200
    assert _cached_cohort_view.cache_info().misses == misses + 1
