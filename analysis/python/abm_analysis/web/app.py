"""FastAPI application serving the read-only run and statistics dashboard.

The application exposes three things: a catalogue of archived runs, the
statistics payload for one run, and the static single-page interface that
renders them. It never writes to ``data/`` and never starts a simulation, so
running it alongside an active experiment cannot disturb the archive.

The Plotly bundle is served from the installed ``plotly`` package rather than a
content-delivery network, so the dashboard works with no network connection and
its charts are drawn by exactly the library version pinned in
``requirements.txt`` — the same one that renders the static reports.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from abm_analysis.environment import configure_analysis_environment
from abm_analysis.web.catalogue import build_catalogue, resolve_run_path
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
    def read_index() -> FileResponse:
        """Serve the single-page interface."""

        return FileResponse(STATIC_DIRECTORY / "index.html", media_type="text/html")

    application.mount(
        "/static",
        StaticFiles(directory=STATIC_DIRECTORY),
        name="static",
    )

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


def _plotly_bundle_path() -> Path | None:
    """Locate ``plotly.min.js`` inside the installed plotly distribution."""

    import plotly

    bundle_path = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    return bundle_path if bundle_path.is_file() else None
