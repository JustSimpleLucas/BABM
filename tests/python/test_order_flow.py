"""Tests for order flow by strategy: the ledger statistics and the dashboard payload.

The properties worth pinning are the ones a reader would otherwise have to take on
trust. A trade is logged once per side, so a statistic that must count it once has
to use one side; net flow must balance to zero because every unit bought is sold;
and a long run's thinned chart must not lose the volume it thins away.
"""

from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from abm_analysis.statistics.agents import STRATEGY_FAMILIES, strategy_family
from abm_analysis.statistics.order_flow import (
    UNKNOWN_GROUP,
    build_group_lookup,
    counterparty_volume,
    maximum_net_flow_residual,
    net_flow_by_strategy,
    protagonist_fills,
    read_trade_ledger,
)
from abm_analysis.web import metrics as web_metrics
from abm_analysis.web.run_view import build_run_view

from abm_test_helpers import (
    write_synthetic_asset_timeseries,
    write_synthetic_protagonist,
    write_synthetic_run,
    write_synthetic_trade_ledger,
)


RUN_ID = "20260427143012_1_1_0_1_20_30_5_2_180_66"


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    """Return a single-asset synthetic run with a two-sided ledger."""

    directory = tmp_path / RUN_ID
    write_synthetic_run(directory, RUN_ID, 66, 0.0)
    write_synthetic_trade_ledger(directory)
    return directory


@pytest.fixture()
def two_asset_run(tmp_path: Path) -> Path:
    """Return a two-asset synthetic run with a protagonist who trades."""

    parent = tmp_path / "two_asset"
    parent.mkdir()
    directory = parent / RUN_ID
    write_synthetic_run(directory, RUN_ID, 66, 0.0)
    write_synthetic_asset_timeseries(directory, ["alpha", "beta"])
    write_synthetic_protagonist(directory)
    write_synthetic_trade_ledger(directory, assets=["alpha", "beta"])
    return directory


# --------------------------------------------------------------------------
# Strategy families
# --------------------------------------------------------------------------


def test_chartist_variants_collapse_into_one_family() -> None:
    labels = [
        "chartist_momentum",
        "chartist_mean_reversion",
        "chartist_breakout",
        "chartist_relative_strength_index",
        "chartist",
    ]

    assert {strategy_family(label) for label in labels} == {"chartist"}
    assert strategy_family("fundamentalist") == "fundamentalist"


def test_an_unrecognised_strategy_is_kept_apart_rather_than_merged() -> None:
    assert strategy_family("herding_trader") == "herding_trader"
    assert "herding_trader" not in STRATEGY_FAMILIES


# --------------------------------------------------------------------------
# The ledger reader
# --------------------------------------------------------------------------


def test_reader_accepts_lower_case_sides_and_drops_unusable_rows(tmp_path: Path) -> None:
    path = tmp_path / "trade_ledger.csv"
    pd.DataFrame(
        {
            "time": [1, 2, 3, 4],
            "agent_id": [1, 2, 3, np.nan],
            "counterparty_agent_id": [2, 1, 4, 3],
            "side": ["buy", "Sell", "hold", "BUY"],
            "price": [100.0, 100.0, 100.0, 100.0],
            "qty": [5.0, 5.0, 5.0, 5.0],
            "asset": ["a", "a", "a", "a"],
        }
    ).to_csv(path, index=False)

    ledger = read_trade_ledger(path)

    assert list(ledger["side"]) == ["BUY", "SELL"]
    assert len(ledger) == 2


def test_reader_reads_a_compressed_ledger(tmp_path: Path, run_dir: Path) -> None:
    compressed = tmp_path / "trade_ledger.csv.gz"
    with (run_dir / "trade_ledger.csv").open("rb") as source, gzip.open(compressed, "wb") as target:
        shutil.copyfileobj(source, target)

    assert len(read_trade_ledger(compressed)) == len(read_trade_ledger(run_dir / "trade_ledger.csv"))


def test_reader_returns_an_empty_frame_without_a_ledger() -> None:
    assert read_trade_ledger(None).empty


# --------------------------------------------------------------------------
# Net flow
# --------------------------------------------------------------------------


def _agents_by_family(run_dir: Path) -> dict[int, str]:
    return build_group_lookup(pd.read_csv(run_dir / "agents_final.csv"), "family")


