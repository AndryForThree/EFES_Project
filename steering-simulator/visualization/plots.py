from __future__ import annotations

import math
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from steering.kinematics import Sample, solve, toggle_angles
from steering.parameters import Parameters, TRANSMISSION_WARNING_SINE
from steering.singularities import diagnose
from .top_view import BLUE, ORANGE, TEAL


def response_plots(p: Parameters, samples: list[Sample], current: float) -> go.Figure:
    fig = make_subplots(rows=3, cols=2, subplot_titles=(
        "A · Trasmissione dello sterzo", "B · Differenza orientamento ruote",
        "C · Rapporto cinematico", "D · Punto T sul tirante",
        "E · Traiettorie dei centri ruota", "F · Margine di trasmissione"),
        vertical_spacing=.13, horizontal_spacing=.12)
    x, right, mismatch, ratio, tx, ty, in_sine, out_sine, clx, cly, crx, cry = ([] for _ in range(12))
    data = [x, right, mismatch, ratio, tx, ty, in_sine, out_sine, clx, cly, crx, cry]
    previous_segment = None
    for sample in samples:
        if previous_segment is not None and sample.segment != previous_segment:
            for series in data:
                series.append(None)
        previous_segment = sample.segment
        x.append(math.degrees(sample.angle))
        pose = sample.pose
        if pose is None or pose.tangent:
            for series in data[1:]:
                series.append(None)
            continue
        d = diagnose(p, pose)
        for series, value in zip(data[1:], [math.degrees(pose.theta_right), math.degrees(d.mismatch), d.ratio,
                                          *pose.point, d.input_sine, d.output_sine,
                                          *pose.c_left, *pose.c_right]):
            series.append(value)
    def line(xs, ys, row, col, name, color, dash="solid"):
        fig.add_trace(go.Scatter(x=xs, y=ys, name=name, mode="lines", connectgaps=False,
                                line=dict(color=color, width=2, dash=dash)), row=row, col=col)
    line(x, right, 1, 1, "θ DX", BLUE)
    degrees = [math.degrees(samples[0].angle), math.degrees(samples[-1].angle)]
    line(degrees, degrees, 1, 1, "Ideale θ DX = θ SX", "#a3afbb", "dash")
    line(x, mismatch, 1, 2, "Δ heading", ORANGE)
    line(x, ratio, 2, 1, "dθ DX / dθ SX", TEAL)
    line(x, tx, 2, 2, "T x", TEAL)
    line(x, ty, 2, 2, "T y", ORANGE)
    line(clx, cly, 3, 1, "C SX", BLUE)
    line(crx, cry, 3, 1, "C DX", ORANGE)
    line(x, in_sine, 3, 2, "Trasmissione ingresso", BLUE)
    line(x, out_sine, 3, 2, "Trasmissione uscita", ORANGE)
    fig.add_hline(y=TRANSMISSION_WARNING_SINE, line_dash="dash", line_color="#ce5966", row=3, col=2)
    boundaries = toggle_angles(p, samples[0].angle, samples[-1].angle)
    cuts = [samples[0].angle, *boundaries, samples[-1].angle]
    for row, col, unit in ((1, 1, "θ DX · °"), (1, 2, "Δ heading · °"), (2, 1, "rad / rad"),
                           (2, 2, "mm"), (3, 2, "|d · B′| / (t L)")):
        fig.update_xaxes(title_text="θ SX · °", row=row, col=col)
        fig.update_yaxes(title_text=unit, row=row, col=col)
        fig.add_vline(x=math.degrees(current), line_color="#8ea0b0", line_width=1, row=row, col=col)
        for boundary in boundaries:
            fig.add_vline(x=math.degrees(boundary), line_color="#cf455b", line_dash="dot", row=row, col=col)
        for lo, hi in zip(cuts, cuts[1:]):
            if not solve(p, (lo+hi)/2).poses:
                fig.add_vrect(x0=math.degrees(lo), x1=math.degrees(hi), fillcolor="#e36274", opacity=.14,
                              line_width=0, row=row, col=col)
    # Both X/Y trajectory scales are identical and +Y points toward the rear.
    fig.update_xaxes(title_text="X · mm", row=3, col=1)
    fig.update_yaxes(title_text="Y · mm", autorange="reversed", scaleanchor="x5", scaleratio=1, row=3, col=1)
    from steering.kinematics import select_pose
    pose = select_pose(solve(p, current), p.branch)
    if pose:
        fig.add_trace(go.Scatter(x=[pose.c_left[0], pose.c_right[0]], y=[pose.c_left[1], pose.c_right[1]],
                                mode="markers", marker=dict(size=8, color=TEAL), name="Centri attuali"), row=3, col=1)
    fig.update_layout(height=950, template="plotly_white", margin=dict(l=25, r=20, t=45, b=20),
                      legend=dict(orientation="h", y=-.09), font=dict(size=11),
                      uirevision=str(p), hovermode="closest")
    return fig
