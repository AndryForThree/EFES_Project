"""Crank + pin-jointed connecting rod to a material point of the steering rod.

The inverse problem (steering -> crank) is exact circle intersection. The
forward problem is bracketed on the continuous, monotone sector containing
neutral; no root can jump to another actuator assembly. Angles are radians.
"""
from __future__ import annotations
from dataclasses import dataclass
import csv
import io
import math
import numpy as np
from .geometry import circle_intersections, perpendicular, unwrap
from .kinematics import Pose, select_pose, solve, steering_input, steering_limit
from .parameters import Parameters


@dataclass(frozen=True)
class MotorPose:
    pose: Pose
    steering: float
    phi: float  # absolute crank direction from +X
    pin: np.ndarray
    sensitivity: float | None  # rad of mean steering per rad of output shaft
    numerator: float
    denominator: float
    margin: float
    closure_error: float


@dataclass(frozen=True)
class MotorRange:
    valid: bool
    reason: str
    neutral_phi: float = 0.0
    mean_lower: float = 0.0
    mean_upper: float = 0.0
    phi_at_lower: float = 0.0  # relative to neutral, not sorted
    phi_at_upper: float = 0.0
    lower_reason: str = ""
    upper_reason: str = ""

    @property
    def phi_lower(self) -> float:
        return min(self.phi_at_lower, self.phi_at_upper)

    @property
    def phi_upper(self) -> float:
        return max(self.phi_at_lower, self.phi_at_upper)


def mean_point_velocity(p: Parameters, pose: Pose, mean: float) -> np.ndarray | None:
    """Analytic T derivative with respect to the mean steering angle."""
    d, t, length = p.pivot_spacing, p.tie_length, p.left.arm_length
    beta = p.left.arm_angle-math.pi/2
    if abs(d-t) <= p.length_tolerance and abs(beta) <= 1e-12:
        delta_prime = 0.0
    else:
        discriminant = t*t-d*d*math.sin(mean)**2
        if discriminant <= p.scale*p.length_tolerance:
            return None
        root = math.sqrt(discriminant)
        u = -d*math.cos(mean)+root
        cosine = math.sqrt(max(0.0, 1-(u/(2*length))**2))
        if cosine <= 1e-10:
            return None
        u_prime = d*math.sin(mean)-d*d*math.sin(mean)*math.cos(mean)/root
        delta_prime = u_prime/(2*length*cosine)
    return ((1-p.actuation_fraction)*(1+delta_prime)*perpendicular(pose.b_left-pose.a_left)
            +p.actuation_fraction*(1-delta_prime)*perpendicular(pose.b_right-pose.a_right))


def at_steering(p: Parameters, mean: float, reference: float = 0.0) -> MotorPose | None:
    try:
        left = steering_input(p, mean)
    except ValueError:
        return None
    pose = select_pose(solve(p, left), p.branch, 2*mean-left)
    if pose is None:
        return None
    motor = p.motor
    center = np.array([motor.x, motor.y])
    tolerance = max(p.scale, motor.crank_radius, motor.connecting_length)*1e-10
    circles = circle_intersections(center, motor.crank_radius, pose.point,
                                    motor.connecting_length, tolerance)
    pin = next((v for branch, v in circles.points if branch in (motor.assembly, 0)), None)
    if pin is None:
        return None
    phi = unwrap(math.atan2(*(pin-center)[::-1]), reference)
    rod = pose.point-pin
    velocity = mean_point_velocity(p, pose, mean)
    numerator = float(rod @ perpendicular(pin-center))
    denominator = float(rod @ velocity) if velocity is not None else math.nan
    normalized = abs(denominator)/(motor.connecting_length*max(p.left.arm_length, p.right.arm_length))
    sensitivity = numerator/denominator if math.isfinite(denominator) and normalized > 1e-8 else None
    return MotorPose(pose, mean, phi, pin, sensitivity, numerator, denominator,
                     circles.margin, abs(float(np.linalg.norm(rod))-motor.connecting_length))


