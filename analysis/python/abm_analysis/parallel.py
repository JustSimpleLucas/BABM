"""Ordered thread-pool execution for independent simulator subprocesses.

Worker threads only launch and wait on subprocesses (the GIL is released
inside ``subprocess``), so a thread pool gives full parallelism without the
pickling constraints of process pools. Results are always collected on the
calling thread in submission order, which lets callers keep their CSV
writers and record lists single-threaded and deterministic.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from typing import Callable, Sequence, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def resolve_job_count(jobs: int, task_count: int) -> int:
    """Resolve a ``--jobs`` value into an effective worker count.

    ``jobs <= 0`` means auto: one worker per CPU core. The result is always
    capped at ``task_count`` so short batches never over-provision threads.
    """

    if task_count <= 0:
        return 1
    if jobs <= 0:
        return min(os.cpu_count() or 1, task_count)
    return min(jobs, task_count)


def map_in_order(
    items: Sequence[T],
    fn: Callable[[int, T], R],
    *,
    jobs: int,
    on_result: Callable[[int, R], None] | None = None,
    run_first_synchronously: bool = False,
) -> list[R]:
    """Run ``fn(index_1_based, item)`` over ``items``, collecting results in order.

    With an effective job count of one this is a plain sequential loop.
    Otherwise all items are submitted to a thread pool up front and results
    are consumed in submission order on the calling thread, where
    ``on_result(index, result)`` is also invoked (for checkpoint writes that
    must stay single-threaded).

    ``run_first_synchronously`` completes the first item before the pool
    opens; callers use it when the first simulator run of a fresh experiment
    directory must create shared files (the experiment manifest header)
    without a concurrent writer.
    """

    effective_jobs = resolve_job_count(jobs, len(items))
    results: list[R] = []

    def collect(index: int, result: R) -> None:
        results.append(result)
        if on_result is not None:
            on_result(index, result)

    if effective_jobs <= 1:
        for index, item in enumerate(items, start=1):
            collect(index, fn(index, item))
        return results

    start = 0
    if run_first_synchronously and len(items) > 0:
        collect(1, fn(1, items[0]))
        start = 1

    executor = ThreadPoolExecutor(max_workers=effective_jobs)
    try:
        futures = [
            executor.submit(fn, index, item)
            for index, item in enumerate(items[start:], start=start + 1)
        ]
        for index, future in enumerate(futures, start=start + 1):
            collect(index, future.result())
    finally:
        # Cancel queued work instead of blocking in shutdown when a result
        # raises (worker timeout) or the user interrupts; running child
        # simulators receive the terminal's SIGINT themselves and unwind.
        executor.shutdown(wait=False, cancel_futures=True)
    return results