def test_net_flow_balances_for_a_two_sided_ledger(run_dir: Path) -> None:
    ledger = read_trade_ledger(run_dir / "trade_ledger.csv")
    flows = net_flow_by_strategy(ledger, _agents_by_family(run_dir))

    assert maximum_net_flow_residual(flows) == pytest.approx(0.0, abs=1e-9)
    assert set(flows["group"]) <= {"fundamentalist", "chartist"}


def test_net_flow_does_not_balance_when_a_side_is_missing(run_dir: Path) -> None:
    ledger = read_trade_ledger(run_dir / "trade_ledger.csv")
    one_sided = ledger[ledger["side"] == "BUY"]
    flows = net_flow_by_strategy(one_sided, _agents_by_family(run_dir))

    assert maximum_net_flow_residual(flows) > 0.0


def test_net_flow_matches_a_hand_computed_ledger() -> None:
    ledger = pd.DataFrame(
        {
            "time": [1, 1, 1, 1],
            "agent_id": [1, 2, 3, 2],
            "counterparty_agent_id": [2, 1, 2, 3],
            "side": ["BUY", "SELL", "BUY", "SELL"],
            "price": 100.0,
            "qty": [4.0, 4.0, 1.0, 1.0],
            "asset": "a",
        }
    )
    lookup = {1: "fundamentalist", 2: "chartist", 3: "noise_trader"}

    flows = net_flow_by_strategy(ledger, lookup).set_index("group")["net_quantity"]

    # Agent 1 buys 4 from agent 2; agent 3 buys 1 from agent 2.
    assert flows["fundamentalist"] == 4.0
    assert flows["noise_trader"] == 1.0
    assert flows["chartist"] == -5.0


# --------------------------------------------------------------------------
# Who traded with whom
# --------------------------------------------------------------------------


def test_counterparty_volume_counts_each_trade_once() -> None:
    ledger = pd.DataFrame(
        {
            "time": [1, 1, 2, 2],
            "agent_id": [1, 2, 3, 2],
            "counterparty_agent_id": [2, 1, 2, 3],
            "side": ["BUY", "SELL", "BUY", "SELL"],
            "price": 100.0,
            "qty": [4.0, 4.0, 1.0, 1.0],
            "asset": "a",
        }
    )
    lookup = {1: "fundamentalist", 2: "chartist", 3: "noise_trader"}

    matrix = counterparty_volume(ledger, lookup)
    cells = {(r.buyer_group, r.seller_group): r.quantity for r in matrix.itertuples()}

    assert cells == {("fundamentalist", "chartist"): 4.0, ("noise_trader", "chartist"): 1.0}
    assert matrix["quantity"].sum() == 5.0, "both rows of each trade must not be summed"


def test_an_agent_the_snapshot_does_not_list_is_reported_not_hidden() -> None:
    ledger = pd.DataFrame(
        {
            "time": [1],
            "agent_id": [1],
            "counterparty_agent_id": [99],
            "side": ["BUY"],
            "price": 100.0,
            "qty": [2.0],
            "asset": "a",
        }
    )

    matrix = counterparty_volume(ledger, {1: "fundamentalist"})

    assert matrix.iloc[0]["seller_group"] == UNKNOWN_GROUP


def test_protagonist_fills_are_that_agents_rows_in_time_order(run_dir: Path) -> None:
    ledger = read_trade_ledger(run_dir / "trade_ledger.csv")
    agent_id = int(ledger["agent_id"].iloc[0])

    fills = protagonist_fills(ledger, agent_id)

    assert not fills.empty
    assert (ledger[ledger["agent_id"] == agent_id].shape[0]) == len(fills)
    assert fills["time"].is_monotonic_increasing


# --------------------------------------------------------------------------
# The dashboard payload
# --------------------------------------------------------------------------


def test_payload_flows_balance_and_the_ledger_is_reported_balanced(run_dir: Path) -> None:
    order_flow = build_run_view(run_dir)["order_flow"]

    assert order_flow["available"] is True
    assert order_flow["checks"]["balanced"] is True
    family = order_flow["groupings"]["family"]
    asset = family["assets"]["market"]
    totals = np.sum([asset["net"][group] for group in family["groups"]], axis=0)
    assert np.allclose(totals, 0.0)


def test_payload_counterparty_volume_equals_the_ledger_total(run_dir: Path) -> None:
    ledger = pd.read_csv(run_dir / "trade_ledger.csv")
    expected = ledger.loc[ledger["side"] == "BUY", "qty"].sum()

    order_flow = build_run_view(run_dir)["order_flow"]

    for grouping in ("family", "label"):
        block = order_flow["groupings"][grouping]["assets"]["market"]["counterparty"]
        assert np.sum(block["volume"]) == pytest.approx(expected)
        assert np.allclose(np.array(block["share"]).sum(axis=1), 1.0)


