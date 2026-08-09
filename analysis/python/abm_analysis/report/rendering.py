"""HTML rendering and table-preview helpers for static reports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from plotly.offline import get_plotlyjs

def _render_report(
    report_path: Path,
    *,
    title: str,
    meta_line: str,
    generated_at: str,
    key_metrics: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
    sections: list[dict[str, object]],
    appendices: list[dict[str, object]],
    evidence_title: str | None = None,
    evidence_intro: str | None = None,
    evidence_caption: str | None = None,
    evidence_fact_header: str | None = None,
) -> None:
    template_dir = Path(__file__).resolve().parent.parent / "templates"
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
    )
    template = environment.get_template("report.html.j2")
    html = template.render(
        title=title,
        meta_line=meta_line,
        generated_at=generated_at,
        key_metrics=key_metrics,
        evidence_rows=evidence_rows,
        plotly_js=get_plotlyjs(),
        sections=sections,
        appendices=appendices,
        # None falls back to the stylised-fact wording inside the template, so
        # existing run/comparison reports render unchanged.
        evidence_title=evidence_title,
        evidence_intro=evidence_intro,
        evidence_caption=evidence_caption,
        evidence_fact_header=evidence_fact_header,
    )
    report_path.write_text(html, encoding="utf-8")

def _table_preview(
    data: pd.DataFrame,
    max_rows: int = 30,
    hidden_columns: set[str] | None = None,
) -> str:
    if data.empty:
        return "<p class=\"empty-note\">No rows available.</p>"
    total_rows = len(data)
    preview = data.head(max_rows).copy()
    if hidden_columns:
        preview = preview.drop(columns=[column for column in hidden_columns if column in preview])
    table_html = preview.to_html(
        index=False,
        border=0,
        classes=["data-table"],
        na_rep="",
        escape=True,
    )
    if total_rows <= max_rows:
        return table_html
    note = (
        f'<p class="table-note">Showing first {max_rows:,} of {total_rows:,} rows. '
        "See the linked CSV export for the full table.</p>"
    )
    return note + table_html
