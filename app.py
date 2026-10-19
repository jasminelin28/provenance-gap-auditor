"""Provenance Gap Auditor - web interface.

Run locally:  python app.py   then open http://127.0.0.1:8050
"""

import os

import dash
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html

from provenance_auditor import config
from provenance_auditor.llm_client import run_budget, spend_cap_exceeded
from provenance_auditor.orchestrator import run_audit, summarise_usage
from provenance_auditor.schema import audit_result, gap_severity, risk_verdict
from provenance_auditor.tools.document_reader import extract_text
from provenance_auditor.tools.geography import build_journey

# Clear, saturated section colours on a white page. Each section owns one
# colour, used by its rule, its icon and its heading, so the eye can tell the
# sections apart without boxes or shadows.
ink = "#18181b"
muted = "#52525b"
faint = "#71717a"
rule = "#d4d4d8"

section_colour = {
    "score": "#4f46e5",
    "facts": "#b45309",
    "artwork": "#a21caf",
    "chain": "#0f766e",
    "gaps": "#be123c",
    "map": "#1d4ed8",
    "crossref": "#6d28d9",
    "shield": "#0369a1",
}

# A pale wash of each section's own colour, so the boxes read as a set rather
# than as eight unrelated panels. Square corners throughout.
section_tint = {
    "score": "#f5f3ff",
    "facts": "#fffbeb",
    "artwork": "#fdf4ff",
    "chain": "#f0fdfa",
    "gaps": "#fff1f2",
    "map": "#eff6ff",
    "crossref": "#faf5ff",
    "shield": "#f0f9ff",
}

verdict_presentation = {
    risk_verdict.clear: ("CLEAR", "#15803d", "#f0fdf4"),
    risk_verdict.review: ("NEEDS REVIEW", "#b45309", "#fffbeb"),
    risk_verdict.high_risk: ("HIGH RISK", "#be123c", "#fff1f2"),
}

severity_colour = {
    gap_severity.high: "#be123c",
    gap_severity.medium: "#b45309",
    gap_severity.low: "#0f766e",
}

sample_directory = config.repo_root / "samples"


def _load_sample(name: str) -> str:
    path = sample_directory / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


app = dash.Dash(__name__, title="Provenance Gap Auditor")
server = app.server  # named for gunicorn when hosted


# --------------------------------------------------------------------------
# building blocks
# --------------------------------------------------------------------------


def section(key: str, heading: str, children, note: str = ""):
    """A titled box in the section's own colour. Square corners, no shadow."""
    colour = section_colour[key]
    return html.Section(
        style={
            "border": f"1.5px solid {colour}",
            "borderTop": f"4px solid {colour}",
            "backgroundColor": "#ffffff",
            "marginBottom": "26px",
        },
        children=[
            # Tinted header band, so the box is legible at a glance.
            html.Div(
                style={
                    "display": "flex", "alignItems": "center", "gap": "9px",
                    "backgroundColor": section_tint[key],
                    "padding": "11px 18px",
                    "borderBottom": f"1px solid {colour}33",
                },
                children=[
                    html.Img(src=f"/assets/icons/{key}.svg", width="19", height="19",
                             alt="", style={"display": "block"}),
                    html.H2(heading, style={
                        "margin": "0", "fontSize": "13.5px", "fontWeight": "700",
                        "letterSpacing": "0.9px", "textTransform": "uppercase",
                        "color": colour,
                    }),
                ],
            ),
            html.Div(
                style={"padding": "17px 18px 20px"},
                children=[
                    html.P(note, style={"margin": "0 0 13px", "fontSize": "13px",
                                        "color": faint}) if note else None,
                    html.Div(children),
                ],
            ),
        ],
    )


def _painter_scene():
    """A painter filling in a canvas, shown while an audit runs."""
    return html.Div(
        [
            html.Img(src="/assets/painter.svg", className="painter_scene",
                     alt="A painter filling in a canvas while the audit runs"),
            html.Div("Reading the chain, checking the names...",
                     className="painter_caption"),
        ],
        style={"textAlign": "center", "padding": "30px 0 36px"},
    )


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------

