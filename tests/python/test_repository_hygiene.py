"""Structural invariants of the repository, checked rather than documented.

`AGENTS.md` and `docs/code_map.md` state how the tree is organised: sources are
registered in the `CMakeLists.txt` next to them, each domain directory names the
target its sources belong to, and a `.cpp` sits beside the header it implements.
Prose cannot fail a build, so the conventions that a contributor could silently
break — most importantly a new `.cpp` that never reaches `target_sources()` and
is therefore never compiled — are asserted here instead.

Each assertion names the rule and where it is documented, so a failure tells the
reader what to do, not only what broke.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"

#: Directories that never hold project code, skipped when walking the tree.
IGNORED_DIRECTORY_NAMES = {".venv", "__pycache__", ".pytest_cache", ".git", "build"}


def iter_domain_directories() -> list[Path]:
    """Return every `src/<Domain>/` directory."""

    return sorted(path for path in SOURCE_ROOT.iterdir() if path.is_dir())


def read_declared_sources(domain: Path) -> set[str]:
    """Return the `.cpp` filenames named in a domain's `target_sources()` call."""

    cmake_file = domain / "CMakeLists.txt"
    if not cmake_file.is_file():
        return set()
    return set(re.findall(r"([A-Za-z0-9_]+\.cpp)", cmake_file.read_text(encoding="utf-8")))


def test_r_analysis_files_have_been_removed() -> None:
    """The R prototype was replaced by the Python analysis package."""

    analysis_dir = REPOSITORY_ROOT / "analysis"
    r_files = [
        path
        for path in analysis_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".r", ".rproj"}
        and not any(part in IGNORED_DIRECTORY_NAMES for part in path.parts)
    ]

    assert r_files == []
    assert not (REPOSITORY_ROOT / "rStudio_workspace").exists()


def test_every_source_is_registered_in_its_directory_cmakelists() -> None:
    """A `.cpp` missing from `target_sources()` is silently never compiled.

    AGENTS.md, "C++ module and documentation workflow": when adding a `.cpp`
    under `src/<Domain>/`, add it to the `target_sources()` call in that
    directory's own `CMakeLists.txt`.
    """

    unregistered: list[str] = []
    for domain in iter_domain_directories():
        declared = read_declared_sources(domain)
        for source in sorted(domain.glob("*.cpp")):
            if source.name not in declared:
                unregistered.append(f"{source.relative_to(REPOSITORY_ROOT)}")

    assert not unregistered, (
        "These sources are not named in their directory's CMakeLists.txt and so "
        f"are never compiled: {unregistered}"
    )


def test_every_domain_with_sources_declares_a_cmakelists() -> None:
    """Header-only domains are the documented exception.

    `src/CMakeLists.txt` explains it: `Results/` is header-only and contributes
    to an INTERFACE target, so it has no sources to add and needs no
    `CMakeLists.txt`. Any directory that does hold a `.cpp` must have one.
    """

    missing = [
        str(domain.relative_to(REPOSITORY_ROOT))
        for domain in iter_domain_directories()
        if any(domain.glob("*.cpp")) and not (domain / "CMakeLists.txt").is_file()
    ]

    assert not missing, f"Domain directories with sources but no CMakeLists.txt: {missing}"


def test_every_domain_cmakelists_is_added_from_the_source_cmakelists() -> None:
    """A domain directory that is never `add_subdirectory`'d is dead weight."""

    listed = set(
        re.findall(
            r"add_subdirectory\(([A-Za-z0-9_]+)\)",
            (SOURCE_ROOT / "CMakeLists.txt").read_text(encoding="utf-8"),
        )
    )
    unwired = [
        domain.name
        for domain in iter_domain_directories()
        if (domain / "CMakeLists.txt").is_file() and domain.name not in listed
    ]

    assert not unwired, f"Domain directories not added from src/CMakeLists.txt: {unwired}"


def test_every_source_sits_beside_the_header_it_implements() -> None:
    """A source's name must begin with the stem of a header in its own directory.

    Usually that means the exact pair `Foo.cpp`/`Foo.h`. The looser prefix rule
    is what lets one header be implemented across several translation units —
    `SimulationConfigSettingAppliers.h` is split into the four
    `SimulationConfigSettingAppliers*.cpp` files, each grouping one part of the
    config schema — while still keeping every source traceable to a declaration.
    """

    orphans: list[str] = []
    for domain in iter_domain_directories():
        header_stems = sorted((header.stem for header in domain.glob("*.h")), key=len, reverse=True)
        for source in sorted(domain.glob("*.cpp")):
            if not any(source.stem.startswith(stem) for stem in header_stems):
                orphans.append(str(source.relative_to(REPOSITORY_ROOT)))

    assert not orphans, (
        "These sources do not share a prefix with any header in their directory, "
        f"so the declaration they implement cannot be found by name: {orphans}"
    )


def test_no_packaging_metadata_is_tracked() -> None:
    """`*.egg-info/` is regenerated by every editable install and must stay untracked."""

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    packaging_metadata = [path for path in tracked if ".egg-info/" in path]

    assert not packaging_metadata, (
        "Packaging metadata is tracked and will churn on every `pip install -e .`: "
        f"{packaging_metadata}"
    )
