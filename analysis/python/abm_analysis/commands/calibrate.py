"""Optuna calibration command: parser and handler."""

from __future__ import annotations

import argparse
from pathlib import Path
from .shared_arguments import add_calibration_benchmark_arguments
from .shared_helpers import resolve_benchmark_dir, timestamped_calibration_name
from abm_analysis.calibration import CalibrationOptions
from abm_analysis.calibration import default_calibration_output_dir
from abm_analysis.calibration import parse_seed_list
from abm_analysis.calibration import run_calibration
from abm_analysis.replication import parse_seed_spec


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``calibrate`` command."""

    calibrate_parser = subparsers.add_parser(
        "calibrate",
        help="Search simulation config combinations against empirical benchmark returns.",
    )
    calibrate_parser.add_argument(
        "--base-config",
        type=Path,
        required=True,
        help="Base key=value simulation config used as the calibration template.",
    )
    calibrate_parser.add_argument(
        "--search-space",
        type=Path,
        required=True,
        help="JSON file describing the config parameters Optuna may vary.",
    )
    calibrate_parser.add_argument(
        "--simulator",
        type=Path,
        default=Path("build/release/simulate"),
        help=(
            "Path to the compiled C++ simulator executable. Defaults to the "
            "optimised release build; build it with 'cmake --preset release "
            "&& cmake --build --preset release'."
        ),
    )
    calibrate_parser.add_argument(
        "--calibration-name",
        default=None,
        help="Name used under data/calibration. Defaults to a timestamped study name.",
    )
    calibrate_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional explicit calibration output directory.",
    )
    calibrate_parser.add_argument(
        "--trials",
        type=int,
        default=50,
        help="Number of Optuna search trials before seed-robust validation.",
    )
    calibrate_parser.add_argument(
        "--seeds",
        default="55",
        help=(
            "Comma-separated seeds. The first seed is used during search; "
            "all seeds validate top candidates unless --validation-seeds is given."
        ),
    )
    calibrate_parser.add_argument(
        "--validation-seeds",
        default=None,
        help=(
            "Seeds used only to validate top candidates, as a comma list or "
            "start:end range (e.g. '55,101:109'). At least 5 seeds enable "
            "robustness verdicts in the candidate ranking; 10+ recommended. "
            "Defaults to --seeds."
        ),
    )
    calibrate_parser.add_argument(
        "--search-seeds",
        default=None,
        help=(
            "Seeds each search trial is scored over, as a comma list or "
            "start:end range (e.g. '55,66,77'). Averaging over 3+ seeds stops "
            "Optuna from fitting single-seed noise; reduce --trials to keep "
            "the run budget. Defaults to the first --seeds entry only."
        ),
    )
    calibrate_parser.add_argument(
        "--search-seed-aggregate",
        choices=["mean", "median"],
        default="mean",
        help=(
            "How per-seed search scores combine into one objective value. "
            "'mean' rejects candidates that crash on any seed; 'median' "
            "tolerates one bad seed but can mask crash-prone regions."
        ),
    )
    calibrate_parser.add_argument(
        "--sampler-seed",
        type=int,
        default=55,
        help="Deterministic Optuna TPE sampler seed for reproducible searches.",
    )
    calibrate_parser.add_argument(
        "--no-sampler-seed",
        action="store_true",
        help="Use a nondeterministic Optuna sampler (legacy behaviour).",
    )
    calibrate_parser.add_argument(
        "--require-robustness-verdicts",
        action="store_true",
        help=(
            "Abort up front when --validation-seeds cannot support robustness "
            "verdicts instead of degrading to the fit-only ranking."
        ),
    )
    calibrate_parser.add_argument(
        "--top-candidates",
        type=int,
        default=5,
        help="Number of best search trials rerun across the validation seeds.",
    )
    calibrate_parser.add_argument(
        "--calibration-settings",
        type=Path,
        default=None,
        help=(
            "Optional JSON overriding score weights, robustness-verdict "
            "thresholds, ranking, and budget defaults "
            "(see config/calibration/calibration_settings.json)."
        ),
    )
    calibrate_parser.add_argument(
        "--robustness-penalty-weight",
        type=float,
        default=None,
        help=(
            "Weight of the robustness shortfall in the final ranking: "
            "robust_score = fit_score * (1 + w * (1 - pass_rate)). "
            "Overrides the settings file (default 1.0)."
        ),
    )
    calibrate_parser.add_argument(
        "--score-threshold",
        type=float,
        default=None,
        help="Optional lower-is-better score threshold for early stopping.",
    )
    calibrate_parser.add_argument(
        "--no-improvement-trials",
        type=int,
        default=None,
        help="Optional early stop after this many trials without score improvement.",
    )
    calibrate_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=None,
        help="Optional timeout for each simulator execution.",
    )
    calibrate_parser.add_argument(
        "--phase",
        default="simulation",
        help="Phase used for return diagnostics.",
    )
    calibrate_parser.add_argument(
        "--price-column",
        default="market_price",
        help="Price column used to compute simulated log returns.",
    )
    calibrate_parser.add_argument(
        "--holdout-benchmark-series",
        default=None,
        help="Optional comma-separated benchmark IDs reserved for holdout validation.",
    )
    calibrate_parser.add_argument(
        "--keep-run-csv",
        action="store_true",
        help="Keep per-run simulator CSV artefacts after scoring instead of pruning them.",
    )
    calibrate_parser.add_argument(
        "--no-isolate-trials",
        action="store_true",
        help="Run trial scoring in the parent Python process instead of a fresh worker.",
    )
    calibrate_parser.add_argument(
        "--quiet-simulation-progress",
        action="store_true",
        help="Hide the C++ per-step progress bar for each calibration simulation.",
    )
    calibrate_parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help=(
            "Concurrent seed-level simulator runs within one trial; trials "
            "stay sequential. 0 (default) launches one per CPU core, capped "
            "at the seed count; 1 restores sequential execution. Parallel "
            "runs disable the live progress bar, and full speedup requires "
            "trial isolation (the default)."
        ),
    )
    add_calibration_benchmark_arguments(calibrate_parser)
    calibrate_parser.set_defaults(handler=handle_calibrate)


def handle_calibrate(args: argparse.Namespace) -> int:
    """Run the calibration workflow against empirical benchmark returns."""

    benchmark_dir = resolve_benchmark_dir(args)
    if benchmark_dir is None:
        parser_hint = (
            "Use --benchmark-dir or place benchmark CSVs under "
            "data/stock_data/candle_chart."
        )
        raise FileNotFoundError(f"Calibration requires empirical benchmark CSVs. {parser_hint}")

    calibration_name = args.calibration_name or timestamped_calibration_name()
    output_dir = args.output_dir or default_calibration_output_dir(calibration_name)
    options = CalibrationOptions(
        base_config=args.base_config,
        search_space=args.search_space,
        simulator=args.simulator,
        calibration_name=calibration_name,
        trials=args.trials,
        seeds=parse_seed_list(args.seeds),
        output_dir=output_dir,
        benchmark_dir=benchmark_dir,
        benchmark_series=args.benchmark_series,
        holdout_benchmark_series=args.holdout_benchmark_series,
        top_candidates=args.top_candidates,
        score_threshold=args.score_threshold,
        no_improvement_trials=args.no_improvement_trials,
        phase=args.phase,
        price_column=args.price_column,
        timeout_seconds=args.timeout_seconds,
        keep_run_csv=args.keep_run_csv,
        isolate_trials=not args.no_isolate_trials,
        show_simulation_progress=not args.quiet_simulation_progress,
        validation_seeds=(
            parse_seed_spec(args.validation_seeds)
            if args.validation_seeds is not None
            else None
        ),
        settings_path=args.calibration_settings,
        robustness_penalty_weight=args.robustness_penalty_weight,
        search_seeds=(
            parse_seed_spec(args.search_seeds)
            if args.search_seeds is not None
            else None
        ),
        search_seed_aggregate=args.search_seed_aggregate,
        sampler_seed=None if args.no_sampler_seed else args.sampler_seed,
        require_robustness_verdicts=args.require_robustness_verdicts,
        jobs=args.jobs,
    )
    output_path = run_calibration(options)
    print(f"Calibration output: {output_path}")
    return 0
