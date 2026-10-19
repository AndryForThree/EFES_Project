"""Small, unit-agnostic rigid-body and circle geometry primitives."""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np
from numpy.typing import NDArray
from .parameters import Bracket

Vector = NDArray[np.float64]


def rotate(vector: Vector | tuple[float, float], angle: float) -> Vector:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s], [s, c]]) @ np.asarray(vector, dtype=float)


def perpendicular(vector: Vector) -> Vector:
    return np.array([-vector[1], vector[0]])


def arm_vector(bracket: Bracket) -> Vector:
    return bracket.arm_length * np.array([math.cos(bracket.arm_angle), math.sin(bracket.arm_angle)])


def unwrap(angle: float, reference: float) -> float:
    return reference + math.remainder(angle - reference, 2 * math.pi)


@dataclass(frozen=True)
class CircleResult:
    status: str
    points: tuple[tuple[int, Vector], ...] = ()
    margin: float = math.nan  # signed radial distance to closest tangency, mm


def circle_intersections(center: Vector, radius: float, other: Vector,
                         other_radius: float, tolerance: float) -> CircleResult:
    """Stable exact intersections, signed by cross(other-center, point-center).

    A tangent yields branch 0. Coincident equal circles have infinitely many
    solutions and intentionally return no selected point.
    """
    if min(radius, other_radius) <= tolerance:
        return CircleResult("degenerate")
    delta = other - center
    h = float(np.linalg.norm(delta))
    if h <= tolerance:
        return CircleResult("coincident" if abs(radius-other_radius) <= tolerance else "concentric")
    margin = min(radius + other_radius - h, h - abs(radius-other_radius))
    if margin < -tolerance:
        return CircleResult("impossible", margin=margin)
    e = delta / h
    a = (h*h + (radius-other_radius)*(radius+other_radius)) / (2*h)
    foot = center + a*e
    if abs(margin) <= tolerance:
        return CircleResult("tangent", ((0, foot),), margin)
    # Heron's factorization avoids subtracting two nearly equal squared lengths.
    q2 = ((radius+other_radius+h)*(radius+other_radius-h)
          *(h+radius-other_radius)*(h-radius+other_radius)) / (4*h*h)
    q = math.sqrt(max(0.0, q2))
    return CircleResult("valid", ((1, foot+q*perpendicular(e)),
                                   (-1, foot-q*perpendicular(e))), margin)


def rectangle(center: Vector, width: float, length: float, angle: float = 0.0) -> Vector:
    corners = np.array([[-width/2, -length/2], [width/2, -length/2],
                        [width/2, length/2], [-width/2, length/2]])
    return np.array([center + rotate(v, angle) for v in corners])


def strip(start: Vector, end: Vector, width: float, margin: float) -> Vector:
    delta = end-start
    angle = math.atan2(delta[1], delta[0]) - math.pi/2
    return rectangle((start+end)/2, width, float(np.linalg.norm(delta))+2*margin, angle)
