"""Small data-transfer objects used by database workflows."""

from __future__ import annotations

from dataclasses import dataclass

class ImportSummary:
    """Summary of one database import action."""

    item_type: str
    identifier: str
    rows_imported: int
