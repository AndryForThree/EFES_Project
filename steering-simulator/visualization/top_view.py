from __future__ import annotations

import math
import numpy as np
import plotly.graph_objects as go
from .shapes import bodies
from steering.geometry import arm_vector, rectangle
from steering.kinematics import Pose, Sample
from steering.parameters import Parameters

BLUE = "#3976c4"
ORANGE = "#df8628"
TEAL = "#138777"
INK = "#243548"


def polygon(fig: go.Figure, points: np.ndarray, color: str, fill: str,
            name: str, dash: str = "solid", width: float = 1.5) -> None:
    closed = np.vstack([points, points[0]])
    fig.add_trace(go.Scatter(x=closed[:, 0], y=closed[:, 1], mode="lines", name=name,
                            line=dict(color=color, width=width, dash=dash),
                            fill="toself", fillcolor=fill, showlegend=False,
                            hovertemplate=name+"<extra></extra>"))


def top_view(p: Parameters, pose: Pose | None, samples: list[Sample], *, labels: bool = True,
             construction: bool = False, trajectories: bool = True, neutral: bool = True,
             envelope: bool = False) -> go.Figure:
    fig = go.Figure()
    f = p.physical
    al, ar = np.array([-p.pivot_spacing/2, 0.]), np.array([p.pivot_spacing/2, 0.])
    if envelope:
        for side in ("left", "right"):
            x, y = [], []
            for sample in samples[::3]:
                s = sample.pose
                if s is None or s.tangent:
                    continue
                corners = rectangle(getattr(s, "c_"+side), f.wheel_width, f.wheel_diameter,
                                    getattr(s, "heading_"+side))
                corners = np.vstack([corners, corners[0]])
                x.extend([*corners[:, 0], None])
                y.extend([*corners[:, 1], None])
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="rgba(57,118,196,.16)", width=1),
                                    hoverinfo="skip", showlegend=False))
    if trajectories:
        for attribute, color, name in (("c_left", BLUE, "Traiettoria C SX"), ("c_right", BLUE, "Traiettoria C DX"),
                                       ("point", TEAL, "Traiettoria T")):
            x, y, previous_segment = [], [], None
            for sample in samples:
                if sample.segment != previous_segment:
                    x.append(None)
                    y.append(None)
                if sample.pose is None or sample.pose.tangent:
                    x.append(None)
                    y.append(None)
                else:
                    point = getattr(sample.pose, attribute)
                    x.append(point[0])
                    y.append(point[1])
                previous_segment = sample.segment
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=color, width=1.5, dash="dot"),
                                    name=name, showlegend=False, hoverinfo="skip"))
    if neutral:
        for pivot, bracket, label in ((al, p.left, "SX"), (ar, p.right, "DX")):
            center = pivot + np.array([bracket.axle_x, bracket.axle_y])
            polygon(fig, rectangle(center, f.wheel_width, f.wheel_diameter, bracket.heading_offset),
                    "#94a3b2", "rgba(0,0,0,0)", f"Ruota {label} nella posa zero nominale", "dash", 1)
    if construction:
        circles = [(al, p.left.arm_length), (ar, p.right.arm_length)]
        if pose:
            circles.append((pose.b_left, p.tie_length))
        for center, radius in circles:
            fig.add_shape(type="circle", x0=center[0]-radius, x1=center[0]+radius,
                          y0=center[1]-radius, y1=center[1]+radius,
                          line=dict(color="#b4c4cf", width=1, dash="dot"), layer="below")
    if pose:
        for body in bodies(p, pose):
            color, fill = {
                "arm": (BLUE, "rgba(57,118,196,.24)"), "bracket": (BLUE, "rgba(57,118,196,.12)"),
                "rod": (ORANGE, "rgba(223,134,40,.35)"), "wheel": (INK, "#33475c"),
                "joint": ("#71869b", "rgba(235,242,248,.7)"),
            }[body.family]
            polygon(fig, body.polygon, color, fill, body.name)
        for center, heading, name in ((pose.c_left, pose.heading_left, "C SX"),
                                      (pose.c_right, pose.heading_right, "C DX")):
            forward = np.array([math.sin(heading), -math.cos(heading)])
            end = center+forward*f.wheel_diameter*.38
            fig.add_annotation(x=end[0], y=end[1], ax=center[0], ay=center[1], axref="x", ayref="y",
                               text="", showarrow=True, arrowhead=2, arrowcolor="white", arrowwidth=1.8)
            fig.add_trace(go.Scatter(x=[center[0]], y=[center[1]], mode="markers+text" if labels else "markers",
                                    text=[name], textposition="bottom center", textfont=dict(color=INK, size=11),
                                    marker=dict(size=5, color="white", line=dict(color=BLUE, width=1)),
                                    showlegend=False, hovertemplate=f"{name}: (%{{x:.2f}}, %{{y:.2f}}) mm<extra></extra>"))
        fig.add_trace(go.Scatter(x=[pose.b_left[0], pose.b_right[0]], y=[pose.b_left[1], pose.b_right[1]],
                                mode="markers+text" if labels else "markers", text=["B SX", "B DX"],
                                textposition="bottom center", textfont=dict(size=11, color=ORANGE),
                                marker=dict(size=7, color="white", line=dict(color=ORANGE, width=2)),
                                showlegend=False, hovertemplate="Giunto: (%{x:.2f}, %{y:.2f}) mm<extra></extra>"))
        fig.add_trace(go.Scatter(x=[pose.point[0]], y=[pose.point[1]], mode="markers+text" if labels else "markers",
                                text=["T"], textposition="top center", marker=dict(size=10, color=TEAL, symbol="diamond"),
                                textfont=dict(color=TEAL), showlegend=False,
                                hovertemplate="T: (%{x:.2f}, %{y:.2f}) mm<extra></extra>"))
        if labels:
            for a, angle in ((al, pose.heading_left), (ar, pose.heading_right)):
                fig.add_annotation(x=a[0], y=-f.wheel_diameter/2-15, text=f"{math.degrees(angle):+.1f}°",
                                   showarrow=False, font=dict(size=15, color=BLUE))
    fig.add_trace(go.Scatter(x=[al[0], ar[0]], y=[0, 0], mode="markers+text" if labels else "markers",
                            text=["A SX", "A DX"], textposition="top center", textfont=dict(size=11, color="#153f70"),
                            marker=dict(size=10, color="#153f70", symbol="circle-cross"), showlegend=False,
                            hovertemplate="Perno fisso: (%{x:.2f}, %{y:.2f}) mm<extra></extra>"))
    if labels:
        dim_y = max(p.left.arm_length, p.right.arm_length,
                        math.hypot(p.left.axle_x, p.left.axle_y),
                        math.hypot(p.right.axle_x, p.right.axle_y)) + math.hypot(f.wheel_width, f.wheel_diameter)/2 + 15
        fig.add_trace(go.Scatter(x=[al[0], ar[0]], y=[dim_y]*2, mode="lines+markers",
                                line=dict(color="#8798a8", width=1), marker=dict(symbol="line-ns", size=8),
                                showlegend=False, hoverinfo="skip"))
        fig.add_annotation(x=0, y=dim_y+8, text=f"Interasse perni · {p.pivot_spacing:g} mm",
                           showarrow=False, font=dict(color="#667a8d", size=11))
    # Conservative fixed viewport, independent of the current steering angle.
    reach = max(math.hypot(p.left.axle_x, p.left.axle_y), math.hypot(p.right.axle_x, p.right.axle_y),
                p.left.arm_length, p.right.arm_length) + math.hypot(f.wheel_width, f.wheel_diameter)/2 + 22
    half_width = p.pivot_spacing/2+reach
    front = reach+15
    rear = reach+15
    fig.update_layout(height=560, margin=dict(l=20, r=15, t=10, b=25),
                      paper_bgcolor="#fafcfd", plot_bgcolor="#fafcfd", font=dict(family="sans-serif", color=INK),
                      xaxis=dict(title="X · mm → destra", range=[-half_width, half_width],
                                 gridcolor="#e8edf1", zerolinecolor="#c9d4dd", dtick=25, constrain="domain"),
                      yaxis=dict(title="Y · mm → retro", range=[rear, -front],
                                 scaleanchor="x", scaleratio=1, gridcolor="#e8edf1", zerolinecolor="#c9d4dd", dtick=25),
                      uirevision=str((p.pivot_spacing, reach)), dragmode="pan")
    fig.add_annotation(x=.5, y=.98, xref="paper", yref="paper", text="↑ FRONTE VEICOLO · −Y",
                       showarrow=False, font=dict(size=10, color="#8394a4"))
    return fig
