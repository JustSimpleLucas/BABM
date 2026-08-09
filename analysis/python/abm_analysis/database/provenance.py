"""Hashing and provenance helpers for reproducible imports."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import subprocess
from typing import Iterable

from .constants import IMPORTER_PACKAGE_NAME, STAGING_ARTIFACTS, UNKNOWN_IMPORTER_VERSION

def _hash_run_archive(run_path: Path) -> str:
    """Hash portable staging artefacts by relative filename and file contents.

    Both the plain and gzip-compressed form of each artefact participate, so a
    compressed archive still produces a stable provenance hash after import.
    """

    archive_path = run_path.expanduser().resolve()
    candidates = []
    for filename in STAGING_ARTIFACTS:
        candidates.append(archive_path / filename)
        candidates.append(archive_path / (filename + ".gz"))
    candidates.append(archive_path / "logs" / "run.log")
    return _hash_existing_files(archive_path, candidates)

def _hash_existing_files(reference_dir: Path, paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted({candidate for candidate in paths if candidate.is_file()}):
        relative_name = path.relative_to(reference_dir).as_posix()
        digest.update(relative_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()

def _file_sha256(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()

def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]

def _importer_version() -> str:
    try:
        return version(IMPORTER_PACKAGE_NAME)
    except PackageNotFoundError:
        return UNKNOWN_IMPORTER_VERSION

def _current_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repository_root(),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None
