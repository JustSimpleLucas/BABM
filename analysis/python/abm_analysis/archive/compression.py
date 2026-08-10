"""In-place gzip compression for completed file-based run archives.

Completed simulation runs are dominated by three per-row CSV artefacts
(``step_timeseries.csv``, ``trade_ledger.csv``, ``agents_final.csv``). Fixed
decimal formatting makes them highly compressible (typically 5-10x), and both
pandas and the archive discovery layer read ``*.csv.gz`` transparently, so
compression trades no analysis capability for a large storage saving.

Small human-readable artefacts (``summary_metrics.csv``, ``stylised_facts.csv``,
``config.json``, ``metadata.json``, ``config_used.cfg``) are deliberately left
uncompressed so a run archive can still be audited with a plain text editor.
"""

from __future__ import annotations

from dataclasses import dataclass
import gzip
from pathlib import Path
import shutil

from abm_analysis.archive.archives import discover_run_directories, resolve_artifact_path


# Per-row artefacts worth compressing. Order matters only for reporting.
COMPRESSIBLE_RUN_ARTIFACTS = (
    "step_timeseries.csv",
    "trade_ledger.csv",
    "agents_final.csv",
    "mechanism_diagnostics.csv",
    "agent_step_diagnostics.csv",
)


@dataclass(frozen=True)
class CompressionResult:
    """Outcome of compressing one artefact inside one run archive."""

    run_dir: Path
    filename: str
    original_bytes: int
    compressed_bytes: int


def compress_run_archive(run_dir: Path | str) -> list[CompressionResult]:
    """Gzip the large CSV artefacts of one completed run archive in place.

    Each plain CSV is rewritten as ``<name>.csv.gz`` and the original file is
    removed only after the compressed copy has been written completely, so an
    interrupted compression never loses data. Artefacts that are already
    compressed or absent are skipped.
    """

    run_path = Path(run_dir).expanduser().resolve()
    if resolve_artifact_path(run_path, "step_timeseries.csv") is None:
        raise FileNotFoundError(
            f"Not a run archive (missing step_timeseries.csv): {run_path}"
        )

    results: list[CompressionResult] = []
    for filename in COMPRESSIBLE_RUN_ARTIFACTS:
        source = run_path / filename
        if not source.is_file():
            continue
        destination = run_path / (filename + ".gz")
        # mtime=0 keeps the gzip container byte-identical for identical CSV
        # content, which preserves reproducible provenance hashing.
        with source.open("rb") as plain_handle:
            with destination.open("wb") as raw_handle:
                with gzip.GzipFile(
                    fileobj=raw_handle, mode="wb", filename="", mtime=0
                ) as gzip_handle:
                    shutil.copyfileobj(plain_handle, gzip_handle)
        original_bytes = source.stat().st_size
        compressed_bytes = destination.stat().st_size
        source.unlink()
        results.append(
            CompressionResult(
                run_dir=run_path,
                filename=filename,
                original_bytes=original_bytes,
                compressed_bytes=compressed_bytes,
            )
        )
    return results


def compress_experiment_archives(experiment_dir: Path | str) -> list[CompressionResult]:
    """Compress every run archive under one experiment directory."""

    results: list[CompressionResult] = []
    for run_dir in discover_run_directories(experiment_dir):
        results.extend(compress_run_archive(run_dir))
    return results