app.layout = html.Div(
    style={
        "backgroundColor": "#ffffff",
        "minHeight": "100vh",
        "fontFamily": "'Helvetica Neue', Helvetica, Arial, sans-serif",
        "color": ink,
        "padding": "34px 20px 70px",
    },
    children=[
        html.Div(
            style={"maxWidth": "1120px", "margin": "0 auto"},
            children=[
                html.H1("Provenance Gap Auditor", style={
                    "fontSize": "27px", "margin": "0 0 26px",
                    "fontWeight": "700", "letterSpacing": "-0.4px",
                }),

                # input left, artwork + facts right
                html.Div(
                    style={"display": "flex", "gap": "30px", "alignItems": "flex-start",
                           "flexWrap": "wrap"},
                    children=[
                        html.Div(
                            style={"flex": "1 1 540px", "minWidth": "340px"},
                            children=[
                                dcc.Textarea(
                                    id="record_input",
                                    value=_load_sample("klimt_adele.txt"),
                                    placeholder="Paste the provenance section of a catalogue entry or lot page...",
                                    style={
                                        "width": "100%", "height": "212px",
                                        "padding": "13px",
                                        "border": f"1px solid {rule}",
                                        "borderRadius": "0", "fontSize": "13.5px",
                                        "fontFamily": "ui-monospace, Consolas, monospace",
                                        "lineHeight": "1.6", "color": ink,
                                        "backgroundColor": "#ffffff", "resize": "vertical",
                                    },
                                ),
                                html.Div(
                                    style={"display": "flex", "alignItems": "center",
                                           "gap": "16px", "marginTop": "13px",
                                           "flexWrap": "wrap"},
                                    children=[
                                        html.Button("Audit this record", id="audit_button",
                                                    n_clicks=0, style={
                                            "backgroundColor": section_colour["score"],
                                            "color": "#ffffff", "border": "none",
                                            "borderRadius": "0", "padding": "12px 26px",
                                            "fontSize": "14px", "fontWeight": "600",
                                            "fontFamily": "inherit", "cursor": "pointer",
                                            "letterSpacing": "0.3px",
                                        }),
                                        dcc.Upload(
                                            id="file_upload",
                                            children=html.Span(
                                                "or upload a PDF / text file",
                                                style={"color": section_colour["score"],
                                                       "fontSize": "13.5px",
                                                       "cursor": "pointer",
                                                       "textDecoration": "underline"},
                                            ),
                                            multiple=False,
                                        ),
                                        html.Span(id="upload_status", style={
                                            "fontSize": "12.5px", "color": faint}),
                                    ],
                                ),
                                dcc.Loading(
                                    id="loading",
                                    custom_spinner=_painter_scene(),
                                    delay_show=150,
                                    children=html.Div(
                                        id="results",
                                        style={"marginTop": "30px"},
                                    ),
                                ),
                            ],
                        ),
                        # Right column: the work, its facts, the map, and the
                        # detail that opens when a flagged row is clicked. It
                        # sticks to the top so the detail stays in view while
                        # the reader scrolls the chain on the left.
                        html.Div(
                            style={"flex": "0 1 336px", "minWidth": "290px",
                                   "position": "sticky", "top": "18px"},
                            children=[
                                html.Div(id="work_panel"),
                            ],
                        ),
                    ],
                ),

                html.Div(
                    style={"marginTop": "40px", "paddingTop": "16px",
                           "borderTop": f"1px solid {rule}", "fontSize": "12px",
                           "color": faint, "lineHeight": "1.7"},
                    children=[
                        html.Span(f"Model: {config.model_name}. "),
                        html.Span("This tool flags gaps for a human researcher. It is "
                                  "not a title opinion, and a clear result is not "
                                  "proof of clean title."),
                    ],
                ),
            ],
        )
    ],
)


