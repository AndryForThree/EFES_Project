"""Boundary conversion from the solver's centered frame to the A SX datum."""
from dataclasses import replace
import numpy as np


def chassis_point(p, point):
    return np.asarray(point)+np.array([p.pivot_spacing/2,0.])


def chassis_pose(p, pose):
    if pose is None:
        return None
    names=('a_left','a_right','b_left','b_right','c_left','c_right','point')
    return replace(pose,**{name:chassis_point(p,getattr(pose,name)) for name in names})


def mounting_coordinates(p):
    """Neutral mounting coordinates in the public chassis frame, in mm."""
    from .kinematics import solve,select_pose
    from .motor import at_steering
    pose=chassis_pose(p,select_pose(solve(p,0.),p.branch))
    actuator=at_steering(p,0.)
    return dict(A_SX=pose.a_left,A_DX=pose.a_right,B_SX=pose.b_left,B_DX=pose.b_right,
                T=pose.point,M=chassis_point(p,[p.motor.x,p.motor.y]),
                Q=chassis_point(p,actuator.pin) if actuator else None)
