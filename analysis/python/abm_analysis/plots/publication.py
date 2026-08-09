"""Publication-quality Plotly styling for static thesis and journal figures."""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

from .common import COLOUR_SEQUENCE, REPORT_COLOURS

PUBLICATION_TEMPLATE = "abm_publication"

PUBLICATION_FONT_FAMILY = '"Times New Roman", "STIX Two Text", Georgia, serif'

# Kaleido maps 96 CSS px to one inch of physical page, so 672 px is a full
# 7.0 in LaTeX text width and px font sizes land on the page at 0.75x in pt
# (11 px base font ~= 8.25 pt).
PUBLICATION_WIDTH_PX = 672

# Reports lay figures out in a ~1100 px web panel; export heights preserve
# each figure's designed aspect ratio relative to that width.
_NOMINAL_WEB_PANEL_WIDTH_PX = 1100

pio.templates[PUBLICATION_TEMPLATE] = go.layout.Template(
    layout=go.Layout(
        colorway=COLOUR_SEQUENCE,
        font=dict(family=PUBLICATION_FONT_FAMILY, size=11, color=REPORT_COLOURS["ink"]),
        title=dict(font=dict(size=13, color=REPORT_COLOURS["graphite"])),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(
            bgcolor="#ffffff",
            bordercolor=REPORT_COLOURS["line"],
            borderwidth=1,
            font=dict(size=10),
            title=dict(font=dict(size=11)),
        ),
        margin=dict(l=52, r=12, t=48, b=58),
        xaxis=dict(
            automargin=True,
            gridcolor=REPORT_COLOURS["grid"],
            linecolor=REPORT_COLOURS["line"],
            tickcolor=REPORT_COLOURS["line"],
            tickfont=dict(size=10),
            ticks="outside",
            zerolinecolor=REPORT_COLOURS["line"],
        ),
        yaxis=dict(
            automargin=True,
            gridcolor=REPORT_COLOURS["grid"],
            linecolor=REPORT_COLOURS["line"],
            tickcolor=REPORT_COLOURS["line"],
            tickfont=dict(size=10),
            ticks="outside",
            zerolinecolor=REPORT_COLOURS["line"],
        ),
        annotationdefaults=dict(
            font=dict(color=REPORT_COLOURS["graphite"], family=PUBLICATION_FONT_FAMILY, size=11)
        ),
    )
)


def apply_publication_style(
    figure: go.Figure,
    *,
    width_px: int = PUBLICATION_WIDTH_PX,
) -> go.Figure:
    """Return a publication-styled deep copy of ``figure`` sized for print.

    By the time figures reach static export, ``_apply_report_theme`` has
    already written the web theme onto them as explicit layout properties,
    and explicit properties always beat templates — so this must copy the
    figure and explicitly re-override those same properties rather than
    merely switching the template.
    """

    styled = go.Figure(figure)
    styled.update_layout(
        template=PUBLICATION_TEMPLATE,
        width=width_px,
        height=_export_height(figure, width_px),
        font=dict(family=PUBLICATION_FONT_FAMILY, size=11, color=REPORT_COLOURS["ink"]),
        title=dict(font=dict(size=13, color=REPORT_COLOURS["graphite"])),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(
            bgcolor="#ffffff",
            bordercolor=REPORT_COLOURS["line"],
            borderwidth=1,
            font=dict(size=10),
            title=dict(font=dict(size=11)),
        ),
        margin=dict(l=52, r=12, t=48, b=58),
    )
    axis_style = dict(
        automargin=True,
        gridcolor=REPORT_COLOURS["grid"],
        linecolor=REPORT_COLOURS["line"],
        mirror=False,
        showline=True,
        tickcolor=REPORT_COLOURS["line"],
        tickfont=dict(size=10, family=PUBLICATION_FONT_FAMILY),
        ticks="outside",
        zerolinecolor=REPORT_COLOURS["line"],
    )
    styled.update_xaxes(**axis_style)
    styled.update_yaxes(**axis_style)
    return styled


def _export_height(figure: go.Figure, width_px: int) -> int:
    """Scale the web panel's designed aspect ratio down to the export width."""

    web_height = int(figure.layout.height or 480)
    scaled = round(width_px * web_height / _NOMINAL_WEB_PANEL_WIDTH_PX)
    return int(min(max(scaled, 300), round(width_px * 1.5)))
