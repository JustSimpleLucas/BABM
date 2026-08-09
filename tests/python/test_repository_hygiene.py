from __future__ import annotations

from pathlib import Path


def test_r_analysis_files_have_been_removed() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    analysis_dir = repository_root / "analysis"
    r_files = [
        path
        for path in analysis_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".r", ".rproj"}
    ]

    assert r_files == []
    assert not (repository_root / "rStudio_workspace").exists()
