"""The command-line interface: one module per subcommand, plus the parser.

The parser used to build every subcommand in a single function while the
handlers lived in another file hundreds of lines away, so adding an option
meant editing two distant places and nothing tied them together. Each command
module here exposes ``register(subparsers)``, which adds the command's parser,
its arguments, and the handler it dispatches to.

Everything CLI-shaped lives in this package: the command modules, the option
groups they share (``shared_arguments``), the helpers their handlers share
(``shared_helpers``), and ``build_parser`` below. Only ``abm_analysis.cli``
sits outside it, because it is the entry point named in ``pyproject.toml``.
"""

from __future__ import annotations

import argparse

from . import calibrate, compress, convert_benchmarks, db, replicate, web

#: Registration order fixes the order subcommands appear in ``--help``.
COMMAND_MODULES = (
    web,
    replicate,
    calibrate,
    compress,
    convert_benchmarks,
    db,
)

__all__ = ["COMMAND_MODULES", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser for all analysis subcommands."""

    parser = argparse.ArgumentParser(
        prog="python -m abm_analysis",
        description=(
            "Browse, replicate and calibrate behavioural-finance ABM experiment "
            "outputs. Start with 'web' to explore an archive."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMAND_MODULES:
        command.register(subparsers)
    return parser
