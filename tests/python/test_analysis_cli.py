"""Wiring checks for the command-line interface.

Every subcommand's parser and handler live in their own module and are pulled
together by ``commands.build_parser``. A command that registers its parser but
forgets its handler parses fine and then crashes on dispatch, so the wiring is
asserted here rather than left to whichever end-to-end test happens to run it.
"""

from __future__ import annotations

import pytest

from abm_analysis.commands import COMMAND_MODULES, build_parser


#: Subcommands the parser must expose. The dashboard is the entry point a reader
#: starts from, so it is registered first and listed first in ``--help``.
EXPECTED_COMMANDS = (
    "web",
    "replicate",
    "calibrate",
    "compress",
    "convert-benchmarks",
    "db",
)


def test_every_registered_command_is_reachable() -> None:
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action.choices, dict)
    )

    assert tuple(subparsers.choices) == EXPECTED_COMMANDS
    assert len(COMMAND_MODULES) == len(EXPECTED_COMMANDS)


@pytest.mark.parametrize("command", EXPECTED_COMMANDS)
def test_every_command_binds_a_handler(command: str) -> None:
    """A command must dispatch to something; ``--help`` alone proves nothing."""

    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action.choices, dict)
    )
    defaults = subparsers.choices[command].get_default("handler")

    # ``db`` dispatches through its own subcommand level, so the handler is
    # bound one layer down rather than on the group parser.
    if defaults is None:
        nested = next(
            action
            for action in subparsers.choices[command]._actions
            if isinstance(action.choices, dict)
        )
        assert nested.choices
        assert all(
            nested.choices[name].get_default("handler") is not None
            for name in nested.choices
        )
        return

    assert callable(defaults)


def test_parser_requires_a_command() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])