def build_range(p: Parameters) -> MotorRange:
    """Find the neutral-connected actuator sector; refine boundaries by bisection.

    Initial bracketing uses 256 intervals per side. Both transmission dead points,
    inverse-circle feasibility and passive steering limits terminate the sector.
    A full revolution is never assumed; excursions are limited to 180° per side.
    """
    neutral = at_steering(p, 0.0)
    if neutral is None:
        return MotorRange(False, "Leva e astina non possono collegarsi al tirante con le ruote dritte.")
    scale = p.motor.connecting_length*max(p.left.arm_length, p.motor.crank_radius)
    if (neutral.margin <= max(p.scale, p.motor.connecting_length)*1e-9
            or not math.isfinite(neutral.denominator)
            or min(abs(neutral.numerator), abs(neutral.denominator)) <= scale*1e-9):
        return MotorRange(False, "Il collegamento del motore è già a un punto morto nella posa centrale. Sposta M o cambia le lunghezze.")
    passive_limit, _ = steering_limit(p, respect_display=False)
    output_sign = math.copysign(1, neutral.denominator)
    input_sign = math.copysign(1, neutral.numerator)

    def acceptable(mean: float) -> tuple[bool, str, MotorPose | None]:
        state = at_steering(p, mean, neutral.phi)
        if state is None or state.margin <= 0:
            return False, "Leva e astina allineate / limite di chiusura", state
        if not math.isfinite(state.denominator) or state.denominator*output_sign <= 0:
            return False, "Punto morto della trasmissione motore–sterzo", state
        if state.numerator*input_sign <= 0:
            return False, "Leva e astina allineate", state
        if abs(state.phi-neutral.phi) >= math.pi-1e-10:
            return False, "Escursione albero di 180° dalla posa centrale", state
        return True, "", state

    ends = []
    for sign in (-1, 1):
        last = 0.0
        end = sign*passive_limit
        reason = "Limite della geometria di sterzo"
        for index in range(1, 257):
            candidate = sign*passive_limit*index/256
            ok, why, _ = acceptable(candidate)
            if not ok:
                lo, hi = last, candidate
                for _ in range(48):
                    middle = (lo+hi)/2
                    if acceptable(middle)[0]:
                        lo = middle
                    else:
                        hi = middle
                end = lo
                reason = why
                break
            last = candidate
        state = at_steering(p, end, neutral.phi)
        if state is None:
            return MotorRange(False, "Impossibile determinare una corsa continua del motore.")
        ends.append((end, state.phi-neutral.phi, reason))
    return MotorRange(True, "", neutral.phi, ends[0][0], ends[1][0], ends[0][1], ends[1][1], ends[0][2], ends[1][2])


def solve_motor(p: Parameters, interval: MotorRange, phi: float) -> MotorPose | None:
    """Forward solve, restricted to the selected neutral-connected assembly."""
    if not interval.valid:
        return None
    requested = min(interval.phi_upper, max(interval.phi_lower, phi))
    if abs(requested) <= 1e-14:
        return at_steering(p, 0.0, interval.neutral_phi)
    lower, upper = interval.mean_lower, interval.mean_upper
    increasing = interval.phi_at_upper > interval.phi_at_lower
    if abs(requested-interval.phi_at_lower) <= 1e-12:
        return at_steering(p, lower, interval.neutral_phi)
    if abs(requested-interval.phi_at_upper) <= 1e-12:
        return at_steering(p, upper, interval.neutral_phi)
    for _ in range(42):
        mid = (lower+upper)/2
        state = at_steering(p, mid, interval.neutral_phi)
        if state is None:
            return None
        if (state.phi-interval.neutral_phi < requested) == increasing:
            lower = mid
        else:
            upper = mid
    return at_steering(p, (lower+upper)/2, interval.neutral_phi)


def response(p: Parameters, interval: MotorRange, count: int = 181) -> list[dict]:
    rows = []
    for phi in np.linspace(interval.phi_lower, interval.phi_upper, count) if interval.valid else []:
        state = solve_motor(p, interval, float(phi))
        if state is not None:
            rows.append({"motor_deg": math.degrees(float(phi)), "steering_mean_deg": math.degrees(state.steering),
                         "wheel_left_deg": math.degrees(state.pose.heading_left), "wheel_right_deg": math.degrees(state.pose.heading_right),
                         "sensitivity_deg_per_deg": state.sensitivity, "rod_error_mm": state.closure_error,
                         "steering_rod_error_mm": state.pose.closure_error})
    return rows


def response_csv(rows: list[dict]) -> str:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return output.getvalue()
