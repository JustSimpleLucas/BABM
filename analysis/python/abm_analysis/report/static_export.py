"""Reliable Kaleido-backed export of publication-ready static figures."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

from abm_analysis.plots.publication import apply_publication_style

STATIC_EXPORT_FORMATS = ("png", "pdf", "svg")

# 300 DPI at Kaleido's 96 CSS px per inch.
PNG_EXPORT_SCALE = 300 / 96

_DISABLE_HINT = "or disable static figures with --no-export-images"

_engine_ready = False


class StaticExportUnavailableError(RuntimeError):
    """The Kaleido/Chrome rendering engine cannot produce static images."""


def parse_figure_formats(value: str) -> tuple[str, ...]:
    """Normalise a comma-separated format list, e.g. "png, pdf" -> ("png", "pdf")."""

    parts = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError(
            "At least one figure format is required "
            f"(supported: {', '.join(STATIC_EXPORT_FORMATS)})."
        )
    unknown = [part for part in parts if part not in STATIC_EXPORT_FORMATS]
    if unknown:
        raise ValueError(
            f"Unsupported figure format(s): {', '.join(unknown)}. "
            f"Supported: {', '.join(STATIC_EXPORT_FORMATS)}."
        )
    return tuple(dict.fromkeys(parts))


class StaticFigureExportError(RuntimeError):
    """One or more figures failed to export despite a working engine."""


def ensure_static_export_ready() -> None:
    """Verify the static-image engine can actually render, or raise.

    ``plotly.io.kaleido.kaleido_available()`` only proves the package
    imports; a real render is the only check that also proves a usable
    Chrome/Chromium exists, so this performs a tiny smoke render once per
    process before any report spends minutes on diagnostics.
    """

    global _engine_ready
    if _engine_ready:
        return
    try:
        import kaleido  # noqa: F401
    except ImportError as exc:
        raise StaticExportUnavailableError(
            "Static figure export needs the 'kaleido' package. Install the "
            "analysis dependencies (.venv/bin/pip install -r requirements.txt) "
            f"{_DISABLE_HINT}."
        ) from exc
    try:
        pio.to_image(go.Figure(), format="png", width=100, height=100)
    except Exception as exc:
        raise StaticExportUnavailableError(
            "Static figure export could not launch a rendering browser "
            f"({exc}). Install Google Chrome, fetch a private copy with "
            ".venv/bin/python -c \"import kaleido; kaleido.get_chrome_sync()\", "
            f"{_DISABLE_HINT}."
        ) from exc
    _engine_ready = True


def export_publication_figures(
    figure_dir: Path,
    figure_objects: dict[str, go.Figure],
    *,
    formats: tuple[str, ...] = STATIC_EXPORT_FORMATS,
) -> list[dict[str, object]]:
    """Export publication-styled copies of every figure in every format.

    All renders go through one ``plotly.io.write_images`` batch so the ~50
    images of a report share a single browser instance instead of paying
    Chrome start-up per file. If the batch fails, each figure is retried
    individually so failures are attributed to specific figures.
    """

    styled = {
        name: apply_publication_style(figure)
        for name, figure in figure_objects.items()
    }
    jobs = [
        (name, figure, figure_dir / f"{name}.{fmt}", fmt)
        for name, figure in styled.items()
        for fmt in formats
    ]

    failures: dict[str, str] = {}
    try:
        pio.write_images(
            fig=[figure for _, figure, _, _ in jobs],
            file=[file for _, _, file, _ in jobs],
            format=[fmt for _, _, _, fmt in jobs],
            scale=[PNG_EXPORT_SCALE if fmt == "png" else None for _, _, _, fmt in jobs],
        )
    except Exception:
        failures = _export_each(jobs)

    rows: list[dict[str, object]] = []
    for name in figure_objects:
        message = failures.get(name, "")
        row: dict[str, object] = {
            "figure_name": name,
            "export_status": "export_failed" if message else "exported",
            "export_message": message,
        }
        for fmt in formats:
            row[f"{fmt}_file"] = (
                "" if message else str(Path(figure_dir.name) / f"{name}.{fmt}")
            )
        rows.append(row)
    return rows


def _export_each(
    jobs: list[tuple[str, go.Figure, Path, str]],
) -> dict[str, str]:
    failures: dict[str, str] = {}
    for name, figure, file, fmt in jobs:
        if name in failures:
            continue
        try:
            figure.write_image(
                file,
                format=fmt,
                scale=PNG_EXPORT_SCALE if fmt == "png" else None,
            )
        except Exception as exc:
            failures[name] = str(exc)
    return failures
