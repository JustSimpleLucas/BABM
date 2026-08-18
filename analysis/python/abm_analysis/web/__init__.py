"""Local web application for browsing archived runs and their market statistics.

This is how the project's results are read: a local server that lists every
archived run and, for the one selected, shows the market, agent and protagonist
statistics that the stylised-facts question turns on. The citable artefacts
themselves are the CSV tables ``abm_analysis.exports`` writes beside each
experiment; this package renders, and never replaces, them.

Nothing here simulates and nothing here writes to the archive. The application
is a read-only view over ``data/``, so it can never alter the provenance of a
run, and every number it displays is recomputed with the same functions the
exported tables use (``abm_analysis.statistics``).
"""

from __future__ import annotations

from abm_analysis.web.app import create_app, serve

__all__ = ["create_app", "serve"]