# --------------------------------------------------------------------------
# artwork + facts panel
# --------------------------------------------------------------------------


def _fact_row(label: str, value: str):
    return html.Div(
        style={"display": "flex", "gap": "10px", "padding": "7px 0",
               "borderBottom": f"1px solid #f4f4f5", "fontSize": "13px"},
        children=[
            html.Span(label, style={"minWidth": "74px", "color": faint,
                                    "fontSize": "11px", "fontWeight": "700",
                                    "letterSpacing": "0.6px",
                                    "textTransform": "uppercase",
                                    "paddingTop": "1px"}),
            html.Span(value, style={"color": ink, "flex": "1"}),
        ],
    )


def _work_panel(result: audit_result):
    """The picture of the work and a specifications box, shown top right."""
    work = result.work
    blocks = []

    if work.image_url:
        caption = (
            "The work, from Wikidata."
            if work.match_kind == "work"
            else "The work was not found in Wikidata. Showing the artist instead."
        )
        blocks.append(html.Div([
            html.Img(src=work.image_url, alt=work.title or "the work", style={
                "width": "100%", "display": "block",
                "border": f"1px solid {rule}"}),
            html.Div(caption, style={"fontSize": "11.5px", "color": faint,
                                     "marginTop": "6px", "fontStyle": "italic"}),
        ], style={"marginBottom": "22px"}))

    facts = []
    if work.title:
        facts.append(_fact_row("Title", work.title))
    if work.artist:
        facts.append(_fact_row("Artist", work.artist))
    if work.year_created:
        facts.append(_fact_row("Created", str(work.year_created)))
    if work.medium:
        facts.append(_fact_row("Medium", work.medium))

    facts.append(_fact_row("Owners", f"{len(result.events)} in the chain"))
    span = [e.start_year for e in result.events if e.start_year]
    ends = [e.end_year for e in result.events if e.end_year]
    if span or ends:
        facts.append(_fact_row(
            "Covers", f"{min(span + ends)} to {max(span + ends)}"))
    if work.sitelink_count:
        facts.append(_fact_row(
            "Profile", f"{work.sitelink_count} Wikipedia editions"))
    if work.wikidata_id:
        facts.append(_fact_row("Wikidata", work.wikidata_id))

    blocks.append(section("facts", "The work", facts))

    # The journey sits directly under the picture, so the object and where it
    # went read as one unit.
    if result.events:
        blocks.append(section("map", "Where the work travelled",
                              _journey_map(result)))
    return blocks


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------


def _score_dial(result: audit_result):
    """The headline number, with a bar rather than a gauge so it reads fast."""
    score = result.score
    label, colour, tint = verdict_presentation[result.verdict]

    return html.Div(
        style={"display": "flex", "gap": "28px", "alignItems": "flex-start",
               "flexWrap": "wrap"},
        children=[
            html.Div(style={"minWidth": "132px"}, children=[
                html.Div([
                    html.Span(str(score.value), style={
                        "fontSize": "54px", "fontWeight": "800",
                        "color": colour, "lineHeight": "1"}),
                    html.Span(" / 100", style={"fontSize": "15px",
                                               "color": faint, "fontWeight": "600"}),
                ]),
                html.Div(score.band, style={"fontSize": "13px", "fontWeight": "700",
                                            "color": colour, "marginTop": "4px"}),
                html.Div("provenance confidence", style={
                    "fontSize": "11px", "color": faint, "marginTop": "2px",
                    "letterSpacing": "0.4px"}),
            ]),
            html.Div(style={"flex": "1 1 330px"}, children=[
                html.Div(style={"display": "flex", "alignItems": "center",
                                "gap": "10px", "marginBottom": "10px"}, children=[
                    html.Span(label, style={
                        "backgroundColor": tint, "color": colour,
                        "border": f"1.5px solid {colour}", "padding": "4px 11px",
                        "fontSize": "11.5px", "fontWeight": "800",
                        "letterSpacing": "0.9px"}),
                    html.Span(f"{len(result.gaps)} gap(s) found",
                              style={"fontSize": "13px", "color": muted}),
                ]),
                # The bar: filled portion is the score.
                html.Div(style={"height": "9px", "backgroundColor": "#f4f4f5",
                                "width": "100%"}, children=[
                    html.Div(style={"height": "9px", "backgroundColor": colour,
                                    "width": f"{score.value}%"}),
                ]),
                html.Div(result.reasoning, style={
                    "marginTop": "14px", "fontSize": "14.5px", "lineHeight": "1.68",
                    "whiteSpace": "pre-wrap", "color": ink}),
            ]),
        ],
    )


