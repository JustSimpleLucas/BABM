"""Archive discovery and validation for file-backed ABM simulation runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from .run_ids import LEGACY_RUN_ID_FIELDS, PRE_BUY_HOLD_RUN_ID_FIELDS, parse_run_id


REQUIRED_STEP_TIMESERIES_COLUMNS = {
    "row_index",
    "phase",
    "simulation_step",
    "market_price",
    "fundamental_price",
    "submitted_orders",
    "net_demand",
    "traded_volume",
    "raw_return",
    "log_return",
}

REQUIRED_SUMMARY_METRICS_COLUMNS = {
    "run_id",
    "seed",
    "time_steps",
    "num_fundamentalists",
    "num_chartists",
    "num_buy_and_hold_agents",
    "num_noise_traders",
    "final_market_price",
    "mean_log_return",
    "log_return_std_dev",
    "excess_kurtosis",
}

REQUIRED_AGENT_FINAL_COLUMNS = {
    "agent_id",
    "initial_strategy_type",
    "current_strategy_type",
    "final_cash",
    "final_stock",
    "number_of_trades",
    "traded_volume",
    "final_wealth",
}

REQUIRED_TRADE_LEDGER_COLUMNS = {
    "trade_id",
    "time",
    "agent_id",
    "counterparty_agent_id",
    "side",
    "price",
    "qty",
    "asset",
}

REQUIRED_ASSET_TIMESERIES_COLUMNS = {
    "row_index",
    "phase",
    "simulation_step",
    "asset",
    "market_price",
    "fundamental_price",
    "raw_return",
    "log_return",
    "traded_volume",
}

# Completed archives may be gzip-compressed in place to reduce long-term
# storage cost. pandas reads ``*.csv.gz`` transparently, so every consumer
# resolves artefacts through :func:`resolve_artifact_path` instead of
# assuming a plain-text file.
COMPRESSED_ARTIFACT_SUFFIX = ".gz"


def resolve_artifact_path(run_dir: Path | str, filename: str) -> Path | None:
    """Return the plain or gzip-compressed path for one archive artefact.

    The plain file wins when both forms exist so that a freshly re-run
    simulation always takes precedence over a stale compressed copy.
    """

    run_path = Path(run_dir)
    candidate = run_path / filename
    if candidate.is_file():
        return candidate
    compressed = run_path / (filename + COMPRESSED_ARTIFACT_SUFFIX)
    if compressed.is_file():
        return compressed
    return None


@dataclass(frozen=True)
class RunArchive:
    """File locations for one archived simulation run."""

    run_id: str
    run_dir: Path
    step_timeseries_csv: Path
    summary_metrics_csv: Path | None
    agents_final_csv: Path | None
    trade_ledger_csv: Path | None
    metadata_json: Path | None
    asset_timeseries_csv: Path | None = None


@dataclass(frozen=True)
class ArchiveValidationResult:
    """Schema validation result for one file-based simulation archive."""

    run_id: str
    run_dir: Path
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        """Return ``True`` when no archive-level validation errors were found."""

        return not self.errors


def discover_run_directories(experiment_dir: Path | str) -> list[Path]:
    """Return archived run directories that contain ``step_timeseries.csv``."""

    experiment_path = Path(experiment_dir).expanduser().resolve()
    if not experiment_path.exists():
        raise FileNotFoundError(f"Experiment directory does not exist: {experiment_path}")
    if not experiment_path.is_dir():
        raise NotADirectoryError(f"Experiment path is not a directory: {experiment_path}")

    run_dirs = [
        path
        for path in experiment_path.iterdir()
        if path.is_dir() and resolve_artifact_path(path, "step_timeseries.csv") is not None
    ]
    return sorted(run_dirs, key=lambda path: path.name)


def build_run_archive(run_dir: Path | str) -> RunArchive:
    """Build a portable description of one run archive."""

    run_path = Path(run_dir).expanduser().resolve()
    step_timeseries_path = resolve_artifact_path(run_path, "step_timeseries.csv")
    if step_timeseries_path is None:
        raise FileNotFoundError(f"Run is missing step_timeseries.csv: {run_path}")

    return RunArchive(
        run_id=run_path.name,
        run_dir=run_path,
        step_timeseries_csv=step_timeseries_path,
        summary_metrics_csv=resolve_artifact_path(run_path, "summary_metrics.csv"),
        agents_final_csv=resolve_artifact_path(run_path, "agents_final.csv"),
        trade_ledger_csv=resolve_artifact_path(run_path, "trade_ledger.csv"),
        metadata_json=resolve_artifact_path(run_path, "metadata.json"),
        asset_timeseries_csv=resolve_artifact_path(run_path, "asset_timeseries.csv"),
    )


def validate_run_archive(run_dir: Path | str) -> ArchiveValidationResult:
    """Validate the file-based schema for one archived simulation run.

    The analysis workflow remains tolerant of partial historical archives, so
    this helper reports structured errors and warnings instead of raising during
    normal discovery. A current thesis-grade archive should have no errors; a
    legacy archive can still be loaded when the missing fields are not required
    for the requested diagnostic.
    """

    run_path = Path(run_dir).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not run_path.exists():
        return ArchiveValidationResult(
            run_id=run_path.name,
            run_dir=run_path,
            errors=(f"Run archive directory does not exist: {run_path}",),
            warnings=(),
        )
    if not run_path.is_dir():
        return ArchiveValidationResult(
            run_id=run_path.name,
            run_dir=run_path,
            errors=(f"Run archive path is not a directory: {run_path}",),
            warnings=(),
        )

    parsed_run_id = parse_run_id(run_path.name)
    if not parsed_run_id["run_id_schema_valid"]:
        errors.append(
            "Run directory name does not follow the required numeric run-id schema: "
            f"{run_path.name}"
        )
    elif len(run_path.name.split("_")) == len(LEGACY_RUN_ID_FIELDS):
        warnings.append(
            "Run directory uses the legacy run-id schema without num_noise_traders "
            "or num_buy_and_hold_agents; analysis will treat both counts as zero."
        )
    elif len(run_path.name.split("_")) == len(PRE_BUY_HOLD_RUN_ID_FIELDS):
        warnings.append(
            "Run directory uses the pre-buy-and-hold run-id schema; analysis will treat "
            "buy-and-hold agents as zero."
        )

    step_timeseries_path = resolve_artifact_path(run_path, "step_timeseries.csv")
    if step_timeseries_path is None:
        errors.append("Missing required step_timeseries.csv.")
    else:
        errors.extend(
            _missing_column_messages(
                step_timeseries_path,
                REQUIRED_STEP_TIMESERIES_COLUMNS,
                "step_timeseries.csv",
            )
        )

    summary_metrics_path = resolve_artifact_path(run_path, "summary_metrics.csv")
    if summary_metrics_path is not None:
        warnings.extend(
            _missing_column_messages(
                summary_metrics_path,
                REQUIRED_SUMMARY_METRICS_COLUMNS,
                "summary_metrics.csv",
            )
        )
    else:
        warnings.append(
            "Missing recommended summary_metrics.csv; run indexing will use run_id only."
        )

    agents_path = resolve_artifact_path(run_path, "agents_final.csv")
    if agents_path is not None:
        warnings.extend(
            _missing_column_messages(
                agents_path,
                REQUIRED_AGENT_FINAL_COLUMNS,
                "agents_final.csv",
            )
        )
    else:
        warnings.append(
            "Missing recommended agents_final.csv; agent-level panels will be unavailable."
        )

    metadata_path = resolve_artifact_path(run_path, "metadata.json")
    trade_ledger_path = resolve_artifact_path(run_path, "trade_ledger.csv")
    trade_ledger_expected = False
    asset_timeseries_expected = False
    if metadata_path is not None:
        metadata_warnings, trade_ledger_expected = _read_output_flag(
            metadata_path, "trade_ledger_enabled"
        )
        warnings.extend(metadata_warnings)
        _, asset_timeseries_expected = _read_output_flag(
            metadata_path, "asset_timeseries_enabled"
        )
    else:
        warnings.append("Missing recommended metadata.json; provenance checks will be unavailable.")

    if trade_ledger_path is not None:
        warnings.extend(
            _missing_column_messages(
                trade_ledger_path,
                REQUIRED_TRADE_LEDGER_COLUMNS,
                "trade_ledger.csv",
            )
        )
    elif trade_ledger_expected:
        errors.append(
            "metadata.json declares trade_ledger_enabled=true but trade_ledger.csv is missing."
        )

    asset_timeseries_path = resolve_artifact_path(run_path, "asset_timeseries.csv")
    if asset_timeseries_path is not None:
        warnings.extend(
            _missing_column_messages(
                asset_timeseries_path,
                REQUIRED_ASSET_TIMESERIES_COLUMNS,
                "asset_timeseries.csv",
            )
        )
    elif asset_timeseries_expected:
        errors.append(
            "metadata.json declares asset_timeseries_enabled=true but asset_timeseries.csv "
            "is missing."
        )
    else:
        warnings.append(
            "Missing asset_timeseries.csv; per-asset panels will be unavailable "
            "(expected for archives created before the multi-asset extension)."
        )

    return ArchiveValidationResult(
        run_id=run_path.name,
        run_dir=run_path,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def ensure_valid_run_archive(run_dir: Path | str) -> RunArchive:
    """Validate one archive and return its file locations, raising on errors."""

    validation = validate_run_archive(run_dir)
    if not validation.is_valid:
        joined_errors = "; ".join(validation.errors)
        raise ValueError(f"Invalid run archive {validation.run_id}: {joined_errors}")
    return build_run_archive(validation.run_dir)


def _missing_column_messages(
    path: Path,
    required_columns: set[str],
    artifact_name: str,
) -> list[str]:
    try:
        columns = set(pd.read_csv(path, nrows=0).columns)
    # pandas raises these for missing/unreadable files or malformed CSV headers;
    # anything else indicates a real bug and should propagate.
    except (
        OSError,
        UnicodeDecodeError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
    ) as error:  # pragma: no cover - pandas parser messages vary by version.
        return [f"Unable to read {artifact_name}: {error}"]

    missing_columns = sorted(required_columns.difference(columns))
    if not missing_columns:
        return []
    missing_text = ", ".join(missing_columns)
    return [f"{artifact_name} is missing required columns: {missing_text}"]


def _read_output_flag(metadata_path: Path, flag_name: str) -> tuple[list[str], bool]:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return ([f"Unable to read metadata.json for output-flag validation: {error}"], False)

    outputs = metadata.get("outputs", {})
    if not isinstance(outputs, dict):
        return (["metadata.json outputs field is not an object."], False)
    return ([], bool(outputs.get(flag_name, False)))
