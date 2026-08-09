"""Normalisation helpers for portable metadata and SQL values."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from .constants import (
    BOOLEAN_TABLE_COLUMNS,
    COUNT_TABLE_COLUMNS,
    JSONB_TABLE_COLUMNS,
    PATH_LIKE_CONFIG_KEYS,
    PATH_LIKE_METADATA_KEYS,
)

def sanitize_metadata_for_database(value: Any) -> Any:
    """Remove path-like metadata fields before storing provenance in SQL."""

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if _is_path_like_metadata_key(str(key)):
                continue
            sanitized[str(key)] = sanitize_metadata_for_database(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_metadata_for_database(item) for item in value]
    return value

def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _coerce_json_value(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value

def _sanitize_config_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    sanitized_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            sanitized_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in PATH_LIKE_CONFIG_KEYS:
            continue
        sanitized_lines.append(line)
    return "\n".join(sanitized_lines) + "\n"

def _is_path_like_metadata_key(key: str) -> bool:
    return key in PATH_LIKE_METADATA_KEYS or key.endswith("_path")

def _first_text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        text = str(value)
        if text and text != "<NA>":
            return text
    return ""

def _normalise_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalise_sql_value(value) for key, value in record.items()}

def _normalise_table_record(table_name: str, record: dict[str, Any]) -> dict[str, Any]:
    normalised = _normalise_record(record)
    for column in BOOLEAN_TABLE_COLUMNS.get(table_name, set()):
        if column in normalised:
            normalised[column] = _coerce_optional_bool(normalised[column])
    for column in COUNT_TABLE_COLUMNS.get(table_name, set()):
        if column in normalised:
            normalised[column] = _coerce_optional_count(normalised[column])
    return normalised

def _normalise_sql_value(value: Any) -> Any:
    if value is pd.NA:
        return None
    if not isinstance(value, (dict, list, tuple, set)):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.date().isoformat()
    if hasattr(value, "item"):
        return _normalise_sql_value(value.item())
    return value

def _coerce_optional_count(value: Any) -> int | None:
    """Coerce an integer count that pandas may have promoted to float.

    Missing values stay ``None``; genuine integers pass through; whole floats
    such as ``12.0`` (a side effect of NaN-padded CSV columns) are restored to
    exact integers before insertion into BIGINT columns.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return int(round(number))


def _coerce_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "1.0", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "0.0", "false", "f", "no", "n"}:
        return False
    try:
        return float(text) != 0.0
    except ValueError:
        return None

def _json_safe_record(record: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _normalise_json_value(value) for key, value in record.items()}

def _normalise_json_value(value: Any) -> Any:
    value = _normalise_sql_value(value)
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

def _normalise_selected_benchmark_ids(
    benchmark_series: str | list[str] | tuple[str, ...] | None,
) -> set[str] | None:
    if benchmark_series is None:
        return None
    if isinstance(benchmark_series, str):
        values = benchmark_series.split(",")
    else:
        values = list(benchmark_series)
    selected = {str(value).strip().upper() for value in values if str(value).strip()}
    return selected or None