def test_both_groupings_are_shipped_so_the_browser_never_sums_arrays(run_dir: Path) -> None:
    groupings = build_run_view(run_dir)["order_flow"]["groupings"]

    assert set(groupings) == {"family", "label"}
    assert groupings["family"]["groups"][0] == "fundamentalist"
    assert groupings["label"]["family_of_group"]["chartist"] == "chartist"


def test_a_single_market_ledger_is_matched_to_the_runs_only_asset(run_dir: Path) -> None:
    """The fixture ledger names its asset ``stock``; the run, with no config, names it ``market``."""

    assets = build_run_view(run_dir)["order_flow"]["groupings"]["family"]["assets"]

    assert list(assets) == ["market"]


def test_a_multi_asset_ledger_is_keyed_by_asset(two_asset_run: Path) -> None:
    order_flow = build_run_view(two_asset_run)["order_flow"]

    assert list(order_flow["groupings"]["family"]["assets"]) == ["alpha", "beta"]
    assert order_flow["checks"]["balanced"] is True


def test_a_ledger_naming_unknown_assets_is_reported_unavailable(two_asset_run: Path) -> None:
    ledger = pd.read_csv(two_asset_run / "trade_ledger.csv")
    ledger["asset"] = "gamma"
    ledger.to_csv(two_asset_run / "trade_ledger.csv", index=False)

    order_flow = build_run_view(two_asset_run)["order_flow"]

    assert order_flow["available"] is False
    assert "gamma" in order_flow["message"]


def test_protagonist_fills_are_placed_on_the_assets_he_traded(two_asset_run: Path) -> None:
    ledger = pd.read_csv(two_asset_run / "trade_ledger.csv")
    protagonist_id = int(pd.read_csv(two_asset_run / "agents_final.csv")["agent_id"].max())
    expected = ledger[ledger["agent_id"] == protagonist_id]

    block = build_run_view(two_asset_run)["order_flow"]["protagonist"]

    assert block["available"] is True
    assert block["agent_id"] == protagonist_id
    assert sum(len(asset["x"]) for asset in block["assets"].values()) == len(expected)
    for name, asset in block["assets"].items():
        rows = expected[expected["asset"] == name]
        assert asset["side"] == list(rows["side"])
        assert asset["quantity"] == pytest.approx(list(rows["qty"]))


def test_a_run_without_a_protagonist_has_no_fills_to_draw(run_dir: Path) -> None:
    assert build_run_view(run_dir)["order_flow"]["protagonist"] == {"available": False}


def test_a_missing_ledger_is_reported_not_raised(run_dir: Path) -> None:
    (run_dir / "trade_ledger.csv").unlink()

    order_flow = build_run_view(run_dir)["order_flow"]

    assert order_flow["available"] is False
    assert "trade_ledger_enabled" in order_flow["message"]


def test_a_one_sided_ledger_is_flagged_as_unbalanced(run_dir: Path) -> None:
    ledger = pd.read_csv(run_dir / "trade_ledger.csv")
    ledger[ledger["side"] == "BUY"].to_csv(run_dir / "trade_ledger.csv", index=False)

    checks = build_run_view(run_dir)["order_flow"]["checks"]

    assert checks["balanced"] is False
    assert checks["net_flow_residual"] > 0


def test_thinning_a_long_series_does_not_lose_traded_volume(
    run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow is an amount per step: thinning must add steps together, not skip them."""

    unthinned = build_run_view(run_dir)["order_flow"]["groupings"]["family"]
    monkeypatch.setattr(web_metrics, "MAXIMUM_SERIES_POINTS", 40)
    thinned_view = build_run_view(run_dir)
    thinned = thinned_view["order_flow"]["groupings"]["family"]

    assert thinned_view["series"]["stride"] > 1
    assert len(thinned["assets"]["market"]["x"]) < len(unthinned["assets"]["market"]["x"])
    for group in unthinned["groups"]:
        assert sum(thinned["assets"]["market"]["net"][group]) == pytest.approx(
            sum(unthinned["assets"]["market"]["net"][group])
        )


def test_order_flow_payload_is_json_serialisable(two_asset_run: Path) -> None:
    encoded = json.dumps(build_run_view(two_asset_run)["order_flow"])

    assert "NaN" not in encoded
    assert "Infinity" not in encoded
