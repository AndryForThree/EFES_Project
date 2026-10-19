"""Conservative polygon envelopes with optional vertical interval checks.

These are clearance candidates, not a 3D contact or structural solver.
Intended mating pairs are excluded and assessed separately by assembly rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
import numpy as np
from .geometry import Vector, rectangle, strip
from .kinematics import Pose
from .parameters import Parameters


@dataclass(frozen=True)
class Body:
    name: str
    polygon: Vector
    z_min: float
    z_max: float
    family: str


@dataclass(frozen=True)
class Clearance:
    first: str
    second: str
    xy_gap: float
    z_gap: float
    status: str  # projected / separated / risk


def bodies(p: Parameters, pose: Pose) -> list[Body]:
    f = p.physical
    result = [Body("Tirante", strip(pose.b_left, pose.b_right, f.rod_width, f.end_margin),
                   f.rod_z, f.rod_z+f.rod_thickness, "rod")]
    for side, a, b, c, heading in (("SX", pose.a_left, pose.b_left, pose.c_left, pose.heading_left),
                                  ("DX", pose.a_right, pose.b_right, pose.c_right, pose.heading_right)):
        result.extend([
            Body(f"Braccio {side}", strip(a, b, f.arm_width, f.end_margin), f.arm_z, f.arm_z+f.arm_thickness, "arm"),
            Body(f"Staffa {side}", strip(a, c, f.bracket_width, f.end_margin), f.bracket_z, f.bracket_z+f.bracket_thickness, "bracket"),
            Body(f"Ruota {side}", rectangle(c, f.wheel_width, f.wheel_diameter, heading),
                 f.wheel_axle_z-f.wheel_diameter/2, f.wheel_axle_z+f.wheel_diameter/2, "wheel"),
        ])
        for prefix, point, z in (("Perno", a, f.arm_z+f.arm_thickness),
                                 ("Giunto", b, f.rod_z+f.rod_thickness)):
            # Circumscribed 16-gon encloses the washer/bolt head footprint.
            radius = max(f.washer_diameter, f.bolt_head_diameter)/2/math.cos(math.pi/16)
            angles = np.linspace(0, math.tau, 16, endpoint=False)
            polygon = point+radius*np.column_stack([np.cos(angles), np.sin(angles)])
            result.append(Body(f"{prefix} {side}", polygon, z, z+f.washer_thickness, "fastener"))
    return result


def polygons_overlap(first: Vector, second: Vector, tolerance: float = 1e-9) -> bool:
    """Separating axis theorem; touching counts as zero clearance."""
    for polygon in (first, second):
        for start, end in zip(polygon, np.roll(polygon, -1, axis=0)):
            edge = end-start
            axis = np.array([-edge[1], edge[0]])
            norm = np.linalg.norm(axis)
            if norm <= tolerance:
                continue
            axis /= norm
            a, b = first @ axis, second @ axis
            if a.max() < b.min()-tolerance or b.max() < a.min()-tolerance:
                return False
    return True


def polygon_distance(first: Vector, second: Vector) -> float:
    if polygons_overlap(first, second):
        return 0.0
    minimum = math.inf
    for points, edges in ((first, second), (second, first)):
        for start, end in zip(edges, np.roll(edges, -1, axis=0)):
            delta = end-start
            length2 = float(delta @ delta)
            if length2 <= 1e-24:
                continue
            fractions = np.clip((points-start) @ delta / length2, 0, 1)
            minimum = min(minimum, float(np.linalg.norm(points-start-fractions[:, None]*delta, axis=1).min()))
    return minimum


def intended_mate(first: Body, second: Body) -> bool:
    names = {first.name, second.name}
    for side in ("SX", "DX"):
        mating = [
            {f"Braccio {side}", "Tirante"}, {f"Braccio {side}", f"Staffa {side}"},
            {f"Staffa {side}", f"Ruota {side}"},
            {f"Perno {side}", f"Braccio {side}"}, {f"Perno {side}", f"Staffa {side}"},
            {f"Giunto {side}", f"Braccio {side}"}, {f"Giunto {side}", "Tirante"},
        ]
        if names in mating:
            return True
    return False


def check_clearances(p: Parameters, pose: Pose) -> list[Clearance]:
    result = []
    for first, second in combinations(bodies(p, pose), 2):
        if intended_mate(first, second):
            continue
        # Cheap broad phase before polygon distance.
        gap = np.maximum(first.polygon.min(axis=0)-second.polygon.max(axis=0),
                         second.polygon.min(axis=0)-first.polygon.max(axis=0))
        if np.any(gap > p.targets.clearance+p.length_tolerance):
            continue
        xy_gap = polygon_distance(first.polygon, second.polygon)
        if xy_gap > p.targets.clearance+p.length_tolerance:
            continue
        z_gap = max(second.z_min-first.z_max, first.z_min-second.z_max, 0.0)
        # Euclidean distance between the polygon prisms, conservative wheel box.
        status = "projected" if not p.physical.use_heights else (
            "risk" if math.hypot(xy_gap, z_gap) <= p.targets.clearance+p.length_tolerance else "separated")
        result.append(Clearance(first.name, second.name, xy_gap, z_gap, status))
    return result


def manufacturing_issues(p: Parameters) -> list[str]:
    f, issues = p.physical, []
    if f.hole_diameter <= f.pivot_diameter:
        issues.append("Il foro non lascia gioco al perno nominale.")
    if min(f.arm_width, f.rod_width) <= f.hole_diameter:
        issues.append("Il foro raggiunge il bordo laterale della piattina.")
    if f.end_margin <= f.hole_diameter/2:
        issues.append("Materiale insufficiente tra foro ed estremità.")
    if f.use_heights:
        gap = f.rod_z-(f.arm_z+f.arm_thickness)
        if gap < f.washer_thickness+f.spacer_height-p.length_tolerance:
            issues.append("Tra braccio e tirante manca lo spazio per rondella e distanziale dichiarati.")
    return issues
