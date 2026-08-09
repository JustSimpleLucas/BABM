"""Argument parser construction for the ABM analysis command-line interface."""

from __future__ import annotations

import argparse


from .cli_arguments import (
    add_benchmark_arguments,
    add_calibration_benchmark_arguments,
    add_database_arguments,
    add_source_arguments,
)
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


# Legacy underscore aliases kept for callers that import the private names.
_build_parser = build_parser
_add_benchmark_arguments = add_benchmark_arguments
_add_calibration_benchmark_arguments = add_calibration_benchmark_arguments
_add_database_arguments = add_database_arguments
_add_source_arguments = add_source_arguments
