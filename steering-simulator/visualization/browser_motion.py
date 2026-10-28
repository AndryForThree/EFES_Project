"""Small local canvas component; Python is not involved in the frame loop."""
from dataclasses import asdict
from pathlib import Path
import streamlit.components.v1 as components
from steering.kinematics import steering_limit
from steering.parameters import Parameters
from steering.motor import MotorRange
from .dimensions import display_dimensions

_component = components.declare_component("steering_motion", path=str(Path(__file__).with_name("browser")))


def browser_motion(p: Parameters, signature: str, motor_range: MotorRange, *, key: str = "steering_motion"):
    limit, geometric = steering_limit(p)
    return _component(parameters=asdict(p), signature=signature,
                      display_dimensions=display_dimensions(p),
                      steering_limit=limit, geometric_limit=geometric, motor_range=asdict(motor_range),
                      key=key, default=None)
