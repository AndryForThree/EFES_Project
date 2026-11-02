"""Vectorized rectangle contacts over the sampled steering travel.

Only motor crank/connecting rod versus wheels, steering arms and axle carriers.
The reserved disks around B SX, B DX and Q share one diameter. Q also checks the steering rod. The motor casing and
other fasteners are deliberately excluded. Q may intersect its own two links. Strips
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
    links_exempt: bool = False
    joint_center: np.ndarray | None = None  # B carried by this steering arm


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


def circle_overlaps_rectangle(centers, radius, polygons, tolerance=1e-9):
    """Exact disk/rotated-rectangle distance, including corner contacts."""
    edges=np.stack((polygons[:,1]-polygons[:,0],polygons[:,3]-polygons[:,0]),axis=1)
    lengths=np.linalg.norm(edges,axis=2)
    axes=edges/lengths[:,:,None]
    offset=centers-polygons.mean(axis=1)
    local=np.einsum('ni,nai->na',offset,axes)
    outside=np.maximum(np.abs(local)-lengths/2,0.)
    return np.einsum('ni,ni->n',outside,outside) <= (radius+tolerance)**2


def prepare_obstacles(p: Parameters, left_angles, right_angles):
    result = []
    ends = []
    for side, label, angles, pivot_x in ((p.left, 'SX', left_angles, -p.pivot_spacing/2),
                                         (p.right, 'DX', right_angles, p.pivot_spacing/2)):
        # Search supports only straight-neutral symmetric steering (heading_offset=0).
        cos, sin = np.cos(angles), np.sin(angles)
        a = np.tile([pivot_x, 0.], (len(angles), 1))
        b = a + side.arm_length*np.column_stack([np.cos(side.arm_angle+angles), np.sin(side.arm_angle+angles)])
        ends.append(b)
        c = a + np.column_stack([side.axle_x*cos-side.axle_y*sin, side.axle_x*sin+side.axle_y*cos])
        wheel = rectangles(c, np.column_stack([cos, sin])*p.physical.wheel_width/2,
                           np.column_stack([-sin, cos])*p.physical.wheel_diameter/2)
        result.extend((Obstacle(f'ruota {label}', wheel),
                       Obstacle(f'braccio {label}', strips(a, b, p.physical.link_width),joint_center=b),
                       Obstacle(f'staffa {label}', strips(a, c, p.physical.link_width))))
    result.append(Obstacle('tirante',strips(ends[0],ends[1],p.physical.link_width),links_exempt=True))
    return tuple(result)


def _intersection_outside_joint(first,second,center,radius,tolerance):
    """Exact convex clipping; shared-end overlap is allowed only near its joint."""
    clipped=list(first)
    for a,b in zip(second,np.roll(second,-1,axis=0)):
        if not clipped:return False
        edge=b-a;length=np.linalg.norm(edge)
        def distance(point):
            v=point-a
            return (edge[0]*v[1]-edge[1]*v[0])/length
        result=[];previous=clipped[-1];old=distance(previous)
        for current in clipped:
            new=distance(current)
            if (old>=-tolerance)!=(new>=-tolerance):
                result.append(previous+(current-previous)*(old/(old-new)))
            if new>=-tolerance:result.append(current)
            previous=current;old=new
        clipped=result
    return any(np.linalg.norm(point-center)>radius+tolerance for point in clipped)


def motor_interference(p: Parameters, points, pins, obstacles):
    radius=p.physical.q_joint_diameter/2  # common reserved radius of B SX, B DX and Q
    for obstacle in obstacles:
        if np.any(circle_overlaps_rectangle(pins,radius,obstacle.polygons,p.length_tolerance)):
            return f'Interferenza 2D: giunto Q / {obstacle.name}'
    center = np.broadcast_to([p.motor.x, p.motor.y], pins.shape)
    outlines=(('leva motore',strips(center,pins,p.physical.link_width)),
              ('astina motore',strips(pins,points,p.physical.link_width)))
    for obstacle in obstacles:
        joint=obstacle.joint_center
        if joint is None:continue
        label=obstacle.name.replace('braccio','giunto B')
        if np.any(np.linalg.norm(pins-joint,axis=1)<=2*radius+p.length_tolerance):
            return f'Interferenza 2D: giunto Q / {label}'
        attached=np.all(np.linalg.norm(points-joint,axis=1)<=p.length_tolerance)
        for name,outline in outlines:
            if name=='astina motore' and attached:continue
            if np.any(circle_overlaps_rectangle(joint,radius,outline,p.length_tolerance)):
                return f'Interferenza 2D: {name} / {label}'
    for name,outline in outlines:
        for obstacle in obstacles:
            if obstacle.links_exempt:continue
            contacts=overlaps(outline,obstacle.polygons,p.length_tolerance)
            if not np.any(contacts):continue
            joint=obstacle.joint_center
            if name=='astina motore' and joint is not None and np.all(np.linalg.norm(points-joint,axis=1)<=p.length_tolerance):
                # The shared pin and the two link-end caps intentionally overlap.
                shared_radius=max(radius,p.physical.link_width/np.sqrt(2))
                if not any(_intersection_outside_joint(outline[i],obstacle.polygons[i],joint[i],shared_radius,p.length_tolerance)
                           for i in np.flatnonzero(contacts)):
                    continue
            return f'Interferenza 2D: {name} / {obstacle.name}'
    return ''


def crank_rear_clearance(p: Parameters, pins, obstacles):
    """Minimum signed gap behind the moving rod's rear face over all poses.

    The B SX→B DX direction transports the rear normal from neutral (+Y).
    Use every corner of the rendered crank rectangle, including its end overhang.
    Positive means the complete crank stays behind the rod; contact is zero.
    """
    tie=next(o.polygons for o in obstacles if o.name=='tirante')
    direction=tie[:,1]-tie[:,0]
    direction/=np.linalg.norm(direction,axis=1)[:,None]
    rear=np.column_stack([-direction[:,1],direction[:,0]])
    center=np.broadcast_to([p.motor.x,p.motor.y],pins.shape)
    outline=strips(center,pins,p.physical.link_width)
    rod_center=tie.mean(axis=1)
    signed=np.einsum('nvi,ni->nv',outline-rod_center[:,None,:],rear)
    return float(np.min(signed)-p.physical.link_width/2)
