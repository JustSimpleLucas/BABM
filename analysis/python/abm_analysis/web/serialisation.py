"""Conversion of pandas and NumPy values into JSON-safe Python primitives.

The analysis layer works in pandas, so missing values arrive as ``NaN``,
``pd.NA`` or ``NaT`` and numbers arrive as NumPy scalars. None of those survive
``json.dumps``. Every value leaving the web API passes through here so the
browser receives ``null`` for "not available" rather than a server error or the
string ``"NaN"``, which JavaScript would silently render as text.
"""

from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def json_safe(value: Any) -> Any:
    """Recursively convert one value into JSON-serialisable primitives.

    Non-finite floats (``NaN``, ``±inf``) become ``None``: a diagnostic that
    could not be computed must read as absent in the interface, never as a
    number the reader might quote.
    """

    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (str, bool)):
        return value
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if isfinite(number) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, np.ndarray, pd.Series)):
        return [json_safe(item) for item in value]
    if pd.isna(value):
        return None
    return str(value)


def numeric_or_none(value: Any) -> float | None:
    """Return ``value`` as a finite float, or ``None`` when it is not usable."""

    number = pd.to_numeric(value, errors="coerce")
    if number is None or pd.isna(number):
        return None
    number = float(number)
    return number if isfinite(number) else None
