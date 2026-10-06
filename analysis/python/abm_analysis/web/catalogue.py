"""Discovery of archived simulation runs beneath a data root.

The archive is not a flat list. Ordinary experiments live in
``data/experiments/<experiment_name>/<run_id>``, calibration studies keep their
own runs under ``data/calibration/<study>/{simulation_runs,best_runs}``, and
``data/latest`` is a single run directory sitting directly under the root. Rather
than hard-coding those three layouts — which would silently miss a fourth — this
module walks the tree and treats **any** directory holding a
``step_timeseries.csv`` as a run, grouping runs by their parent directory. The
parent's path is what the interface calls an "experiment".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from abm_analysis.archive.archives import resolve_artifact_path
from abm_analysis.archive.run_ids import parse_run_id
from abm_analysis.statistics.calibration_study import is_calibration_study
from abm_analysis.web.serialisation import json_safe


#: Subdirectories that belong to a run's own output and can never be runs.
#: Pruning them keeps the walk cheap on archives with thousands of figures.
NON_RUN_DIRECTORY_NAMES = frozenset(
    {
        "__pycache__",
        "best_runs_robustness_report",
        "calibration_report",
        "comparison_reports",
        "figures",
        "holdout_validation",
        "logs",
        "python_analysis",
        "robustness_reports",
        "sql_reports",
        "trial_configs",
        "worker_payloads",
    }
)

#: How deep below the data root a run directory may sit. Calibration studies
#: are the deepest real case (``calibration/<study>/best_runs/<run_id>`` = 4).
MAXIMUM_SEARCH_DEPTH = 5


@dataclass(frozen=True)
class RunEntry:
    """One archived run as the run picker needs to describe it.

    Only the run-id is parsed here — reading each run's CSVs to populate the
    picker would make the catalogue cost grow with the size of the archive.
    The authoritative parameter record is loaded on demand when a run is opened.
    """

    run_id: str
    relative_path: str
    parameters: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON payload for one run-picker entry."""

        return json_safe(
            {
                "run_id": self.run_id,
                "path": self.relative_path,
                "created_at": self.parameters.get("run_id_created_at_local"),
                "seed": self.parameters.get("run_id_seed"),
                "time_steps": self.parameters.get("run_id_time_steps"),
                "prospect_theory_enabled": self.parameters.get("run_id_prospect_theory_enabled"),
                "social_enabled": self.parameters.get("run_id_social_enabled"),
                "short_selling_enabled": self.parameters.get("run_id_short_selling_enabled"),
                "population": {
                    "fundamentalists": self.parameters.get("run_id_num_fundamentalists"),
                    "chartists": self.parameters.get("run_id_num_chartists"),
                    "noise_traders": self.parameters.get("run_id_num_noise_traders"),
                    "buy_and_hold": self.parameters.get("run_id_num_buy_and_hold_agents"),
                },
            }
        )


