"""Config-file patching and Optuna search-space helpers."""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
import json
from pathlib import Path
from typing import Any

from abm_analysis.statistics.robustness_verdicts import VerdictThresholds

from .constants import CONFIG_KEY_PATTERN
from .models import BudgetSettings, CalibrationSettings, RankingSettings, ScoreWeights

def parse_seed_list(value: str | None) -> tuple[int, ...]:
    """Parse comma-separated deterministic seeds for calibration replication."""

    if value is None or not str(value).strip():
        return (55,)
    seeds = tuple(int(item.strip()) for item in str(value).split(",") if item.strip())
    if not seeds:
        raise ValueError("At least one calibration seed is required.")
    return seeds

def default_calibration_output_dir(calibration_name: str) -> Path:
    """Return the repository-local calibration output directory."""

    repository_root = Path(__file__).resolve().parents[4]
    return repository_root / "data" / "calibration" / calibration_name

def resolve_simulator_path(path: Path | str) -> Path:
    """Resolve the simulator executable from common local build layouts.

    Optimised builds are preferred: the CMake ``release`` preset tree is
    checked before ``debug``, and the legacy non-preset ``build/simulate``
    location (typically configured without a build type, i.e. un-optimised)
    is only a last resort before ``app/build``.
    """

    requested_path = Path(path).expanduser()
    if requested_path.is_file():
        return requested_path.resolve()

    repository_root = Path(__file__).resolve().parents[4]
    candidates = [
        repository_root / "build" / "release" / "simulate",
        repository_root / "build" / "debug" / "simulate",
        repository_root / "build" / "simulate",
        repository_root / "app" / "build" / "simulate",
    ]
    if not requested_path.is_absolute():
        candidates.insert(0, (Path.cwd() / requested_path))

    checked_paths: list[Path] = []
    for candidate in candidates:
        resolved_candidate = candidate.expanduser().resolve()
        if resolved_candidate in checked_paths:
            continue
        checked_paths.append(resolved_candidate)
        if resolved_candidate.is_file():
            print(
                f"Requested simulator {requested_path} does not exist; "
                f"using {resolved_candidate} instead."
            )
            return resolved_candidate

    checked_text = "\n  - ".join(str(candidate) for candidate in checked_paths)
    raise FileNotFoundError(
        "Simulator executable does not exist. Checked:\n"
        f"  - {checked_text}\n"
        "Build the simulator with CMake or pass --simulator PATH to an existing binary."
    )

def warn_if_simulator_stale(
    simulator_path: Path,
    repository_root: Path | None = None,
) -> bool:
    """Warn (never abort) when the simulator binary predates the C++ sources.

    Returns ``True`` when a warning was emitted. The check compares the binary
    mtime against the newest ``src/**/*.cpp``/``*.h`` file and the top-level
    ``CMakeLists.txt``; calibrating an intentionally older binary stays
    possible because this only prints.
    """

    if repository_root is None:
        repository_root = Path(__file__).resolve().parents[4]
    source_root = repository_root / "src"
    if not simulator_path.is_file() or not source_root.is_dir():
        return False

    newest_mtime = 0.0
    newest_source: Path | None = None
    source_files = list(source_root.rglob("*.cpp")) + list(source_root.rglob("*.h"))
    cmake_lists = repository_root / "CMakeLists.txt"
    if cmake_lists.is_file():
        source_files.append(cmake_lists)
    for source_file in source_files:
        mtime = source_file.stat().st_mtime
        if mtime > newest_mtime:
            newest_mtime = mtime
            newest_source = source_file
    if newest_source is None or simulator_path.stat().st_mtime >= newest_mtime:
        return False

    print(
        "WARNING: simulator binary is older than the newest C++ source "
        f"({newest_source.relative_to(repository_root)}).\n"
        "         Rebuild with: cmake --build --preset release"
    )
    return True

def load_search_space(path: Path | str) -> dict[str, dict[str, object]]:
    """Load and validate a JSON search-space specification.

    The accepted schema is either ``{"parameters": {...}}`` or a direct
    mapping of config keys to parameter specifications. A specification supports
    ``type`` values ``float``, ``int``, ``categorical``, and ``fixed``.
    """

    search_space_path = Path(path).expanduser().resolve()
    payload = json.loads(search_space_path.read_text(encoding="utf-8"))
    raw_parameters = payload.get("parameters", payload)
    if not isinstance(raw_parameters, dict) or not raw_parameters:
        raise ValueError("Search space must contain a non-empty parameters mapping.")

    parameters: dict[str, dict[str, object]] = {}
    for name, raw_spec in raw_parameters.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Search-space parameter names must be non-empty strings.")
        parameters[name] = _normalise_parameter_spec(name, raw_spec)
    return parameters

_SETTINGS_SECTIONS = {
    "score_weights": ScoreWeights,
    "verdict_thresholds": VerdictThresholds,
    "ranking": RankingSettings,
    "budget": BudgetSettings,
}

