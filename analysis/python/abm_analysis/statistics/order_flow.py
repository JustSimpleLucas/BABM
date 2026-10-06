"""Who traded with whom: order flow by strategy, read from the trade ledger.

The price series says where the market went. The trade ledger says who pushed it
there, and that is the question a behavioural agent-based model exists to ask:
when the price fell, were the chartists selling into it, were the
fundamentalists buying it, and who absorbed whom? Aggregating the ledger by the
strategy each agent ran turns a million fills into three or four numbers per
step that can be read against the price.

**The ledger records every trade twice**, once from each side: a BUY row for the
buyer, with the seller as counterparty, and a SELL row for the seller, with the
buyer as counterparty. That shapes every aggregation here:

* Volume that must count each trade *once* — the counterparty matrix, gross
  volume — uses the BUY rows only. Summing both sides would double it.
* Net flow signs both sides (``+qty`` bought, ``−qty`` sold) and adds them up
  per strategy. Every unit one agent buys another sells, so the net flows of all
  strategies sum to **zero at every step**. That is an accounting identity of the
  matching engine, and :func:`maximum_net_flow_residual` measures how far a
  ledger departs from it — a ledger that does not balance is incomplete or
  corrupt, and the number says so before anyone reads a chart built on it.

Net flow by strategy is the order-flow decomposition used to study how
heterogeneous trading rules shape the limit order book in agent-based markets
(Chiarella, Iori and Perelló, 2009, *Journal of Economic Dynamics and Control*).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from abm_analysis.statistics.agents import agent_strategy_column, strategy_family


#: Ledger columns the aggregations need. Reading only these keeps a ledger of a
#: million rows cheap: the file also carries order ids and cash flows that no
#: order-flow statistic uses.
LEDGER_COLUMNS = (
    "time",
    "agent_id",
    "counterparty_agent_id",
    "side",
    "price",
    "qty",
    "asset",
)

#: Group assigned to an agent the snapshot does not list. Its presence is a
#: finding in itself — the ledger and the snapshot disagree about who traded.
UNKNOWN_GROUP = "unknown"

#: The two ways agents can be grouped for flow statistics: by strategy family,
#: or by the exact strategy label (which splits the chartist variants).
GROUPINGS = ("family", "label")


def read_trade_ledger(ledger_csv: Path | None) -> pd.DataFrame:
    """Read the trade ledger's order-flow columns, normalised for aggregation.

    Args:
        ledger_csv: Path of ``trade_ledger.csv`` (plain or gzip-compressed), or
            ``None`` when the run was archived without one.

    Returns:
        One row per ledger line with ``side`` upper-cased to ``BUY``/``SELL``,
        numeric ids, quantity and price, and rows missing any of step, agent,
        side or quantity dropped. An empty frame when there is no ledger.
    """

    if ledger_csv is None or not ledger_csv.is_file():
        return pd.DataFrame(columns=LEDGER_COLUMNS)

    ledger = pd.read_csv(ledger_csv, usecols=lambda column: column in LEDGER_COLUMNS)
    for column in LEDGER_COLUMNS:
        if column not in ledger.columns:
            ledger[column] = np.nan

    ledger["side"] = ledger["side"].astype(str).str.strip().str.upper()
    ledger = ledger[ledger["side"].isin(("BUY", "SELL"))].copy()
    for column in ("time", "agent_id", "counterparty_agent_id", "price", "qty"):
        ledger[column] = pd.to_numeric(ledger[column], errors="coerce")
    ledger = ledger.dropna(subset=["time", "agent_id", "qty"])
    ledger["asset"] = ledger["asset"].fillna("").astype(str)
    return ledger[list(LEDGER_COLUMNS)].reset_index(drop=True)


def build_group_lookup(agents: pd.DataFrame, grouping: str = "family") -> dict[int, str]:
    """Map each agent id to the group its flow is attributed to.

    Args:
        agents: The end-of-run agent snapshot.
        grouping: ``"family"`` to merge the chartist variants into one group, or
            ``"label"`` to keep each recorded strategy label apart.

    Returns:
        ``{agent_id: group}``. Empty when the snapshot names no strategy, in which
        case every agent falls into :data:`UNKNOWN_GROUP`.
    """

    if grouping not in GROUPINGS:
        raise ValueError(f"grouping must be one of {GROUPINGS}, got {grouping!r}")
    strategy_column = agent_strategy_column(agents) if not agents.empty else None
    if strategy_column is None or "agent_id" not in agents.columns:
        return {}

    ids = pd.to_numeric(agents["agent_id"], errors="coerce")
    labels = agents[strategy_column].astype(str).str.strip()
    groups = labels.map(strategy_family) if grouping == "family" else labels
    return {int(agent_id): str(group) for agent_id, group in zip(ids, groups) if np.isfinite(agent_id)}


def net_flow_by_strategy(ledger: pd.DataFrame, group_of_agent: dict[int, str]) -> pd.DataFrame:
    """Sum each group's signed traded quantity per step and asset.

    Returns:
        One row per (asset, time, group) with ``net_quantity`` (bought minus
        sold), ``bought_quantity`` and ``sold_quantity``. For a ledger that
        records both sides of every trade, ``net_quantity`` sums to zero across
        groups at each (asset, time).
    """

    columns = ["asset", "time", "group", "net_quantity", "bought_quantity", "sold_quantity"]
    if ledger.empty:
        return pd.DataFrame(columns=columns)

    is_buy = ledger["side"] == "BUY"
    flows = pd.DataFrame(
        {
            "asset": ledger["asset"],
            "time": ledger["time"],
            "group": ledger["agent_id"].astype(int).map(group_of_agent).fillna(UNKNOWN_GROUP),
            "bought_quantity": np.where(is_buy, ledger["qty"], 0.0),
            "sold_quantity": np.where(is_buy, 0.0, ledger["qty"]),
        }
    )
    flows["net_quantity"] = flows["bought_quantity"] - flows["sold_quantity"]
    grouped = flows.groupby(["asset", "time", "group"], as_index=False, sort=True)[
        ["net_quantity", "bought_quantity", "sold_quantity"]
    ].sum()
    return grouped[columns]


def maximum_net_flow_residual(flows: pd.DataFrame) -> float:
    """Return the largest |Σ over groups of net quantity| at any (asset, step).

    Zero for a ledger that records both sides of every trade. A positive value
    means some trades were logged from one side only, so net flow by strategy
    does not balance and should not be read as a decomposition of the market.
    """

    if flows.empty:
        return 0.0
    totals = flows.groupby(["asset", "time"])["net_quantity"].sum()
    return float(totals.abs().max())


def counterparty_volume(ledger: pd.DataFrame, group_of_agent: dict[int, str]) -> pd.DataFrame:
    """Total quantity bought by each group from each other group.

    Uses the BUY rows only, so each trade is counted once: the buyer is the row's
    agent and the seller is its counterparty.

    Returns:
        One row per (asset, buyer group, seller group) with the traded
        ``quantity`` and the number of ``trades``.
    """

    columns = ["asset", "buyer_group", "seller_group", "quantity", "trades"]
    purchases = ledger[ledger["side"] == "BUY"]
    if purchases.empty:
        return pd.DataFrame(columns=columns)

    sellers = purchases["counterparty_agent_id"]
    seller_group = (
        sellers.where(np.isfinite(sellers), -1).astype(int).map(group_of_agent).fillna(UNKNOWN_GROUP)
    )
    matrix = pd.DataFrame(
        {
            "asset": purchases["asset"],
            "buyer_group": purchases["agent_id"].astype(int).map(group_of_agent).fillna(UNKNOWN_GROUP),
            "seller_group": seller_group,
            "quantity": purchases["qty"],
        }
    )
    grouped = matrix.groupby(["asset", "buyer_group", "seller_group"], as_index=False).agg(
        quantity=("quantity", "sum"),
        trades=("quantity", "size"),
    )
    return grouped[columns]


def protagonist_fills(ledger: pd.DataFrame, agent_id: int) -> pd.DataFrame:
    """Return one agent's own fills in time order.

    Returns:
        One row per fill with ``asset``, ``time``, ``side``, ``price`` and ``qty``.
    """

    columns = ["asset", "time", "side", "price", "qty"]
    fills = ledger[ledger["agent_id"] == agent_id]
    return fills[columns].sort_values(["time", "asset"]).reset_index(drop=True)