def _chain_summary(result: audit_result):
    """A one-line reading of the chain, above all the detail."""
    events = result.events
    if not events:
        return html.Div("No ownership chain could be read from this record.",
                        style={"fontSize": "14px", "color": muted})

    named = [e for e in events if not e.is_vague]
    vague = len(events) - len(named)
    years = [y for e in events for y in (e.start_year, e.end_year) if y]
    places = []
    for event in events:
        if event.location and event.location not in places:
            places.append(event.location)

    pieces = [
        f"{len(events)} owners",
        f"{vague} unnamed" if vague else "all named",
    ]
    if years:
        pieces.append(f"{min(years)} to {max(years)}")
    if places:
        pieces.append(" to ".join(places[:4]) + ("..." if len(places) > 4 else ""))

    return html.Div([
        html.Div(" | ".join(pieces), style={
            "fontSize": "15px", "fontWeight": "600", "marginBottom": "10px"}),
        html.Div(
            _headline_finding(result),
            style={"fontSize": "14px", "color": muted, "lineHeight": "1.65"},
        ),
    ])


def _headline_finding(result: audit_result) -> str:
    """The single thing a reader should take away."""
    red = sorted({h.matched_label for h in result.crossref_hits if h.is_red_flag})
    if red:
        return (f"The chain includes {', '.join(red)}, recorded in the app's "
                "red-flag table of Nazi-era dealers and bodies.")
    high = [g for g in result.gaps if g.severity is gap_severity.high]
    if high:
        return high[0].description
    if result.gaps:
        return result.gaps[0].description
    return "No gaps were found by the rule checks."


# --------------------------------------------------------------------------
# map
# --------------------------------------------------------------------------