def load_calibration_settings(path: Path | str | None) -> CalibrationSettings:
    """Load calibration settings from JSON; ``None`` returns pure defaults.

    The schema mirrors :class:`CalibrationSettings`: an object with optional
    ``score_weights``, ``verdict_thresholds``, ``ranking``, and ``budget``
    sections, each holding only keys named after that dataclass's fields.
    Unknown sections or keys are rejected so typos never silently fall back
    to defaults.
    """

    if path is None:
        return CalibrationSettings()

    settings_path = Path(path).expanduser().resolve()
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Calibration settings must be a JSON object: {settings_path}")

    unknown_sections = sorted(set(payload) - set(_SETTINGS_SECTIONS))
    if unknown_sections:
        raise ValueError(
            f"Unknown calibration settings section(s) {unknown_sections} in "
            f"{settings_path}; expected {sorted(_SETTINGS_SECTIONS)}."
        )

    sections: dict[str, object] = {}
    for section_name, section_type in _SETTINGS_SECTIONS.items():
        raw_section = payload.get(section_name, {})
        if not isinstance(raw_section, dict):
            raise ValueError(
                f"Calibration settings section '{section_name}' must be a JSON object."
            )
        field_types = {
            field.name: field.type for field in dataclass_fields(section_type)
        }
        unknown_keys = sorted(set(raw_section) - set(field_types))
        if unknown_keys:
            raise ValueError(
                f"Unknown key(s) {unknown_keys} in calibration settings section "
                f"'{section_name}'; expected {sorted(field_types)}."
            )
        coerced = {
            key: (int(value) if "int" in str(field_types[key]) else float(value))
            for key, value in raw_section.items()
        }
        sections[section_name] = section_type(**coerced)

    return CalibrationSettings(**sections)

def suggest_trial_parameters(
    trial: Any,
    search_space: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Ask an Optuna trial for one candidate parameter set."""

    parameters: dict[str, object] = {}
    for name, spec in search_space.items():
        parameter_type = str(spec["type"])
        if parameter_type == "float":
            parameters[name] = trial.suggest_float(
                name,
                float(spec["low"]),
                float(spec["high"]),
                step=spec.get("step"),
                log=bool(spec.get("log", False)),
            )
        elif parameter_type == "int":
            parameters[name] = trial.suggest_int(
                name,
                int(spec["low"]),
                int(spec["high"]),
                step=int(spec.get("step", 1)),
                log=bool(spec.get("log", False)),
            )
        elif parameter_type == "categorical":
            parameters[name] = trial.suggest_categorical(name, list(spec["choices"]))
        elif parameter_type == "fixed":
            parameters[name] = spec["value"]
        else:  # pragma: no cover - guarded by _normalise_parameter_spec.
            raise ValueError(f"Unsupported parameter type: {parameter_type}")
    return parameters

def patch_config_text(config_text: str, updates: dict[str, object]) -> str:
    """Apply key-value updates while preserving comments and config ordering."""

    remaining_updates = dict(updates)
    patched_lines: list[str] = []
    for raw_line in config_text.splitlines(keepends=True):
        line, newline = _split_newline(raw_line)
        match = CONFIG_KEY_PATTERN.match(line)
        if match is None:
            patched_lines.append(raw_line)
            continue

        prefix, key, remainder = match.group(1), match.group(2), match.group(3)
        if key not in remaining_updates:
            patched_lines.append(raw_line)
            continue

        value_text = format_config_value(remaining_updates.pop(key))
        patched_lines.append(f"{prefix}{value_text}{_preserved_comment_suffix(remainder)}{newline}")

    if patched_lines and not patched_lines[-1].endswith(("\n", "\r")):
        patched_lines[-1] = f"{patched_lines[-1]}\n"

    if remaining_updates:
        patched_lines.append("\n# Automatically controlled by the calibration workflow.\n")
        for key in sorted(remaining_updates):
            patched_lines.append(f"{key} = {format_config_value(remaining_updates[key])}\n")

    return "".join(patched_lines)

def format_config_value(value: object) -> str:
    """Format a Python value for the project's ``key = value`` config files."""

    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)

def _normalise_parameter_spec(name: str, raw_spec: object) -> dict[str, object]:
    if isinstance(raw_spec, list):
        raw_spec = {"type": "categorical", "choices": raw_spec}
    elif not isinstance(raw_spec, dict):
        raw_spec = {"type": "fixed", "value": raw_spec}

    parameter_type = str(raw_spec.get("type", "")).lower()
    if not parameter_type:
        parameter_type = "categorical" if "choices" in raw_spec else "float"

    spec = dict(raw_spec)
    spec["type"] = parameter_type
    if parameter_type in {"float", "int"}:
        if "low" not in spec or "high" not in spec:
            raise ValueError(f"Search parameter '{name}' requires low and high bounds.")
        if float(spec["low"]) > float(spec["high"]):
            raise ValueError(f"Search parameter '{name}' has low > high.")
    elif parameter_type == "categorical":
        choices = spec.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError(f"Categorical search parameter '{name}' requires choices.")
    elif parameter_type == "fixed":
        if "value" not in spec:
            raise ValueError(f"Fixed search parameter '{name}' requires a value.")
    else:
        raise ValueError(f"Unsupported search parameter type for '{name}': {parameter_type}")
    return spec

def _split_newline(raw_line: str) -> tuple[str, str]:
    if raw_line.endswith("\r\n"):
        return raw_line[:-2], "\r\n"
    if raw_line.endswith("\n"):
        return raw_line[:-1], "\n"
    return raw_line, ""

def _preserved_comment_suffix(remainder: str) -> str:
    comment_index = remainder.find("#")
    if comment_index < 0:
        return ""
    value_without_comment = remainder[:comment_index].rstrip()
    return remainder[len(value_without_comment):]