@dataclass(frozen=True)
class ExperimentEntry:
    """A directory of archived runs, presented as one group in the picker."""

    name: str
    relative_path: str
    runs: tuple[RunEntry, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON payload for one experiment group."""

        return {
            "name": self.name,
            "path": self.relative_path,
            "run_count": len(self.runs),
            "runs": [run.to_dict() for run in self.runs],
        }


def is_run_directory(path: Path) -> bool:
    """Check whether a directory is an archived run.

    ``step_timeseries.csv`` is the one artefact every run has and every
    analysis command requires, so it is the archive's defining marker. The
    compressed ``.gz`` form counts, since ``compress`` rewrites completed
    archives in place.
    """

    return path.is_dir() and resolve_artifact_path(path, "step_timeseries.csv") is not None


def discover_runs(data_root: Path) -> list[Path]:
    """Return every run directory beneath ``data_root``, in archive order.

    The walk prunes report and working directories and stops at
    ``MAXIMUM_SEARCH_DEPTH``. A run directory is never descended into, so a
    nested figures folder cannot be mistaken for a second run.
    """

    root = data_root.expanduser().resolve()
    if not root.is_dir():
        return []

    discovered: list[Path] = []
    for current_dir, subdirectory_names, _ in os.walk(root):
        current_path = Path(current_dir)
        depth = len(current_path.relative_to(root).parts)
        if depth >= MAXIMUM_SEARCH_DEPTH:
            subdirectory_names.clear()
            continue
        subdirectory_names[:] = sorted(
            name
            for name in subdirectory_names
            if name not in NON_RUN_DIRECTORY_NAMES and not name.startswith(".")
        )
        retained: list[str] = []
        for name in subdirectory_names:
            candidate = current_path / name
            if is_run_directory(candidate):
                discovered.append(candidate)
            else:
                retained.append(name)
        subdirectory_names[:] = retained
    return sorted(discovered, key=lambda path: str(path))


def build_catalogue(data_root: Path) -> list[ExperimentEntry]:
    """Group every discovered run under the directory that contains it.

    Groups are ordered by name and runs within a group by run-id, which is
    chronological because the frozen run-id schema starts with the timestamp.
    """

    root = data_root.expanduser().resolve()
    grouped: dict[Path, list[Path]] = {}
    for run_path in discover_runs(root):
        grouped.setdefault(run_path.parent, []).append(run_path)

    experiments: list[ExperimentEntry] = []
    for parent_path in sorted(grouped, key=lambda path: str(path)):
        run_entries = tuple(
            RunEntry(
                run_id=run_path.name,
                relative_path=relative_path_text(run_path, root),
                parameters=parse_run_id(run_path.name),
            )
            for run_path in sorted(grouped[parent_path], key=lambda path: path.name)
        )
        experiments.append(
            ExperimentEntry(
                name=experiment_name(parent_path, root),
                relative_path=relative_path_text(parent_path, root),
                runs=run_entries,
            )
        )
    return experiments


def experiment_name(parent_path: Path, data_root: Path) -> str:
    """Return the label shown for a group of runs.

    ``data/experiments/demo`` reads as ``demo``, while a calibration study's
    runs read as ``calibration/<study>/best_runs`` — the extra context matters
    because those runs were produced by a search, not by a deliberate
    experiment configuration.
    """

    if parent_path == data_root:
        return data_root.name
    parts = parent_path.relative_to(data_root).parts
    if parts[0] == "experiments":
        return "/".join(parts[1:]) or "experiments"
    return "/".join(parts)


def relative_path_text(path: Path, data_root: Path) -> str:
    """Return a path relative to the data root, used as the API's run handle.

    Relative handles keep absolute filesystem paths out of the browser and make
    the resolution in ``resolve_run_path`` a containment check rather than a
    trust decision.
    """

    if path == data_root:
        return "."
    return str(path.relative_to(data_root))


def resolve_run_path(relative_path: str, data_root: Path) -> Path:
    """Resolve a client-supplied run handle to a directory inside the data root.

    Raises ``ValueError`` when the resolved path escapes the data root or is
    not an archived run. The server is bound to the loopback interface, but the
    check is unconditional: a path parameter is untrusted input regardless of
    who can reach the port.
    """

    root = data_root.expanduser().resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Run path is outside the data root: {relative_path}")
    if not is_run_directory(candidate):
        raise ValueError(f"Not an archived run directory: {relative_path}")
    return candidate


def discover_calibration_studies(data_root: Path) -> list[Path]:
    """Return every calibration study beneath ``data_root``.

    A study is any directory holding ``calibration_trials.csv``. The walk does not
    descend into one: what sits beneath a study — its trial configs, its best runs,
    its reports — belongs to the study, and the best runs are already listed by
    ``discover_runs`` where they can be opened as runs.
    """

    root = data_root.expanduser().resolve()
    if not root.is_dir():
        return []

    studies: list[Path] = []
    for current_dir, subdirectory_names, _ in os.walk(root):
        current_path = Path(current_dir)
        if len(current_path.relative_to(root).parts) >= MAXIMUM_SEARCH_DEPTH:
            subdirectory_names.clear()
            continue
        if is_calibration_study(current_path):
            studies.append(current_path)
            subdirectory_names.clear()
            continue
        subdirectory_names[:] = sorted(
            name
            for name in subdirectory_names
            if name not in NON_RUN_DIRECTORY_NAMES and not name.startswith(".")
        )
    return sorted(studies, key=lambda path: str(path))


def resolve_study_path(relative_path: str, data_root: Path) -> Path:
    """Resolve a client-supplied study handle to a study directory inside the data root.

    Raises ``ValueError`` when the resolved path escapes the data root or is not a
    calibration study, on the same terms as ``resolve_run_path``.
    """

    root = data_root.expanduser().resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Study path is outside the data root: {relative_path}")
    if not is_calibration_study(candidate):
        raise ValueError(f"Not a calibration study: {relative_path}")
    return candidate