def _journey_map(result: audit_result):
    stops, unresolved = build_journey(result.events)

    if not stops:
        message = "No locations in this record could be placed on a map."
        if unresolved:
            message += " Unrecognised places: " + ", ".join(unresolved) + "."
        return html.Div(message, style={"fontSize": "14px", "color": muted})

    gap_indexes = {i for gap in result.gaps for i in gap.related_event_indexes}
    colour = section_colour["map"]

    latitudes = [s["latitude"] for s in stops]
    longitudes = [s["longitude"] for s in stops]

    figure = go.Figure()

    # The route between consecutive stops.
    if len(stops) > 1:
        figure.add_trace(go.Scattergeo(
            lat=latitudes, lon=longitudes, mode="lines",
            line=dict(width=2, color=colour), opacity=0.55,
            hoverinfo="skip", showlegend=False,
        ))

    # The stops themselves, flagged red where a gap touches them.
    marker_colours = [
        "#be123c" if set(s["event_indexes"]) & gap_indexes else colour
        for s in stops
    ]
    labels = []
    for index, stop in enumerate(stops, start=1):
        owners = ", ".join(stop["owners"])
        years = "-".join(str(y) if y else "?"
                         for y in (stop["year_from"], stop["year_to"]))
        labels.append(f"<b>{index}. {stop['place']}</b><br>{owners}<br>{years}")

    figure.add_trace(go.Scattergeo(
        lat=latitudes, lon=longitudes, mode="markers+text",
        marker=dict(size=13, color=marker_colours,
                    line=dict(width=2, color="#ffffff")),
        text=[str(i) for i in range(1, len(stops) + 1)],
        textfont=dict(color="#ffffff", size=9, family="Arial Black"),
        textposition="middle center",
        hovertext=labels, hoverinfo="text", showlegend=False,
    ))

    # Frame the map on the places actually used, with a margin.
    # Pad the latitude range against the longitude span as well, so a
    # transatlantic journey does not render as a thin letterboxed strip.
    longitude_span = max(longitudes) - min(longitudes)
    latitude_pad = max((max(latitudes) - min(latitudes)) * 0.45,
                       longitude_span * 0.22, 6)
    longitude_pad = max(longitude_span * 0.18, 6)

    figure.update_geos(
        projection_type="natural earth",
        showland=True, landcolor="#f4f4f5",
        showocean=True, oceancolor="#ffffff",
        showcountries=True, countrycolor="#d4d4d8",
        coastlinecolor="#d4d4d8", coastlinewidth=0.7,
        lataxis_range=[min(latitudes) - latitude_pad, max(latitudes) + latitude_pad],
        lonaxis_range=[min(longitudes) - longitude_pad, max(longitudes) + longitude_pad],
    )
    figure.update_layout(
        margin=dict(l=0, r=0, t=0, b=0), height=430,
        paper_bgcolor="#ffffff", dragmode=False,
    )

    if len(stops) == 1:
        caption_parts = [
            f"The record places the work in {stops[0]['place']} throughout. "
            "No movement is described."
        ]
    else:
        caption_parts = [
            " then ".join(f"{i}. {s['place']}" for i, s in enumerate(stops, start=1))
        ]
    if unresolved:
        caption_parts.append(
            "Not mapped, because the place could not be identified: "
            + ", ".join(unresolved) + ".")

    return html.Div([
        dcc.Graph(figure=figure, config={"displayModeBar": False,
                                         "scrollZoom": False,
                                         "staticPlot": False}),
        html.Div(caption_parts[0], style={"fontSize": "13px", "color": ink,
                                          "marginTop": "10px",
                                          "fontWeight": "600"}),
        *[html.Div(part, style={"fontSize": "12.5px", "color": faint,
                                "marginTop": "5px"})
          for part in caption_parts[1:]],
        html.Div("Red marks a stop involved in a gap. Places come from a "
                 "built-in table of art-trade cities, not a geocoding service.",
                 style={"fontSize": "11.5px", "color": faint, "marginTop": "8px",
                        "fontStyle": "italic"}),
    ])


# --------------------------------------------------------------------------
# detail blocks
# --------------------------------------------------------------------------


