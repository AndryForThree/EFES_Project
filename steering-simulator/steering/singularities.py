"""Scale-independent transmission diagnostics and analytic point velocities."""
from dataclasses import dataclass
import math
import numpy as np
from .geometry import Vector, perpendicular
from .kinematics import Pose, toggle_angles
from .parameters import Parameters, TRANSMISSION_WARNING_SINE


@dataclass(frozen=True)
class Diagnostics:
    ratio: float | None
    input_sine: float
    output_sine: float
    near_input_deadpoint: bool
    near_output_deadpoint: bool
    toggle_distance: float  # radians in input coordinate; inf if none
    point_velocity: Vector | None  # mm per radian of left input
    mismatch: float  # wheel heading difference, wrapped radians


def diagnose(p: Parameters, pose: Pose) -> Diagnostics:
    rod = pose.b_right-pose.b_left
    left_velocity = perpendicular(pose.b_left-pose.a_left)
    right_unit_velocity = perpendicular(pose.b_right-pose.a_right)
    numerator = float(rod @ left_velocity)
    denominator = float(rod @ right_unit_velocity)
    input_sine = abs(numerator)/(p.tie_length*p.left.arm_length)
    output_sine = abs(denominator)/(p.tie_length*p.right.arm_length)
    # Numerical tolerance is dimensionless; engineering warning is an internal diagnostic constant.
    numerical_sine = 1e-9
    near_output = pose.tangent or output_sine <= max(TRANSMISSION_WARNING_SINE, numerical_sine)
    near_input = input_sine <= max(TRANSMISSION_WARNING_SINE, numerical_sine)
    ratio = None if near_output else numerator/denominator
    velocity = None if ratio is None else (1-p.actuation_fraction)*left_velocity + p.actuation_fraction*right_unit_velocity*ratio
    roots = toggle_angles(p, pose.theta_left-math.pi, pose.theta_left+math.pi)
    distance = min((abs(root-pose.theta_left) for root in roots), default=math.inf)
    return Diagnostics(ratio, input_sine, output_sine, near_input, near_output,
                       distance, velocity, math.remainder(pose.heading_right-pose.heading_left, math.tau))
