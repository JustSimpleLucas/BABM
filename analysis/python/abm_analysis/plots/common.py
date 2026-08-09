"""Shared Plotly theme and helpers for ABM report figures."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

REPORT_FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'

REPORT_COLOURS = {
    "graphite": "#17212f",
    "ink": "#202b3a",
    "muted": "#667085",
    "line": "#d8dee8",
    "grid": "#e7ecf3",
    "panel": "#ffffff",
    "plot": "#fbfcfe",
    "teal": "#167c80",
    "blue": "#215d9c",
    "amber": "#c68424",
    "red": "#aa4545",
    "green": "#2f7d51",
}

PLOT_TEMPLATE = "abm_executive_report"

COLOUR_SEQUENCE = [
    REPORT_COLOURS["blue"],
    REPORT_COLOURS["teal"],
    REPORT_COLOURS["amber"],
    REPORT_COLOURS["red"],
    REPORT_COLOURS["green"],
    "#52677a",
    "#7a5f99",
    "#b05f34",
]

HEATMAP_COLOUR_SCALE = [
    [0.00, "#f8fafc"],
    [0.22, "#a8c7d7"],
    [0.48, REPORT_COLOURS["teal"]],
    [0.74, REPORT_COLOURS["amber"]],
    [1.00, REPORT_COLOURS["red"]],
]
pio.templates[PLOT_TEMPLATE] = go.layout.Template(
    layout=go.Layout(
        colorway=COLOUR_SEQUENCE,
        font=dict(family=REPORT_FONT_FAMILY, size=12, color=REPORT_COLOURS["ink"]),
        title=dict(font=dict(size=15, color=REPORT_COLOURS["graphite"])),
        paper_bgcolor=REPORT_COLOURS["panel"],
        plot_bgcolor=REPORT_COLOURS["plot"],
        hoverlabel=dict(
            bgcolor=REPORT_COLOURS["graphite"],
            bordercolor=REPORT_COLOURS["graphite"],
            font=dict(color="#ffffff", family=REPORT_FONT_FAMILY, size=12),
        ),
        legend=dict(
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor=REPORT_COLOURS["line"],
            borderwidth=1,
            font=dict(size=11),
            title=dict(font=dict(size=12)),
        ),
        margin=dict(l=64, r=30, t=78, b=64),
        xaxis=dict(
            automargin=True,
            gridcolor=REPORT_COLOURS["grid"],
            linecolor=REPORT_COLOURS["line"],
            tickcolor=REPORT_COLOURS["line"],
            ticks="outside",
            zerolinecolor=REPORT_COLOURS["line"],
        ),
        yaxis=dict(
            automargin=True,
            gridcolor=REPORT_COLOURS["grid"],
            linecolor=REPORT_COLOURS["line"],
            tickcolor=REPORT_COLOURS["line"],
            ticks="outside",
            zerolinecolor=REPORT_COLOURS["line"],
        ),
        annotationdefaults=dict(
            font=dict(color=REPORT_COLOURS["graphite"], family=REPORT_FONT_FAMILY, size=12)
        ),
    )
)

AGENT_STRATEGY_COLUMN_CANDIDATES = ("current_strategy_type", "initial_strategy_type")

AGENT_SUMMARY_METRICS = [
    "final_wealth",
    "final_cash",
    "final_stock",
    "wealth_change",
    "number_of_trades",
    "traded_volume",
    "average_entry_price",
    "recent_peak_wealth",
    "last_prospect_reference_point",
]

def build_simulation_labels(run_ids: list[str]) -> dict[str, str]:
    """Return short data labels for long reproducible run identifiers."""

    return {
        str(run_id): f"Data {index}"
        for index, run_id in enumerate(run_ids, start=1)
    }

def select_display_run_ids(runs_index: pd.DataFrame, max_runs: int = 8) -> list[str]:
    """Choose a readable subset for dense line charts."""

    if runs_index.empty or "run_id" not in runs_index.columns:
        return []
    sortable = runs_index.copy()
    sort_column = "created_at_local" if "created_at_local" in sortable.columns else "run_id"
    sortable = sortable.sort_values(sort_column, na_position="last")
    return sortable["run_id"].astype(str).tail(max_runs).tolist()

_FIGURE_ID_COUNTER = itertools.count()

def figure_to_html(figure: go.Figure) -> str:
    """Return a lazily-rendered Plotly placeholder that defers drawing until scrolled into view.

    Reports embed 15-25 large figures on one page; calling ``figure.to_html()``
    for each one draws every chart eagerly on load, which is what made big
    comparison reports (tens of megabytes) slow to paint and scroll. Instead we
    ship the figure spec as inert JSON and let the report's shared
    IntersectionObserver script (see report.html.j2) call ``Plotly.newPlot``
    only once a panel approaches the viewport. Using a counter rather than a
    random id keeps regenerated reports byte-for-byte diffable in git.
    """

    _apply_report_theme(figure)
    div_id = f"plotly-fig-{next(_FIGURE_ID_COUNTER)}"
    height = figure.layout.height or 480
    # Guard against a stray "</script>" inside figure text (titles, hover text)
    # from prematurely closing the inline JSON <script> tag.
    figure_json = figure.to_json().replace("</", "<\\/")
    return (
        f'<div class="plotly-lazy" data-plot-id="{div_id}">'
        f'<div id="{div_id}" class="plotly-graph-div" style="height:{height}px;"></div>'
        f'<script type="application/json" class="plotly-spec">{figure_json}</script>'
        f"</div>"
    )

def _apply_report_theme(figure: go.Figure) -> go.Figure:
    """Apply final report-wide decoration to all axes and legends.

    Plotly templates cover the primary axes, while subplot figures may create
    additional numbered axes. This pass keeps every generated panel consistent
    without altering the underlying data traces or diagnostics.
    """

    figure.update_layout(
        template=PLOT_TEMPLATE,
        font=dict(family=REPORT_FONT_FAMILY, color=REPORT_COLOURS["ink"]),
        paper_bgcolor=REPORT_COLOURS["panel"],
        plot_bgcolor=REPORT_COLOURS["plot"],
        legend=dict(
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor=REPORT_COLOURS["line"],
            borderwidth=1,
            font=dict(size=11),
            title=dict(font=dict(size=12)),
        ),
    )
    figure.update_xaxes(
        automargin=True,
        gridcolor=REPORT_COLOURS["grid"],
        linecolor=REPORT_COLOURS["line"],
        mirror=False,
        showline=True,
        tickcolor=REPORT_COLOURS["line"],
        ticks="outside",
        zerolinecolor=REPORT_COLOURS["line"],
    )
    figure.update_yaxes(
        automargin=True,
        gridcolor=REPORT_COLOURS["grid"],
        linecolor=REPORT_COLOURS["line"],
        mirror=False,
        showline=True,
        tickcolor=REPORT_COLOURS["line"],
        ticks="outside",
        zerolinecolor=REPORT_COLOURS["line"],
    )
    return figure

def _finite_array(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]

def _condition_labels(seed_summary: pd.DataFrame) -> list[str]:
    if "condition_id" in seed_summary.columns:
        labels = seed_summary["condition_id"].astype(str).tolist()
    else:
        labels = [f"Condition {index}" for index in range(1, len(seed_summary) + 1)]
    return [_display_condition_label(label) for label in labels]

def _display_condition_label(label: str) -> str:
    """Render a condition identifier for chart axes.

    Short ``condition_<n>`` identifiers become "Condition <n>"; any other
    value (for example a legacy ``key=value`` listing) is truncated so long
    strings cannot blow up the axis layout.
    """

    suffix = label.removeprefix("condition_")
    if suffix != label and suffix.isdigit():
        return f"Condition {suffix}"
    return label if len(label) <= 80 else f"{label[:77]}..."

def _time_axis(time_series: pd.DataFrame) -> pd.Series:
    if "simulation_step" in time_series.columns:
        values = pd.to_numeric(time_series["simulation_step"], errors="coerce")
        if values.notna().any():
            return values.fillna(0)
    if "row_index" in time_series.columns:
        return time_series["row_index"]
    return pd.Series(range(len(time_series)))

def _simulation_phase(time_series: pd.DataFrame) -> pd.DataFrame:
    return _analysis_phase(time_series, "simulation")

def _analysis_phase(time_series: pd.DataFrame, phase: str) -> pd.DataFrame:
    if "phase" not in time_series.columns:
        return time_series
    requested_phase = phase.lower()
    if requested_phase == "all":
        return time_series
    phase_rows = time_series[
        time_series["phase"].astype(str).str.lower() == requested_phase
    ]
    return phase_rows if not phase_rows.empty else time_series

def _agent_strategy_column(agents: pd.DataFrame) -> str | None:
    for column in AGENT_STRATEGY_COLUMN_CANDIDATES:
        if column in agents.columns:
            return column
    return None

def _run_label(run_id: str, run_labels: dict[str, str] | None = None) -> str:
    if run_labels is None:
        return str(run_id)
    return run_labels.get(str(run_id), str(run_id))

def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=16),
    )
    figure.update_layout(template=PLOT_TEMPLATE, height=320)
    return figure
