"""Archive-compression command: parser and handler."""

from __future__ import annotations

import argparse
from pathlib import Path
from abm_analysis.compression import compress_experiment_archives, compress_run_archive
from abm_analysis.data import resolve_artifact_path


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``compress`` command."""

    compress_parser = subparsers.add_parser(
        "compress",
        help=(
            "Gzip the large per-row CSV artefacts of archived runs in place. "
            "Analysis and database import read *.csv.gz transparently."
        ),
    )
    compress_parser.add_argument(
        "target",
        type=Path,
        help=(
            "Path to one archived run directory, or to one "
            "data/experiments/<experiment_name> directory to compress every run."
        ),
    )
    compress_parser.set_defaults(handler=handle_compress)


def handle_compress(args: argparse.Namespace) -> int:
    """Gzip large archived CSVs in place and report the storage saving."""

    target = Path(args.target)
    if resolve_artifact_path(target, "step_timeseries.csv") is not None:
        results = compress_run_archive(target)
    else:
        results = compress_experiment_archives(target)

    if not results:
        print("No plain CSV artefacts found to compress.")
        return 0

    for result in results:
        print(
            f"{result.run_dir.name}/{result.filename}: "
            f"{result.original_bytes:,} -> {result.compressed_bytes:,} bytes"
        )
    total_before = sum(result.original_bytes for result in results)
    total_after = sum(result.compressed_bytes for result in results)
    print(
        f"Compressed {len(results)} artefacts: {total_before:,} -> {total_after:,} bytes "
        f"({total_before - total_after:,} saved)."
    )
    return 0
