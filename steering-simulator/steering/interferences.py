"""Vectorized rectangle contacts over the sampled steering travel.

Only motor crank/connecting rod versus wheels, steering arms and axle carriers.
The steering rod, motor casing and fasteners are deliberately excluded. Strips
extend half their width beyond hole centers, matching both rendered views.
This is a sampled 2D filter, not continuous collision detection or a 3D check.
"""
from dataclasses import dataclass
import numpy as np
from .parameters import Parameters


@dataclass(frozen=True)
class Obstacle:
    name: str
    polygons: np.ndarray  # (poses, 4 corners, 2 coordinates)


SIGNS = np.array([[-1., -1.], [1., -1.], [1., 1.], [-1., 1.]])


def rectangles(center, horizontal, vertical):
    return (center[:, None, :] + SIGNS[None, :, :1]*horizontal[:, None, :]
            + SIGNS[None, :, 1:]*vertical[:, None, :])


def strips(start, end, width):
    start, end = np.broadcast_arrays(start, end)
    delta = end-start
    length = np.linalg.norm(delta, axis=1)
    unit = np.divide(delta, length[:, None], out=np.tile([1., 0.], (len(delta), 1)),
                     where=length[:, None] > 0)
    normal = np.column_stack([-unit[:, 1], unit[:, 0]])
    return rectangles((start+end)/2, unit*((length+width)/2)[:, None], normal*width/2)


def overlaps(first, second, tolerance=1e-9):
    """SAT for oriented rectangles at matching poses; touching counts as contact."""
    edges = np.concatenate((first[:, 1:3]-first[:, :2], second[:, 1:3]-second[:, :2]), axis=1)
    axes = np.stack((-edges[:, :, 1], edges[:, :, 0]), axis=-1)
    axes /= np.linalg.norm(axes, axis=-1, keepdims=True)
    a = np.einsum('nvi,nai->nav', first, axes)
    b = np.einsum('nvi,nai->nav', second, axes)
    separation = np.maximum(b.min(axis=2)-a.max(axis=2), a.min(axis=2)-b.max(axis=2))
    return np.all(separation <= tolerance, axis=1)


def prepare_obstacles(p: Parameters, left_angles, right_angles):
    result = []
    for side, label, angles, pivot_x in ((p.left, 'SX', left_angles, -p.pivot_spacing/2),
                                         (p.right, 'DX', right_angles, p.pivot_spacing/2)):
        # Search supports only straight-neutral symmetric steering (heading_offset=0).
        cos, sin = np.cos(angles), np.sin(angles)
        a = np.tile([pivot_x, 0.], (len(angles), 1))
        b = a + side.arm_length*np.column_stack([np.cos(side.arm_angle+angles), np.sin(side.arm_angle+angles)])
        c = a + np.column_stack([side.axle_x*cos-side.axle_y*sin, side.axle_x*sin+side.axle_y*cos])
        wheel = rectangles(c, np.column_stack([cos, sin])*p.physical.wheel_width/2,
                           np.column_stack([-sin, cos])*p.physical.wheel_diameter/2)
        result.extend((Obstacle(f'ruota {label}', wheel),
                       Obstacle(f'braccio {label}', strips(a, b, p.physical.link_width)),
                       Obstacle(f'staffa {label}', strips(a, c, p.physical.link_width))))
    return tuple(result)


def motor_interference(p: Parameters, points, pins, obstacles):
    center = np.broadcast_to([p.motor.x, p.motor.y], pins.shape)
    for name, start, end in (('leva motore', center, pins), ('astina motore', pins, points)):
        outline = strips(start, end, p.physical.link_width)
        for obstacle in obstacles:
            if np.any(overlaps(outline, obstacle.polygons, p.length_tolerance)):
                return f'Interferenza 2D: {name} / {obstacle.name}'
    return ''
