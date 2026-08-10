"""Command-line entry point for Python-only ABM experiment analysis.

Each subcommand owns its parser and handler in ``abm_analysis.commands``; this
module only builds the top-level parser and dispatches to the handler the
selected subcommand registered.
"""

from __future__ import annotations

from .cli_parser import build_parser

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the selected command handler."""

    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
