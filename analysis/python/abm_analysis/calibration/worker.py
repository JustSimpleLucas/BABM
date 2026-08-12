"""Isolated worker entry point for one calibration trial.

The parent Optuna process launches this module in a fresh Python interpreter so
pandas, NumPy, statsmodels, and ARCH allocations disappear when the worker
exits. This gives calibration a hard memory reset after every simulated trial.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import traceback

from .execution import run_candidate_worker_payload


def main(argv: list[str] | None = None) -> int:
    """Run one JSON-described calibration candidate and write a JSON response."""

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(
            "Usage: python -m abm_analysis.calibration.worker "
            "<request_json> <response_json>",
            file=sys.stderr,
        )
        return 2

    request_path = Path(args[0])
    response_path = Path(args[1])
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        response = run_candidate_worker_payload(payload)
        response_path.write_text(json.dumps(response, sort_keys=True), encoding="utf-8")
        return 0
    except Exception as exc:  # pragma: no cover - defensive worker boundary.
        response_path.write_text(
            json.dumps(
                {
                    "execution": {
                        "status": "worker_exception",
                        "config_path": "",
                        "run_dir": None,
                        "return_code": 1,
                        "stdout": "",
                        "stderr": traceback.format_exc(),
                        "message": str(exc),
                    },
                    "score": {
                        "score": 1.0e9,
                        "components": {
                            "market_distance": 1.0e9,
                            "stylised_penalty": 0.0,
                        },
                        "benchmark_scores": [],
                        "diagnostics": {
                            "diagnostic_status": "worker_exception",
                            "message": str(exc),
                        },
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
