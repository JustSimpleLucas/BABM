from __future__ import annotations

import threading
import time

import pytest

from abm_analysis.parallel import map_in_order, resolve_job_count


def test_resolve_job_count_auto_and_explicit_values() -> None:
    import os

    cpu_count = os.cpu_count() or 1
    assert resolve_job_count(0, 8) == min(cpu_count, 8)
    assert resolve_job_count(3, 8) == 3
    assert resolve_job_count(16, 4) == 4
    assert resolve_job_count(1, 5) == 1
    assert resolve_job_count(0, 0) == 1


def test_map_in_order_sequential_preserves_order_and_indices() -> None:
    calls: list[tuple[int, str]] = []
    collected: list[tuple[int, str]] = []

    results = map_in_order(
        ["a", "b", "c"],
        lambda index, item: calls.append((index, item)) or item.upper(),
        jobs=1,
        on_result=lambda index, result: collected.append((index, result)),
    )

    assert calls == [(1, "a"), (2, "b"), (3, "c")]
    assert results == ["A", "B", "C"]
    assert collected == [(1, "A"), (2, "B"), (3, "C")]


def test_map_in_order_parallel_returns_submission_order() -> None:
    delays = {"a": 0.15, "b": 0.0, "c": 0.05}
    collected: list[str] = []
    main_thread = threading.get_ident()
    callback_threads: set[int] = set()

    def slow_upper(index: int, item: str) -> str:
        time.sleep(delays[item])
        return item.upper()

    def on_result(index: int, result: str) -> None:
        callback_threads.add(threading.get_ident())
        collected.append(result)

    results = map_in_order(["a", "b", "c"], slow_upper, jobs=3, on_result=on_result)

    assert results == ["A", "B", "C"]
    assert collected == ["A", "B", "C"]
    assert callback_threads == {main_thread}


def test_map_in_order_first_synchronous_completes_before_pool_opens() -> None:
    events: list[str] = []
    lock = threading.Lock()

    def record(index: int, item: str) -> str:
        with lock:
            events.append(f"start_{item}")
        time.sleep(0.02)
        with lock:
            events.append(f"end_{item}")
        return item

    map_in_order(
        ["first", "second", "third"],
        record,
        jobs=3,
        run_first_synchronously=True,
    )

    assert events[0] == "start_first"
    assert events[1] == "end_first"


def test_map_in_order_propagates_worker_exception() -> None:
    def explode(index: int, item: int) -> int:
        if item == 2:
            raise RuntimeError("boom")
        return item

    with pytest.raises(RuntimeError, match="boom"):
        map_in_order([1, 2, 3], explode, jobs=2)
