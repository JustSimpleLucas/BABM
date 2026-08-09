"""Race-free discovery of the run directory created by one simulator process.

The simulator names its own run folder, so the harness has to find it after
the subprocess exits. Diffing the experiment directory before/after the run
and taking the highest-sorted new name mis-attributes runs as soon as seeds
execute concurrently. The primary mechanism here instead parses the
``Experiment run directory: <path>`` line the simulator prints on stdout;
the directory diff remains only as a fallback (test doubles do not emit the
line) and is filtered to the requesting seed so it stays correct when
sibling runs finish in between the snapshots.
"""

from __future__ import annotations

from pathlib import Path

from abm_analysis.data import discover_run_directories, resolve_artifact_path


RUN_DIRECTORY_STDOUT_PREFIX = "Experiment run directory: "


def parse_run_directory_from_stdout(
    stdout: str,
    *,
    experiment_dir: Path,
    cwd: Path | None,
    seed: int,
) -> Path | None:
    """Extract and validate the run directory the simulator printed on stdout.

    Returns ``None`` (caller falls back to the directory diff) unless the
    printed path is an existing directory directly under ``experiment_dir``,
    its run-id ends with the requesting seed, and it contains a usable
    ``step_timeseries.csv`` archive.
    """

    # The progress bar redraws with carriage returns, so the run-directory
    # line may share a captured buffer chunk with \r-separated frames.
    lines = [segment.strip() for line in stdout.split("\n") for segment in line.split("\r")]
    prefixed = [line for line in lines if line.startswith(RUN_DIRECTORY_STDOUT_PREFIX)]
    if not prefixed:
        return None
    raw_path = prefixed[-1][len(RUN_DIRECTORY_STDOUT_PREFIX) :].strip()
    if not raw_path:
        return None

    path = Path(raw_path)
    if not path.is_absolute():
        if cwd is None:
            return None
        path = cwd / path
    try:
        path = path.resolve()
        expected_parent = experiment_dir.expanduser().resolve()
    except OSError:
        return None
    if path.parent != expected_parent:
        return None
    if not _matches_seed(path.name, seed):
        return None
    if not path.is_dir():
        return None
    if resolve_artifact_path(path, "step_timeseries.csv") is None:
        return None
    return path


def run_directory_names(experiment_dir: Path) -> set[str]:
    """Return the names of run directories under an experiment directory, or an empty set if it does not exist yet."""

    if not experiment_dir.is_dir():
        return set()
    return {path.name for path in discover_run_directories(experiment_dir)}


def discover_new_run_directory(
    *,
    stdout: str,
    experiment_dir: Path,
    cwd: Path | None,
    before_names: set[str],
    seed: int,
) -> Path | None:
    """Locate the run directory one simulator subprocess just created."""

    parsed = parse_run_directory_from_stdout(
        stdout,
        experiment_dir=experiment_dir,
        cwd=cwd,
        seed=seed,
    )
    if parsed is not None:
        return parsed

    new_names = run_directory_names(experiment_dir).difference(before_names)
    matching = sorted(name for name in new_names if _matches_seed(name, seed))
    if not matching:
        return None
    return experiment_dir / matching[-1]


def _matches_seed(run_name: str, seed: int) -> bool:
    """Check the run-id's final underscore component against the seed.

    The run-id schema is frozen with the seed as its last component; exact
    comparison avoids ``endswith`` false-matches such as seed 55 vs 155.
    """

    return run_name.rsplit("_", 1)[-1] == str(seed)
