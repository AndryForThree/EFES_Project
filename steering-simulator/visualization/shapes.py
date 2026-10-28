"""Component outlines shared with the 2D interference model."""
from dataclasses import dataclass
import math
import numpy as np
from steering.geometry import Vector, rectangle, strip
from steering.kinematics import Pose
from steering.parameters import Parameters
from .dimensions import display_dimensions


@dataclass(frozen=True)
class Body:
    name: str
    polygon: Vector
    family: str


def bodies(p: Parameters, pose: Pose) -> list[Body]:
    D = display_dimensions(p)
    result = [Body("Tirante", strip(pose.b_left, pose.b_right, D['rod_width'], D['end_margin']), "rod")]
    for side, a, b, c, heading in (("SX", pose.a_left, pose.b_left, pose.c_left, pose.heading_left),
                                  ("DX", pose.a_right, pose.b_right, pose.c_right, pose.heading_right)):
        result.extend([
            Body(f"Braccio {side}", strip(a, b, D['arm_width'], D['end_margin']), "arm"),
            Body(f"Staffa {side}", strip(a, c, D['bracket_width'], D['end_margin']), "bracket"),
            Body(f"Ruota {side}", rectangle(c, p.physical.wheel_width, p.physical.wheel_diameter, heading), "wheel"),
        ])
        angles = np.linspace(0, math.tau, 16, endpoint=False)
        outline = D['joint_radius']*np.column_stack([np.cos(angles), np.sin(angles)])
        for prefix, point in (("Perno", a), ("Giunto", b)):
            result.append(Body(f"{prefix} {side}", point+outline, "joint"))
    return result