def _chain_rows(result: audit_result):
    gap_indexes = {i for gap in result.gaps for i in gap.related_event_indexes}
    rows = []
    for index, event in enumerate(result.events):
        flagged = index in gap_indexes
        years = " - ".join(str(y) if y else "?"
                           for y in (event.start_year, event.end_year))
        meta = event.role.value.replace("_", " ")
        if event.location:
            meta += f"  |  {event.location}"
        if event.method.value != "unknown":
            meta += f"  |  {event.method.value.replace('_', ' ')}"

        inner = [
            html.Span(years, style={
                "minWidth": "100px", "color": faint, "fontSize": "12.5px",
                "fontFamily": "ui-monospace, Consolas, monospace",
                "paddingTop": "2px", "textAlign": "left"}),
            html.Div([
                html.Div(event.owner_name, style={
                    "fontWeight": "400" if event.is_vague else "700",
                    "fontStyle": "italic" if event.is_vague else "normal",
                    "fontSize": "14.5px", "textAlign": "left"}),
                html.Div(meta, style={"color": faint, "fontSize": "12.5px",
                                      "marginTop": "2px", "textAlign": "left"}),
            ], style={"flex": "1"}),
        ]

        shared = {
            "display": "flex", "gap": "16px", "padding": "11px 13px",
            "borderLeft": f"3px solid {'#be123c' if flagged else rule}",
            "backgroundColor": "#fff1f2" if flagged else "#ffffff",
            "marginBottom": "4px", "width": "100%", "alignItems": "flex-start",
        }

        if flagged:
            # Only flagged rows open: a clean row has nothing to show. A native
            # <details> keeps the expansion instant and server-free, so opening
            # a row costs no round trip and no tokens.
            inner.append(html.Span("View", className="chain_row_toggle", style={
                "color": "#be123c", "fontSize": "11.5px", "fontWeight": "700",
                "letterSpacing": "0.5px", "whiteSpace": "nowrap",
                "paddingTop": "3px"}))
            rows.append(html.Details(
                className="chain_row_details",
                style={"marginBottom": "4px",
                       "borderLeft": "3px solid #be123c",
                       "backgroundColor": "#fff1f2"},
                children=[
                    html.Summary(
                        html.Div(inner, style={**shared, "marginBottom": "0",
                                               "borderLeft": "none"}),
                        className="chain_row_summary",
                    ),
                    html.Div(
                        _owner_detail(result, index, event),
                        style={"padding": "0 15px 16px 15px",
                               "borderTop": "1px solid #fecdd3"},
                    ),
                ],
            ))
        else:
            rows.append(html.Div(inner, style=shared))
    return rows


def _owner_detail(result: audit_result, index: int, event):
    """The gaps and database matches for one owner, shown inside its own row."""
    related = [gap for gap in result.gaps if index in gap.related_event_indexes]
    owner_key = event.owner_name.strip().lower()
    matches = [hit for hit in result.crossref_hits
               if hit.owner_name.strip().lower() == owner_key]

    body = [html.Div("GAPS (" + str(len(related)) + ")", style={
        "fontSize": "10.5px", "fontWeight": "800", "letterSpacing": "0.8px",
        "color": "#be123c", "margin": "14px 0 8px"})]

    if related:
        for gap in related:
            colour = severity_colour[gap.severity]
            body.append(html.Div([
                html.Span(gap.severity.value.upper(), style={
                    "color": "#ffffff", "backgroundColor": colour,
                    "fontSize": "9.5px", "fontWeight": "800", "padding": "2px 6px",
                    "letterSpacing": "0.6px"}),
                html.Span("  " + gap.kind.value.replace("_", " "), style={
                    "color": faint, "fontSize": "11.5px"}),
                html.Div(gap.description, style={
                    "marginTop": "6px", "fontSize": "13.5px", "lineHeight": "1.6"}),
            ], style={"marginBottom": "12px"}))
    else:
        body.append(html.Div("None recorded against this owner.", style={
            "fontSize": "13px", "color": faint, "marginBottom": "12px"}))

    red = [hit for hit in matches if hit.is_red_flag]
    other = [hit for hit in matches if not hit.is_red_flag]

    body.append(html.Div("DATABASE MATCHES (" + str(len(matches)) + ")", style={
        "fontSize": "10.5px", "fontWeight": "800", "letterSpacing": "0.8px",
        "color": section_colour["crossref"], "margin": "16px 0 8px"}))

    for hit in red:
        body.append(html.Div([
            html.Div("RED FLAG - " + hit.matched_label, style={
                "color": "#be123c", "fontWeight": "800", "fontSize": "11.5px",
                "letterSpacing": "0.5px", "marginBottom": "4px"}),
            html.Div(hit.note, style={"fontSize": "12.5px", "lineHeight": "1.55"}),
        ], style={"backgroundColor": "#ffffff", "borderLeft": "3px solid #be123c",
                  "padding": "9px 11px", "marginBottom": "9px"}))

    for hit in other[:6]:
        body.append(html.Div([
            html.Span(hit.matched_label, style={"fontWeight": "600"}),
            html.Span("  " + hit.source.replace("_", " "), style={
                "color": faint, "fontSize": "11.5px"}),
            html.Div(hit.note[:130], style={
                "color": faint, "fontSize": "12px", "marginTop": "1px"}),
        ], style={"padding": "6px 0", "borderBottom": "1px solid #fecdd3",
                  "fontSize": "13px"}))

    if len(other) > 6:
        body.append(html.Div("...and " + str(len(other) - 6) + " more.", style={
            "fontSize": "12px", "color": faint, "marginTop": "6px"}))

    if not matches:
        body.append(html.Div(
            "No match in Wikidata, Getty or the local tables. That is not "
            "evidence of anything; many legitimate owners are simply not in "
            "these sources.",
            style={"fontSize": "12.5px", "color": faint, "lineHeight": "1.55"}))

    return body


