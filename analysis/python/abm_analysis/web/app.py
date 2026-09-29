"""FastAPI application serving the read-only run and statistics dashboard.

The application exposes three things: a catalogue of archived runs, the
statistics payload for one run, and the static single-page interface that
renders them. It never writes to ``data/`` and never starts a simulation, so
running it alongside an active experiment cannot disturb the archive.

The Plotly bundle is served from the installed ``plotly`` package rather than a
content-delivery network, so the dashboard works with no network connection and
its charts are drawn by exactly the library version pinned in
``requirements.txt``.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from abm_analysis.environment import configure_analysis_environment
from abm_analysis.web.catalogue import (
    build_catalogue,
    discover_runs,
    resolve_run_path,
)
from abm_analysis.web.cohort_view import (
    MAXIMUM_COHORT_RUNS,
    MINIMUM_COHORT_RUNS,
    build_cohort_view,
)
from abm_analysis.web.run_view import build_run_view


#: Directory holding the single-page interface.
STATIC_DIRECTORY = Path(__file__).parent / "static"

#: Default data root, relative to the working directory the command is run from.
DEFAULT_DATA_ROOT = Path("data")

#: Every archive file the run view reads. All of them are stamped into the
#: cache key, so touching any one of them re-computes the payload.
CACHE_KEY_ARTEFACTS = (
    "step_timeseries.csv",
    "asset_timeseries.csv",
    "agents_final.csv",
    "protagonist_timeseries.csv",
    "summary_metrics.csv",
    "config.json",
    "metadata.json",
)


def create_app(data_root: Path | str = DEFAULT_DATA_ROOT) -> FastAPI:
    """Build the dashboard application for one archive root.

    Args:
        data_root: Directory the run catalogue is discovered under. Every run
            handle the API accepts is resolved inside this directory.

    Returns:
        A configured FastAPI application. The data root is resolved once at
        construction so that later changes to the working directory cannot move
        the archive out from under a running server.
    """

    configure_analysis_environment()
    resolved_data_root = Path(data_root).expanduser().resolve()

    application = FastAPI(
        title="BABM market statistics",
        description=(
            "Read-only browser for archived behavioural agent-based market runs "
            "and their stylised-fact statistics."
        ),
        version="0.1.0",
    )
    application.state.data_root = resolved_data_root

    @application.get("/api/catalogue")
    def read_catalogue() -> dict[str, Any]:
        """List every archived run beneath the data root, grouped by experiment."""

        experiments = build_catalogue(resolved_data_root)
        return {
            "data_root": str(resolved_data_root),
            "data_root_exists": resolved_data_root.is_dir(),
            "experiment_count": len(experiments),
            "run_count": sum(len(experiment.runs) for experiment in experiments),
            "experiments": [experiment.to_dict() for experiment in experiments],
        }

    @application.get("/api/run")
    def read_run(
        path: str = Query(..., description="Run directory, relative to the data root."),
        phase: str = Query("simulation", description="Step phase to analyse, or 'all'."),
        price_column: str = Query("market_price", description="Price column for log returns."),
    ) -> dict[str, Any]:
        """Return the full statistics payload for one archived run."""

        try:
            run_path = resolve_run_path(path, resolved_data_root)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        try:
            return _cached_run_view(run_path, phase, price_column, _archive_generation(run_path))
        except (KeyError, FileNotFoundError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/cohort")
    def read_cohort(
        path: list[str] = Query(
            ..., description="Run directories, relative to the data root. Repeat per run."
        ),
        phase: str = Query("simulation", description="Step phase to analyse, or 'all'."),
        price_column: str = Query("market_price", description="Price column for log returns."),
    ) -> dict[str, Any]:
        """Return the cross-seed and cross-condition payload for a set of runs."""

        return _cohort_response(resolved_data_root, path, phase, price_column)

    @application.get("/api/cohort/experiment")
    def read_experiment_cohort(
        path: str = Query(..., description="Experiment directory, relative to the data root."),
        phase: str = Query("simulation", description="Step phase to analyse, or 'all'."),
        price_column: str = Query("market_price", description="Price column for log returns."),
    ) -> dict[str, Any]:
        """Return the cohort payload for every run in one experiment directory."""

        group_path = (resolved_data_root / path).resolve()
        if group_path != resolved_data_root and resolved_data_root not in group_path.parents:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment path is outside the data root: {path}",
            )
        members = [
            run_path
            for run_path in discover_runs(resolved_data_root)
            if run_path.parent == group_path
        ]
        if not members:
            raise HTTPException(status_code=404, detail=f"No archived runs under: {path}")
        relative = [str(run_path.relative_to(resolved_data_root)) for run_path in members]
        return _cohort_response(resolved_data_root, relative, phase, price_column)

    @application.get("/vendor/plotly.min.js")
    def read_plotly_bundle() -> FileResponse:
        """Serve the Plotly bundle shipped with the installed ``plotly`` package."""

        bundle_path = _plotly_bundle_path()
        if bundle_path is None:
            raise HTTPException(
                status_code=503,
                detail="The installed plotly package does not ship plotly.min.js.",
            )
        return FileResponse(bundle_path, media_type="application/javascript")

    @application.get("/")
    def read_index() -> HTMLResponse:
        """Serve the single-page interface with its assets versioned by content.

        The stylesheet and script are referenced as ``app.js?v=<hash>``, so a
        change to either is a new URL and no browser can pair a cached script
        with a newer page. Safari in particular reuses a subresource it holds
        without asking the server, whatever the server now says about caching.
        """

        html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
        for name in ("styles.css", "app.js"):
            html = html.replace(
                f"/static/{name}",
                f"/static/{name}?v={_asset_version(STATIC_DIRECTORY / name)}",
            )
        return HTMLResponse(html)

    application.mount(
        "/static",
        StaticFiles(directory=STATIC_DIRECTORY),
        name="static",
    )

    @application.middleware("http")
    async def revalidate_interface(request: Request, call_next: Any) -> Response:
        """Make the browser revalidate the page and its script on every load.

        Without a cache policy browsers keep a static file for a share of the
        time since it last changed, so after an upgrade a reader can get the
        new ``index.html`` with a stale ``app.js`` and a page that fails on an
        element that no longer exists. ``no-cache`` still allows a conditional
        request, which the ETag answers with 304; only the vendored Plotly
        bundle, which changes with the package, keeps the default.
        """

        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @application.exception_handler(ValueError)
    def handle_value_error(_request: Any, error: ValueError) -> JSONResponse:
        """Return archive problems as a readable message instead of a traceback."""

        return JSONResponse(status_code=422, content={"detail": str(error)})

    return application


def serve(
    data_root: Path | str = DEFAULT_DATA_ROOT,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Run the dashboard with uvicorn until interrupted.

    The default host is the loopback interface: the archive is unpublished
    research output, so the server is not reachable from the network unless the
    user asks for that explicitly.
    """

    import uvicorn

    uvicorn.run(
        create_app(data_root),
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


def _cohort_response(
    data_root: Path,
    paths: list[str],
    phase: str,
    price_column: str,
) -> dict[str, Any]:
    """Validate a cohort request and return its payload.

    Duplicate selections are collapsed rather than rejected: the same run
    reached through two handles is one run, and counting it twice would halve
    every dispersion statistic on the page.
    """

    unique_paths = list(dict.fromkeys(paths))
    if len(unique_paths) < MINIMUM_COHORT_RUNS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"A cohort needs at least {MINIMUM_COHORT_RUNS} runs; "
                f"{len(unique_paths)} were selected."
            ),
        )
    if len(unique_paths) > MAXIMUM_COHORT_RUNS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"A cohort is limited to {MAXIMUM_COHORT_RUNS} runs; "
                f"{len(unique_paths)} were selected. Every run costs a GARCH fit."
            ),
        )

    run_paths: list[Path] = []
    for relative_path in unique_paths:
        try:
            run_paths.append(resolve_run_path(relative_path, data_root))
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    # Resolution can still collapse two handles onto one directory.
    run_paths = list(dict.fromkeys(run_paths))
    if len(run_paths) < MINIMUM_COHORT_RUNS:
        raise HTTPException(
            status_code=422,
            detail=f"A cohort needs at least {MINIMUM_COHORT_RUNS} distinct runs.",
        )

    try:
        return _cached_cohort_view(
            tuple(run_paths),
            phase,
            price_column,
            tuple(_archive_generation(run_path) for run_path in run_paths),
        )
    except (KeyError, FileNotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


# Cohort payloads are larger than run payloads and a reader compares a handful
# of cohorts in a session, so fewer are held than the per-run diagnostics below.
@lru_cache(maxsize=8)
def _cached_cohort_view(
    run_paths: tuple[Path, ...],
    phase: str,
    price_column: str,
    archive_generations: tuple[tuple[tuple[int, int], ...], ...],
) -> dict[str, Any]:
    """Memoise one cohort's payload for the current generation of its archives."""

    from abm_analysis.exports.seed_robustness import build_seed_robustness_frames

    diagnostics: list[dict[str, Any]] = []
    return_series: dict[str, pd.Series] = {}
    for run_path, generation in zip(run_paths, archive_generations, strict=True):
        diagnostics.extend(
            dict(row) for row in _cached_run_diagnostics(run_path, phase, price_column, generation)
        )
        return_series.update(
            _cached_run_return_series(run_path, phase, price_column, generation)
        )

    frames = build_seed_robustness_frames(
        list(run_paths),
        phase=phase,
        price_column=price_column,
        per_asset=True,
        diagnostics=pd.DataFrame(diagnostics),
        return_series=return_series,
    )
    return build_cohort_view(
        list(run_paths),
        phase=phase,
        price_column=price_column,
        frames=frames,
    )


# The per-run caches are what make a cohort affordable. Each entry is one run's
# GARCH(1,1) fit and its return series; adding a run to a selection then costs
# that one run rather than the whole cohort again, and a multi-asset run opened
# on its own has already paid for its diagnostics by the time it is compared.
@lru_cache(maxsize=512)
def _cached_run_diagnostics(
    run_path: Path,
    phase: str,
    price_column: str,
    archive_generation: tuple[tuple[int, int], ...],
) -> tuple[tuple[tuple[str, Any], ...], ...]:
    """Memoise one run's per-asset stylised-fact rows.

    Rows are returned as tuples of pairs rather than dictionaries so a caller
    cannot mutate the cached value in place; each caller rebuilds its own
    dictionaries from them.
    """

    from abm_analysis.statistics.diagnostics import run_asset_stylised_fact_diagnostics

    rows = run_asset_stylised_fact_diagnostics(
        run_path,
        phase=phase,
        price_column=price_column,
    )
    return tuple(tuple(row.items()) for row in rows)


@lru_cache(maxsize=512)
def _cached_run_return_series(
    run_path: Path,
    phase: str,
    price_column: str,
    archive_generation: tuple[tuple[int, int], ...],
) -> dict[str, pd.Series]:
    """Memoise one run's log-return series, keyed as the cohort layer keys them.

    The returned series are shared with every caller, so they are read-only by
    convention; the statistics functions that consume them never assign into a
    series they are given.
    """

    from abm_analysis.statistics.diagnostics import build_return_series_by_asset

    return build_return_series_by_asset(
        [run_path],
        phase=phase,
        price_column=price_column,
    )


def _archive_generation(run_path: Path) -> tuple[tuple[int, int], ...]:
    """Return a change stamp for every artefact the run view reads.

    Including it in the cache key means re-running a simulation into the same
    directory invalidates the memoised statistics, so the dashboard can never
    show numbers from a superseded archive. Every artefact that feeds the
    payload has to be in the stamp: ``config.json`` alone decides the asset
    universe, the primary asset, and the cross-asset reference correlation, so
    editing it must invalidate the cache just as re-running the model does.
    """

    from abm_analysis.archive.archives import resolve_artifact_path

    stamps: list[tuple[int, int]] = []
    for filename in CACHE_KEY_ARTEFACTS:
        artifact_path = resolve_artifact_path(run_path, filename)
        if artifact_path is None:
            stamps.append((0, 0))
            continue
        file_stat = artifact_path.stat()
        stamps.append((file_stat.st_mtime_ns, file_stat.st_size))
    return tuple(stamps)


# Cached payloads roughly doubled when the view gained a track per asset and
# the agent panel, so fewer of them are held.
@lru_cache(maxsize=16)
def _cached_run_view(
    run_path: Path,
    phase: str,
    price_column: str,
    archive_generation: tuple[tuple[int, int], ...],
) -> dict[str, Any]:
    """Memoise one run's statistics payload for the current file generation.

    The GARCH(1,1) fit behind the volatility-clustering verdict dominates the
    cost of opening a run, and the dashboard re-requests the same run whenever
    the reader switches back to it.
    """

    return build_run_view(run_path, phase=phase, price_column=price_column)


def _asset_version(path: Path) -> str:
    """Short content hash of one interface file, for cache-busting its URL."""

    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _plotly_bundle_path() -> Path | None:
    """Locate ``plotly.min.js`` inside the installed plotly distribution."""

    import plotly

    bundle_path = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    return bundle_path if bundle_path.is_file() else None
