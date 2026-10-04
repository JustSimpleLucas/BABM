"""Structural invariants of the repository, checked rather than documented.

`AGENTS.md` and `docs/code_map.md` state how the tree is organised: sources are
registered in the `CMakeLists.txt` next to them, each domain directory names the
target its sources belong to, a `.cpp` sits beside the header it implements, and
a layer includes headers only from the layers it links. Prose cannot fail a
build, so the conventions that a contributor could silently break — most
importantly a new `.cpp` that never reaches `target_sources()` and is therefore
never compiled — are asserted here instead.

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

#: Domains with no `CMakeLists.txt` of their own, mapped to the INTERFACE target
#: they feed. `src/CMakeLists.txt` documents the exception: `Results/` is
#: header-only, so it has no sources to add.
HEADER_ONLY_DOMAIN_TARGETS = {"Results": "abm_results"}

#: `#include "<Domain>/<File>"`, capturing `<Domain>`. Same-directory includes
#: carry no `<Domain>/` prefix and angle-bracket includes are never project code,
#: so neither matches.
CROSS_DIRECTORY_INCLUDE = re.compile(r'^\s*#\s*include\s+"([A-Za-z0-9_]+)/[^"]+"', re.MULTILINE)

#: One `target_link_libraries(<target> ...)` call in the root `CMakeLists.txt`.
TARGET_LINK_LIBRARIES = re.compile(r"target_link_libraries\(\s*(\w+)\s+(.*?)\)", re.DOTALL)


def iter_domain_directories() -> list[Path]:
    """Return every `src/<Domain>/` directory."""

    return sorted(path for path in SOURCE_ROOT.iterdir() if path.is_dir())


def read_declared_sources(domain: Path) -> set[str]:
    """Return the `.cpp` filenames named in a domain's `target_sources()` call."""

    cmake_file = domain / "CMakeLists.txt"
    if not cmake_file.is_file():
        return set()
    return set(re.findall(r"([A-Za-z0-9_]+\.cpp)", cmake_file.read_text(encoding="utf-8")))


def read_domain_targets() -> dict[str, str]:
    """Map every `src/<Domain>/` directory to the CMake target its sources join."""

    targets = dict(HEADER_ONLY_DOMAIN_TARGETS)
    for domain in iter_domain_directories():
        cmake_file = domain / "CMakeLists.txt"
        if not cmake_file.is_file():
            continue
        declaration = re.search(r"target_sources\(\s*(\w+)", cmake_file.read_text(encoding="utf-8"))
        if declaration:
            targets[domain.name] = declaration.group(1)
    return targets


def read_declared_target_links() -> dict[str, set[str]]:
    """Return the `target_link_libraries()` dependencies of each domain target.

    The whole layering is declared in the root `CMakeLists.txt`. Only edges
    between domain targets are kept: `abm_project_includes` and
    `abm_build_metadata` are build plumbing, and `abm_core` is the aggregate that
    the executable and the tests link, not a layer.
    """

    domain_targets = set(read_domain_targets().values())
    links: dict[str, set[str]] = {target: set() for target in domain_targets}
    root_cmake = (REPOSITORY_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    for declaration in TARGET_LINK_LIBRARIES.finditer(root_cmake):
        target, arguments = declaration.groups()
        if target in links:
            linked = set(re.findall(r"\babm_\w+\b", arguments)) & domain_targets
            links[target] |= linked - {target}
    return links


def find_reachable_targets(links: dict[str, set[str]], target: str) -> set[str]:
    """Return every target reachable from `target` through the declared links."""

    reachable: set[str] = set()
    pending = [target]
    while pending:
        for dependency in links.get(pending.pop(), ()):
            if dependency not in reachable:
                reachable.add(dependency)
                pending.append(dependency)
    return reachable


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
    `SimulationConfigSettingAppliers.h` is split into a dispatcher and five
    `SimulationConfigSettingAppliers*.cpp` section files, each grouping one part
    of the config schema — while still keeping every source traceable to a
    declaration.
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


def test_declared_target_links_are_acyclic() -> None:
    """CMake accepts cycles between static libraries, so nothing else forbids them.

    Root `CMakeLists.txt`, above `abm_add_domain_library()`: nothing in a lower
    layer may link a higher one. A cycle would make "lower" and "higher"
    meaningless for every target on it.
    """

    links = read_declared_target_links()
    cycles: list[list[str]] = []
    finished: set[str] = set()
    path: list[str] = []

    def visit(target: str) -> None:
        if target in path:
            cycles.append(path[path.index(target) :] + [target])
            return
        if target in finished:
            return
        path.append(target)
        for dependency in sorted(links[target]):
            visit(dependency)
        path.pop()
        finished.add(target)

    for target in sorted(links):
        visit(target)

    assert not cycles, "Declared target_link_libraries() edges form a cycle: " + "; ".join(
        " -> ".join(cycle) for cycle in cycles
    )


def test_every_cross_directory_include_follows_a_declared_link() -> None:
    """A layer may include headers only from the layers it links.

    Root `CMakeLists.txt`, above `abm_add_domain_library()`: the declared
    `target_link_libraries()` edges are the whole architecture. Every target
    still gets `src/` on its include path through `abm_project_includes`, so the
    compiler accepts an include of any header whether or not the target links the
    library behind it. Without this check a layering violation compiles cleanly
    and only surfaces as a link error — or, on macOS, where static-library order
    does not matter and CI runs, not at all.

    A link declared `PRIVATE` counts: a `.cpp` may include the headers of a
    library it links privately.
    """

    domain_targets = read_domain_targets()
    unmapped = [
        domain.name for domain in iter_domain_directories() if domain.name not in domain_targets
    ]
    assert not unmapped, (
        "These domain directories belong to no CMake target, so their includes cannot be "
        f"checked: {unmapped}. Header-only domains are listed in HEADER_ONLY_DOMAIN_TARGETS."
    )

    links = read_declared_target_links()
    violations: list[str] = []
    for domain in iter_domain_directories():
        own_target = domain_targets[domain.name]
        permitted = {own_target} | find_reachable_targets(links, own_target)
        for source in sorted([*domain.glob("*.h"), *domain.glob("*.cpp")]):
            text = source.read_text(encoding="utf-8")
            for included_domain in sorted(set(CROSS_DIRECTORY_INCLUDE.findall(text))):
                included_target = domain_targets.get(included_domain)
                if included_target is not None and included_target not in permitted:
                    violations.append(
                        f"{source.relative_to(REPOSITORY_ROOT)} includes {included_domain}/ "
                        f"({included_target}), which {own_target} does not link"
                    )

    assert not violations, (
        "These includes reach into a layer the including target does not link. Declare the "
        "dependency in the root CMakeLists.txt if it is intended, otherwise move the code: "
        f"{violations}"
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
