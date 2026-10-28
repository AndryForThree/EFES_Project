"""Exact four-bar solver, branch boundaries and guarded motion tracking."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import numpy as np
from .geometry import Vector, arm_vector, circle_intersections, rotate, unwrap
from .parameters import Parameters


@dataclass(frozen=True)
class Pose:
    theta_left: float
    theta_right: float
    branch: int
    a_left: Vector
    a_right: Vector
    b_left: Vector
    b_right: Vector
    c_left: Vector
    c_right: Vector
    heading_left: float
    heading_right: float
    point: Vector
    tangent: bool
    radial_margin: float
    closure_error: float


@dataclass(frozen=True)
class Solution:
    status: str
    poses: tuple[Pose, ...]
    reason: str = ""


REASONS = {
    "impossible": "I cerchi non si intersecano: il tirante non può chiudere il meccanismo.",
    "coincident": "Cerchi coincidenti: angolo destro indeterminato, configurazione singolare.",
    "concentric": "Cerchi concentrici di raggi diversi: nessuna configurazione.",
    "degenerate": "Un collegamento ha lunghezza degenere.",
    "tangent": "Punto morto: i due rami coincidono. Movimento arrestato.",
}


def neutral_tie_length(p: Parameters) -> float:
    return float(np.linalg.norm(np.array([p.pivot_spacing, 0.0])
                                + arm_vector(p.right)-arm_vector(p.left)))


def neutral_branch(p: Parameters) -> int:
    """Choose neutral-compatible branch once; never use this during motion."""
    solutions = solve(p, 0.0).poses
    return min(solutions, key=lambda s: abs(math.remainder(s.theta_right, 2*math.pi))).branch if solutions else p.branch


def solve(p: Parameters, theta_left: float) -> Solution:
    try:
        p.validate()
    except ValueError as exc:
        return Solution("degenerate", (), str(exc))
    if not math.isfinite(theta_left):
        return Solution("degenerate", (), "Angolo di ingresso non finito.")
    al, ar = np.array([-p.pivot_spacing/2, 0.0]), np.array([p.pivot_spacing/2, 0.0])
    bl = al + rotate(arm_vector(p.left), theta_left)
    intersections = circle_intersections(ar, p.right.arm_length, bl, p.tie_length, p.length_tolerance)
    poses = []
    for branch, br in intersections.points:
        theta_right = math.remainder(math.atan2(*(br-ar)[::-1])-p.right.arm_angle, 2*math.pi)
        cl = al + rotate((p.left.axle_x, p.left.axle_y), theta_left)
        cr = ar + rotate((p.right.axle_x, p.right.axle_y), theta_right)
        poses.append(Pose(theta_left, theta_right, branch, al, ar, bl, br, cl, cr,
                          theta_left+p.left.heading_offset, theta_right+p.right.heading_offset,
                          bl+p.actuation_fraction*(br-bl), intersections.status == "tangent",
                          intersections.margin, abs(float(np.linalg.norm(br-bl))-p.tie_length)))
    return Solution(intersections.status, tuple(poses), REASONS.get(intersections.status, ""))


def select_pose(solution: Solution, branch: int, reference: float = 0.0) -> Pose | None:
    for pose in solution.poses:
        if pose.branch in (branch, 0):
            angle = unwrap(pose.theta_right, reference)
            return replace(pose, theta_right=angle,
                           heading_right=pose.heading_right+(angle-pose.theta_right))
    return None


def toggle_angles(p: Parameters, lower: float, upper: float) -> list[float]:
    """All exact circle tangencies/coincidences in an input interval.

    h² = d² + L² - 2dL cos(theta_left + alpha_left).
    This also detects an isolated toggle skipped by coarse slider/plot samples.
    """
    d, length = p.pivot_spacing, p.left.arm_length
    if min(d, length) <= p.length_tolerance:
        return []
    roots = []
    for radius in (abs(p.right.arm_length-p.tie_length), p.right.arm_length+p.tie_length):
        cosine = (d*d + length*length-radius*radius)/(2*d*length)
        if abs(cosine) > 1+1e-12:
            continue
        phase = math.acos(float(np.clip(cosine, -1, 1)))
        for sign in (-1, 1):
            base = sign*phase-p.left.arm_angle
            for turn in range(math.ceil((lower-base)/math.tau-1e-12),
                              math.floor((upper-base)/math.tau+1e-12)+1):
                value = base+turn*math.tau
                if not any(abs(value-old) < 1e-10 for old in roots):
                    roots.append(value)
    return sorted(roots)


def steering_input(p: Parameters, steering: float) -> float:
    """Left angle for a specified mean wheel angle, on the symmetric neutral path.

    theta_L=m+delta, theta_R=m-delta, u=2L*sin(beta+delta).
    Closure gives u²+2*d*cos(m)*u+d²-t²=0; choose its neutral root.
    """
    d, t, length = p.pivot_spacing, p.tie_length, p.left.arm_length
    discriminant = t*t-d*d*math.sin(steering)**2
    if discriminant < -p.scale*p.length_tolerance:
        raise ValueError("Angolo medio non raggiungibile.")
    u = -d*math.cos(steering)+math.sqrt(max(0.0, discriminant))
    sine = u/(2*length)
    if abs(sine) > 1+1e-9:
        raise ValueError("Angolo medio non raggiungibile.")
    delta = math.asin(max(-1.0, min(1.0, sine)))-(p.left.arm_angle-math.pi/2)
    return steering+delta


def steering_limit(p: Parameters, *, respect_display: bool = True) -> tuple[float, bool]:
    """Symmetric mean-angle interval, ending at the first toggle on either side.

    Mirrored poses exchange the wheels. Use the first input/output toggle to
    avoid entering a different assembly sector on either steering direction.
    """
    roots = toggle_angles(p, -math.pi, math.pi)
    endpoints = []
    for side in (-1, 1):
        candidates = [r for r in roots if r*side > 1e-12]
        if not candidates:
            continue
        root = min(candidates, key=abs)
        pose = select_pose(solve(p, root), p.branch)
        if pose:
            endpoints.append(abs((pose.heading_left+pose.heading_right)/2))
        elif solve(p, root).status == "coincident":
            # Symmetric parallelogram: the unique path limit is ±90°.
            endpoints.append(abs(root))
    geometric = min(endpoints, default=math.pi)
    cap = p.display_range if respect_display else math.pi/2
    return min(cap, geometric), geometric <= cap+1e-12


@dataclass
class BranchTracker:
    parameters: Parameters
    pose: Pose | None = None
    stop_reason: str = ""

    def move(self, theta_left: float, reset: bool = False) -> Pose | None:
        """Reject traversing a branch boundary, even with a large input jump.

        An explicit reset permits choosing a new disconnected assembly pose.
        On rejection the last accepted pose is retained and labelled in the UI.
        """
        self.stop_reason = ""
        if self.pose is not None and not reset and abs(theta_left-self.pose.theta_left) > 1e-12:
            lo, hi = sorted((theta_left, self.pose.theta_left))
            if toggle_angles(self.parameters, lo, hi):
                self.stop_reason = "Movimento bloccato: attraverserebbe un punto morto. Ultima posa valida mantenuta."
                return self.pose
        solution = solve(self.parameters, theta_left)
        pose = select_pose(solution, self.parameters.branch,
                           self.pose.theta_right if self.pose is not None and not reset else 0)
        if pose is None:
            self.stop_reason = solution.reason
            if reset:
                self.pose = None
            return self.pose
        self.pose = pose
        if pose.tangent:
            self.stop_reason = solution.reason
        return pose


@dataclass(frozen=True)
class Sample:
    angle: float
    pose: Pose | None
    segment: int
    status: str


def sweep(p: Parameters, lower: float, upper: float, count: int = 181) -> list[Sample]:
    boundaries = toggle_angles(p, lower, upper)
    angles = sorted(set(np.linspace(lower, upper, count).tolist()+boundaries))
    samples, previous, segment = [], None, 0
    for angle in angles:
        solution = solve(p, angle)
        pose = select_pose(solution, p.branch, previous.theta_right if previous else 0)
        if pose is None or pose.tangent:
            segment += 1
            previous = None
        else:
            previous = pose
        samples.append(Sample(angle, pose, segment, solution.status))
    return samples
