"""Local web application for browsing archived runs and their market statistics.

The command-line reports remain the authoritative, citable artefacts: they are
written to disk, versioned alongside the run they describe, and exported as
publication figures. This package adds a lighter way in for day-to-day research
work — a local server that lists every archived run and, for the one selected,
shows the market statistics that matter for the stylised-facts question without
regenerating a report first.

Nothing here simulates and nothing here writes to the archive. The application
is a read-only view over ``data/``, so it can never alter the provenance of a
run, and every number it displays is recomputed with the same functions the
static reports use (``abm_analysis.statistics.diagnostics``).
"""

from __future__ import annotations

from abm_analysis.web.app import create_app, serve

__all__ = ["create_app", "serve"]
