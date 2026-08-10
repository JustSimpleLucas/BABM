"""Argument parser construction for the ABM analysis command-line interface."""

from __future__ import annotations

import argparse

from .commands import COMMAND_MODULES


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser for all analysis subcommands."""

    parser = argparse.ArgumentParser(
        prog="python -m abm_analysis",
        description=(
            "Generate Python-only diagnostics and static Plotly HTML reports "
            "for behavioural-finance ABM experiment outputs."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMAND_MODULES:
        command.register(subparsers)
    return parser
