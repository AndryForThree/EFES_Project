"""Small local canvas component; Python is not involved in the frame loop."""
from dataclasses import asdict
from pathlib import Path
import streamlit.components.v1 as components
from steering.kinematics import toggle_angles
from steering.parameters import Parameters

_component = components.declare_component("steering_motion", path=str(Path(__file__).with_name("browser")))


def browser_motion(p: Parameters, signature: str):
    return _component(parameters=asdict(p), signature=signature,
                      boundaries=toggle_angles(p, -p.display_range, p.display_range),
                      key="steering_motion", default=None)
