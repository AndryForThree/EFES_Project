"""Small local canvas component; Python is not involved in the frame loop."""
from dataclasses import asdict
from pathlib import Path
import streamlit.components.v1 as components
from steering.kinematics import steering_limit
from steering.parameters import Parameters
from steering.motor import MotorRange
from .dimensions import display_dimensions

_component = components.declare_component("steering_motion", path=str(Path(__file__).with_name("browser")))


def browser_motion(p: Parameters, signature: str, motor_range: MotorRange, *, key: str = "steering_motion", steering_only: bool = False, initial_state: dict | None = None, motor_axis_diameter: float = 0.):
    limit, geometric = steering_limit(p)
    visuals=display_dimensions(p)
    visuals['motor_axis_radius']=motor_axis_diameter/2
    return _component(parameters=asdict(p), signature=signature, steering_only=steering_only, initial_state=initial_state or {},
                      display_dimensions=visuals,
                      steering_limit=limit, geometric_limit=geometric, motor_range=asdict(motor_range),
                      key=key, default=None)