def _gap_rows(result: audit_result):
    rows = []
    for gap in result.gaps:
        colour = severity_colour[gap.severity]
        rows.append(html.Div(
            style={"padding": "12px 0", "borderBottom": f"1px solid #f4f4f5"},
            children=[
                html.Span(gap.severity.value.upper(), style={
                    "color": "#ffffff", "backgroundColor": colour,
                    "fontSize": "10px", "fontWeight": "800", "padding": "2px 7px",
                    "letterSpacing": "0.7px", "marginRight": "9px"}),
                html.Span(gap.kind.value.replace("_", " "), style={
                    "color": faint, "fontSize": "12px", "letterSpacing": "0.3px"}),
                html.Div(gap.description, style={
                    "marginTop": "6px", "fontSize": "14px", "lineHeight": "1.6"}),
            ],
        ))
    return rows


def _score_breakdown(result: audit_result):
    rows = []
    for component in result.score.components:
        positive = component.points > 0
        rows.append(html.Div(
            style={"display": "flex", "gap": "14px", "padding": "8px 0",
                   "borderBottom": "1px solid #f4f4f5", "fontSize": "13.5px"},
            children=[
                html.Span(f"{component.points:+.1f}", style={
                    "minWidth": "46px", "textAlign": "right", "fontWeight": "700",
                    "color": "#15803d" if positive else "#be123c",
                    "fontFamily": "ui-monospace, Consolas, monospace"}),
                html.Div([
                    html.Div(component.label, style={"fontWeight": "600"}),
                    html.Div(component.detail, style={
                        "color": faint, "fontSize": "12.5px", "marginTop": "2px",
                        "lineHeight": "1.5"}),
                ]),
            ],
        ))
    rows.append(html.Div(result.score.method_note, style={
        "fontSize": "12px", "color": faint, "marginTop": "14px",
        "fontStyle": "italic", "lineHeight": "1.6"}))
    return rows


