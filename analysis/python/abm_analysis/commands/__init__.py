"""One module per CLI command, each pairing its parser with its handler.

The parser used to build every subcommand in a single function while the
handlers lived in another file hundreds of lines away, so adding an option
meant editing two distant places and nothing tied them together. Each module
here exposes ``register(subparsers)``, which adds the command's parser, its
arguments, and the handler it dispatches to.
"""

from __future__ import annotations

from . import calibrate, compare, compress, db, replicate, robustness, run, web

#: Registration order fixes the order subcommands appear in ``--help``.
COMMAND_MODULES = (run, compare, replicate, robustness, compress, calibrate, db, web)

__all__ = ["COMMAND_MODULES"]
