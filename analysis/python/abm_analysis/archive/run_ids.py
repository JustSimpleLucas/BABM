"""Run identifier parsing for archived ABM simulation outputs."""

from __future__ import annotations

from datetime import datetime

import pandas as pd


RUN_ID_FIELDS = [
    "timestamp",
    "prospect_theory_enabled",
    "prospect_heterogeneity_enabled",
    "social_enabled",
    "short_selling_enabled",
    "num_fundamentalists",
    "num_chartists",
    "num_noise_traders",
    "num_buy_and_hold_agents",
    "time_steps",
    "seed",
]

PRE_BUY_HOLD_RUN_ID_FIELDS = [
    "timestamp",
    "prospect_theory_enabled",
    "prospect_heterogeneity_enabled",
    "social_enabled",
    "short_selling_enabled",
    "num_fundamentalists",
    "num_chartists",
    "num_noise_traders",
    "time_steps",
    "seed",
]

LEGACY_RUN_ID_FIELDS = [
    "timestamp",
    "prospect_theory_enabled",
    "prospect_heterogeneity_enabled",
    "social_enabled",
    "short_selling_enabled",
    "num_fundamentalists",
    "num_chartists",
    "time_steps",
    "seed",
]


def parse_run_id(run_id: str) -> dict[str, object]:
    """Parse the numeric run identifier required by the project convention.

    The C++ archive uses
    ``YYYYMMDDHHMMSS_<prospect_theory>_<prospect_heterogeneity>_<social>_
    <short_sale>_<num_fundamentalists>_<num_chartists>_<num_noise_traders>_
    <num_buy_and_hold_agents>_<time_steps>_<seed>``.
    The parser is deliberately tolerant: malformed fields become missing values
    rather than preventing comparison of older or manually copied runs. Older
    IDs without ``num_buy_and_hold_agents`` or ``num_noise_traders`` remain
    accepted and are interpreted as zero for the missing population counts.

    The folder-name schema is frozen. Three historical variants already need
    permanent parser support, so new experimental parameters must be recorded
    in ``metadata.json`` and ``summary_metrics.csv`` instead of extending the
    run-id; analysis code should treat those artefacts as the authoritative
    parameter record and use the run-id only as a sortable label.
    """

    parts = run_id.split("_")
    values: dict[str, object] = {"run_id": run_id}
    if len(parts) == len(RUN_ID_FIELDS):
        field_schema = RUN_ID_FIELDS
    elif len(parts) == len(PRE_BUY_HOLD_RUN_ID_FIELDS):
        field_schema = PRE_BUY_HOLD_RUN_ID_FIELDS
    else:
        field_schema = LEGACY_RUN_ID_FIELDS
    for field_name, raw_value in zip(field_schema, parts):
        values[f"run_id_{field_name}"] = raw_value

    timestamp_value = parts[0] if parts else ""
    try:
        values["run_id_created_at_local"] = datetime.strptime(
            timestamp_value,
            "%Y%m%d%H%M%S",
        ).isoformat(timespec="seconds")
    except ValueError:
        values["run_id_created_at_local"] = pd.NA

    for index, field_name in enumerate(field_schema[1:], start=1):
        parsed_name = f"run_id_{field_name}"
        try:
            values[parsed_name] = int(parts[index])
        except (IndexError, TypeError, ValueError):
            values[parsed_name] = pd.NA

    if "run_id_num_noise_traders" not in values:
        values["run_id_num_noise_traders"] = 0
    if "run_id_num_buy_and_hold_agents" not in values:
        values["run_id_num_buy_and_hold_agents"] = 0

    values["run_id_schema_valid"] = len(parts) in {
        len(RUN_ID_FIELDS),
        len(PRE_BUY_HOLD_RUN_ID_FIELDS),
        len(LEGACY_RUN_ID_FIELDS),
    }
    return values
