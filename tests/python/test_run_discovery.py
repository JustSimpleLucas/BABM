from __future__ import annotations

from pathlib import Path

from abm_analysis.archive.run_discovery import (
    RUN_DIRECTORY_STDOUT_PREFIX,
    discover_new_run_directory,
    parse_run_directory_from_stdout,
    run_directory_names,
)


def _make_run_dir(experiment_dir: Path, run_id: str) -> Path:
    run_dir = experiment_dir / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "step_timeseries.csv").write_text("row_index\n0\n", encoding="utf-8")
    return run_dir


def test_parse_returns_absolute_path_printed_by_simulator(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    run_dir = _make_run_dir(experiment_dir, "20260701120000_1_1_0_0_20_30_5_0_180_55")

    stdout = f"Loaded config\n{RUN_DIRECTORY_STDOUT_PREFIX}{run_dir}\nDone\n"
    parsed = parse_run_directory_from_stdout(
        stdout,
        experiment_dir=experiment_dir,
        cwd=None,
        seed=55,
    )

    assert parsed == run_dir.resolve()


def test_parse_resolves_relative_path_against_subprocess_cwd(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    run_dir = _make_run_dir(experiment_dir, "20260701120000_1_1_0_0_20_30_5_0_180_55")

    relative = run_dir.relative_to(tmp_path)
    stdout = f"{RUN_DIRECTORY_STDOUT_PREFIX}{relative}\n"
    parsed = parse_run_directory_from_stdout(
        stdout,
        experiment_dir=experiment_dir,
        cwd=tmp_path,
        seed=55,
    )

    assert parsed == run_dir.resolve()


def test_parse_survives_carriage_return_progress_frames(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    run_dir = _make_run_dir(experiment_dir, "20260701120000_1_1_0_0_20_30_5_0_180_55")

    stdout = (
        "Simulation progress [##........]  20%\r"
        "Simulation progress [##########] 100%\r"
        f"{RUN_DIRECTORY_STDOUT_PREFIX}{run_dir}\n"
    )
    parsed = parse_run_directory_from_stdout(
        stdout,
        experiment_dir=experiment_dir,
        cwd=None,
        seed=55,
    )

    assert parsed == run_dir.resolve()


def test_parse_rejects_path_outside_experiment_dir(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    outside_dir = _make_run_dir(tmp_path / "elsewhere", "20260701120000_1_1_0_0_20_30_5_0_180_55")

    parsed = parse_run_directory_from_stdout(
        f"{RUN_DIRECTORY_STDOUT_PREFIX}{outside_dir}\n",
        experiment_dir=experiment_dir,
        cwd=None,
        seed=55,
    )

    assert parsed is None


def test_parse_rejects_seed_mismatch_and_missing_archive(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    run_dir = _make_run_dir(experiment_dir, "20260701120000_1_1_0_0_20_30_5_0_180_55")
    empty_dir = experiment_dir / "20260701120001_1_1_0_0_20_30_5_0_180_66"
    empty_dir.mkdir()

    wrong_seed = parse_run_directory_from_stdout(
        f"{RUN_DIRECTORY_STDOUT_PREFIX}{run_dir}\n",
        experiment_dir=experiment_dir,
        cwd=None,
        seed=66,
    )
    no_archive = parse_run_directory_from_stdout(
        f"{RUN_DIRECTORY_STDOUT_PREFIX}{empty_dir}\n",
        experiment_dir=experiment_dir,
        cwd=None,
        seed=66,
    )

    assert wrong_seed is None
    assert no_archive is None


def test_fallback_diff_picks_seed_match_not_highest_sorted_name(tmp_path: Path) -> None:
    """Regression test for the parallel-seed race in the old diff-and-take-last logic."""

    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    before_names = run_directory_names(experiment_dir)
    # A sibling seed's run appears between the snapshots and sorts last.
    target = _make_run_dir(experiment_dir, "20260701120000_1_1_0_0_20_30_5_0_180_55")
    _make_run_dir(experiment_dir, "20260701120009_1_1_0_0_20_30_5_0_180_66")

    discovered = discover_new_run_directory(
        stdout="ok",
        experiment_dir=experiment_dir,
        cwd=None,
        before_names=before_names,
        seed=55,
    )

    assert discovered == target


def test_fallback_requires_exact_seed_component_match(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    before_names = run_directory_names(experiment_dir)
    _make_run_dir(experiment_dir, "20260701120000_1_1_0_0_20_30_5_0_180_155")

    discovered = discover_new_run_directory(
        stdout="ok",
        experiment_dir=experiment_dir,
        cwd=None,
        before_names=before_names,
        seed=55,
    )

    assert discovered is None


def test_stdout_parse_wins_over_later_sorting_fallback_candidate(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    before_names = run_directory_names(experiment_dir)
    target = _make_run_dir(experiment_dir, "20260701120000_1_1_0_0_20_30_5_0_180_55")
    # Same seed, later timestamp: the diff fallback would pick this decoy.
    _make_run_dir(experiment_dir, "20260701120009_1_1_0_0_20_30_5_0_180_55")

    discovered = discover_new_run_directory(
        stdout=f"{RUN_DIRECTORY_STDOUT_PREFIX}{target}\n",
        experiment_dir=experiment_dir,
        cwd=None,
        before_names=before_names,
        seed=55,
    )

    assert discovered == target.resolve()


def test_discovery_returns_none_when_nothing_matches(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()

    discovered = discover_new_run_directory(
        stdout="ok",
        experiment_dir=experiment_dir,
        cwd=None,
        before_names=set(),
        seed=55,
    )

    assert discovered is None
