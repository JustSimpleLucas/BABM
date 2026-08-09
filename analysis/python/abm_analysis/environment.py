"""Local environment setup for reproducible analysis runs."""

from __future__ import annotations

import os
from pathlib import Path


def configure_analysis_environment() -> None:
    """Route library caches to a writable project-local directory.

    Some econometrics/plotting dependencies import Matplotlib internally. On a
    locked-down Mac user profile, Matplotlib can warn or slow down while trying
    to write its default cache under the home directory. A project-local cache
    keeps command-line runs reproducible and avoids machine-specific setup.
    """

    if "MPLCONFIGDIR" in os.environ:
        return
    cache_dir = Path.cwd() / ".cache" / "matplotlib"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache_dir)
