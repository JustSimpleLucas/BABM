from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from abm_analysis.archive.data import discover_run_directories
from abm_analysis.plots.common import REPORT_FONT_FAMILY, _apply_report_theme
from abm_analysis.plots.publication import (
    PUBLICATION_WIDTH_PX,
    apply_publication_style,
)
from abm_analysis.report import build_run_report
from abm_analysis.report import static_export
from abm_analysis.report.figures import _build_figure_index
from abm_analysis.report.static_export import (
    StaticExportUnavailableError,
    StaticFigureExportError,
    ensure_static_export_ready,
    export_publication_figures,
    parse_figure_formats,
)

from abm_test_helpers import make_synthetic_experiment


def _small_figure(height: int = 940) -> go.Figure:
    figure = go.Figure(go.Scatter(y=[1.0, 3.0, 2.0]))
    figure.update_layout(title="Test Panel", height=height)
    return figure


def test_apply_publication_style_returns_serif_copy_and_keeps_original() -> None:
    figure = _apply_report_theme(_small_figure(height=940))

    styled = apply_publication_style(figure)

    assert styled is not figure
    assert "serif" in styled.layout.font.family
    assert styled.layout.width == PUBLICATION_WIDTH_PX
    assert styled.layout.height == round(PUBLICATION_WIDTH_PX * 940 / 1100)
    assert styled.layout.paper_bgcolor == "#ffffff"
    assert styled.layout.plot_bgcolor == "#ffffff"
    # The original keeps its web styling for the HTML report.
    assert figure.layout.font.family == REPORT_FONT_FAMILY
    assert figure.layout.width is None


def test_figure_index_without_export_keeps_html_only_schema(tmp_path: Path) -> None:
    figure_index = _build_figure_index(
        tmp_path,
        {"panel": _small_figure()},
        export_images=False,
    )

    assert list(figure_index["export_status"]) == ["html_only"]
    assert list(figure_index["png_file"]) == [""]
    assert list(figure_index["pdf_file"]) == [""]
    assert list(figure_index["svg_file"]) == [""]


def test_export_uses_one_write_images_batch(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_write_images(*, fig, file, format, scale):
        calls.append({"fig": fig, "file": file, "format": format, "scale": scale})
        for path in file:
            Path(path).touch()

    monkeypatch.setattr("plotly.io.write_images", fake_write_images)

    figure_index = _build_figure_index(
        tmp_path,
        {"alpha": _small_figure(), "beta": _small_figure()},
        export_images=True,
    )

    assert len(calls) == 1
    assert len(calls[0]["file"]) == 6  # 2 figures x (png, pdf, svg)
    assert set(figure_index["export_status"]) == {"exported"}
    assert list(figure_index["pdf_file"]) == ["figures/alpha.pdf", "figures/beta.pdf"]
    assert (tmp_path / "figures" / "alpha.png").is_file()


def test_export_failure_keeps_html_report_and_raises(monkeypatch, tmp_path: Path) -> None:
    experiment_dir = make_synthetic_experiment(tmp_path)
    run_dir = discover_run_directories(experiment_dir)[0]
    report_dir = tmp_path / "run_report"

    def raise_batch(**kwargs):
        raise RuntimeError("batch boom")

    def raise_single(self, *args, **kwargs):
        raise RuntimeError("kaleido exploded")

    monkeypatch.setattr("abm_analysis.report.run.ensure_static_export_ready", lambda: None)
    monkeypatch.setattr("plotly.io.write_images", raise_batch)
    monkeypatch.setattr(go.Figure, "write_image", raise_single)

    with pytest.raises(StaticFigureExportError, match="kaleido exploded"):
        build_run_report(run_dir, output_dir=report_dir, export_images=True)

    assert (report_dir / "index.html").is_file()
    figure_index = pd.read_csv(report_dir / "figure_index.csv")
    assert set(figure_index["export_status"]) == {"export_failed"}
    assert figure_index["export_message"].str.contains("kaleido exploded").all()


def test_engine_check_failure_mentions_recovery_steps(monkeypatch) -> None:
    def raise_render(*args, **kwargs):
        raise RuntimeError("no usable browser")

    monkeypatch.setattr(static_export, "_engine_ready", False)
    monkeypatch.setattr("plotly.io.to_image", raise_render)

    with pytest.raises(StaticExportUnavailableError) as excinfo:
        ensure_static_export_ready()

    message = str(excinfo.value)
    assert "get_chrome_sync" in message
    assert "--no-export-images" in message


def test_parse_figure_formats_normalises_and_deduplicates() -> None:
    assert parse_figure_formats("png, pdf") == ("png", "pdf")
    assert parse_figure_formats("PDF,pdf,svg") == ("pdf", "svg")


def test_parse_figure_formats_rejects_unknown_and_empty() -> None:
    with pytest.raises(ValueError, match="Unsupported figure format"):
        parse_figure_formats("png,tiff")
    with pytest.raises(ValueError, match="At least one figure format"):
        parse_figure_formats(" , ")


def test_figure_index_respects_format_selection(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_write_images(*, fig, file, format, scale):
        calls.append({"file": file, "format": format})
        for path in file:
            Path(path).touch()

    monkeypatch.setattr("plotly.io.write_images", fake_write_images)

    figure_index = _build_figure_index(
        tmp_path,
        {"alpha": _small_figure()},
        export_images=True,
        figure_formats=("png", "pdf"),
    )

    assert calls[0]["format"] == ["png", "pdf"]
    assert list(figure_index["png_file"]) == ["figures/alpha.png"]
    assert list(figure_index["pdf_file"]) == ["figures/alpha.pdf"]
    assert list(figure_index["svg_file"]) == [""]
    assert not (tmp_path / "figures" / "alpha.svg").exists()


def test_cli_parses_figure_formats() -> None:
    from abm_analysis.commands import build_parser

    parser = build_parser()
    args = parser.parse_args(["robustness", "some_dir", "--figure-formats", "png,pdf"])
    assert args.figure_formats == ("png", "pdf")

    defaults = parser.parse_args(["robustness", "some_dir"])
    assert defaults.figure_formats == ("png", "pdf", "svg")

    with pytest.raises(SystemExit):
        parser.parse_args(["robustness", "some_dir", "--figure-formats", "png,tiff"])


def test_real_kaleido_export_produces_valid_files(tmp_path: Path) -> None:
    try:
        ensure_static_export_ready()
    except StaticExportUnavailableError as exc:
        pytest.skip(f"Kaleido/Chrome unavailable: {exc}")

    figure_dir = tmp_path / "figures"
    figure_dir.mkdir()
    rows = export_publication_figures(figure_dir, {"tiny": _small_figure(height=480)})

    assert rows[0]["export_status"] == "exported"
    assert (figure_dir / "tiny.png").read_bytes()[:4] == b"\x89PNG"
    assert (figure_dir / "tiny.pdf").read_bytes()[:5] == b"%PDF-"
    assert b"<svg" in (figure_dir / "tiny.svg").read_bytes()[:200]