def _crossref_blocks(result: audit_result):
    red = [h for h in result.crossref_hits if h.is_red_flag]
    other = [h for h in result.crossref_hits if not h.is_red_flag]
    blocks = []

    if red:
        blocks.append(html.Div(
            style={"borderLeft": "3px solid #be123c", "backgroundColor": "#fff1f2",
                   "padding": "13px 15px", "marginBottom": "16px"},
            children=[
                html.Div("NAMED IN THE RED-FLAG LIST", style={
                    "color": "#be123c", "fontWeight": "800", "fontSize": "11px",
                    "letterSpacing": "0.8px", "marginBottom": "8px"}),
                *[html.Div([
                    html.Span(f"{h.owner_name} ", style={"fontWeight": "700"}),
                    html.Span(f"matched {h.matched_label}. ",
                              style={"fontSize": "13.5px"}),
                    html.Span(h.note, style={"fontSize": "13px", "color": muted}),
                ], style={"marginBottom": "6px", "fontSize": "14px",
                          "lineHeight": "1.6"}) for h in red],
            ],
        ))

    if other:
        grouped = {}
        for hit in other:
            grouped.setdefault(hit.owner_name, []).append(hit)
        rows = [html.Div([
            html.Span(owner, style={"fontWeight": "700"}),
            html.Span(" - " + ", ".join(
                f"{h.matched_label} ({h.source.replace('_', ' ')})"
                for h in hits[:3]),
                style={"color": muted, "fontSize": "13px"}),
        ], style={"padding": "6px 0", "fontSize": "13.5px"})
            for owner, hits in grouped.items()]

        blocks.append(html.Details([
            html.Summary(f"{len(other)} reference matches across Wikidata and Getty",
                         style={"cursor": "pointer", "fontSize": "13.5px",
                                "color": section_colour["crossref"],
                                "fontWeight": "600"}),
            html.Div(rows, style={"marginTop": "10px"}),
            html.Div("A match only confirms a name exists in a reference database. "
                     "It is not evidence of wrongdoing, and no match is not "
                     "evidence of anything.",
                     style={"marginTop": "10px", "fontSize": "12px",
                            "color": faint, "fontStyle": "italic"}),
        ]))

    if not blocks:
        blocks.append(html.Div("No cross-reference matches were found.",
                               style={"fontSize": "14px", "color": muted}))
    return blocks


# --------------------------------------------------------------------------
# callbacks
# --------------------------------------------------------------------------


@callback(
    Output("record_input", "value"),
    Output("upload_status", "children"),
    Input("file_upload", "contents"),
    State("file_upload", "filename"),
    prevent_initial_call=True,
)
def handle_upload(contents, filename):
    text, warnings = extract_text(contents, filename or "")
    if not text:
        return dash.no_update, (warnings[0] if warnings else "Could not read that file.")
    note = f"Loaded {filename}."
    if warnings:
        note += " " + warnings[0]
    return text, note


def _render(result: audit_result):
    blocks = [
        # Summary first: the number, the verdict, the one-line chain reading.
        section("score", "Summary", [
            _score_dial(result),
            html.Div(style={"height": "1px", "backgroundColor": rule,
                            "margin": "22px 0 18px"}),
            _chain_summary(result),
        ]),
    ]

    if result.warnings:
        blocks.append(section("shield", "Notes on this run", [
            html.Div(f"- {w}", style={"fontSize": "13.5px", "lineHeight": "1.65",
                                      "marginBottom": "5px"})
            for w in result.warnings
        ]))

    if result.events:
        blocks.append(section(
            "chain", "Ownership chain", _chain_rows(result),
            note="Rows marked red are involved in a gap. Click one to see the "
                 "gap and any database matches for that owner."))
    if result.gaps:
        blocks.append(section("gaps", "Gaps", _gap_rows(result)))

    blocks.append(section("crossref", "Cross-reference", _crossref_blocks(result)))
    blocks.append(section("score", "How the score was reached",
                          _score_breakdown(result)))

    blocks.append(html.Div(summarise_usage(result.usage), style={
        "fontSize": "11.5px", "color": faint, "textAlign": "right",
        "fontFamily": "ui-monospace, Consolas, monospace"}))
    return blocks


@callback(
    Output("results", "children"),
    Output("work_panel", "children"),
    Input("audit_button", "n_clicks"),
    State("record_input", "value"),
    prevent_initial_call=True,
)
def run(n_clicks, record_text):
    if not record_text or not record_text.strip():
        return (html.Div("Paste a provenance record first.",
                         style={"color": muted, "fontSize": "14px"}), None)
    try:
        result = run_audit(record_text, budget=run_budget())
    except spend_cap_exceeded as error:
        return html.Div(str(error), style={"color": "#be123c"}), None
    except Exception as error:
        return (html.Div(
            f"The audit could not finish ({type(error).__name__}). "
            "Check that the API key is set, then try again.",
            style={"color": "#be123c", "fontSize": "14px"}), None)
    return _render(result), _work_panel(result)


if __name__ == "__main__":
    config.load_environment()
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
