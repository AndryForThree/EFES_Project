"""On-demand shaft-footprint checks, cached as one radius per candidate."""
from dataclasses import replace
import math
import numpy as np
from .motor_search import sample_steering,_response,pareto_mask
from .interferences import prepare_obstacles,strips


def point_rectangle_distance(centers,polygons):
    edges=np.stack((polygons[:,1]-polygons[:,0],polygons[:,3]-polygons[:,0]),axis=1)
    lengths=np.linalg.norm(edges,axis=2);axes=edges/lengths[:,:,None]
    local=np.einsum('ni,nai->na',centers-polygons.mean(axis=1),axes)
    outside=np.maximum(np.abs(local)-lengths/2,0.)
    return np.linalg.norm(outside,axis=1)


def axis_clearance_from_poses(p,points,pins,obstacles):
    """Largest shaft radius before contact over the sampled travel, in mm.

    The crank is attached to M and intentionally exempt. The connecting rod,
    Q, both B disks, wheels, arms, carriers and steering rod remain obstacles.
    """
    center=np.broadcast_to([p.motor.x,p.motor.y],pins.shape)
    radius=p.physical.q_joint_diameter/2
    distances=[np.linalg.norm(center-pins,axis=1).min()-radius]
    distances.append(point_rectangle_distance(center,strips(pins,points,p.physical.link_width)).min())
    for obstacle in obstacles:
        distances.append(point_rectangle_distance(center,obstacle.polygons).min())
        if obstacle.joint_center is not None:
            distances.append(np.linalg.norm(center-obstacle.joint_center,axis=1).min()-radius)
    return float(min(distances))


def candidate_axis_clearance(candidate,target,count=241):
    p=candidate.parameters
    samples=sample_steering(p,target,count)
    values,reason=_response(p,samples)
    if values is None:raise ValueError('Verifica asse non disponibile: '+reason)
    return axis_clearance_from_poses(p,samples.points,values[2],
                                    prepare_obstacles(p,samples.left_angles,samples.right_angles))


def axis_pareto(candidates,diameter,cache,evaluate=None):
    """Certify the exact feasible Pareto, testing front layers only as needed.

    Unknown dominated candidates stay in the original search, not labelled as
    valid or invalid. Removing a failed front can promote and test them later.
    A smaller diameter or different fixed filters starts from the full set again.
    """
    if not math.isfinite(diameter) or diameter<0:raise ValueError('Diametro asse non valido.')
    if diameter==0:return tuple(candidates)
    radius=diameter/2
    def passes(c):return cache[c.id]>radius+c.parameters.length_tolerance
    active=[c for c in candidates if c.id not in cache or passes(c)]
    while active:
        flags=pareto_mask(np.array([(c.metrics.max_sensitivity,c.metrics.variation) for c in active]))
        front=[c for c,flag in zip(active,flags) if flag]
        failed=set()
        for c in front:
            if c.id not in cache:
                if evaluate is None:raise ValueError('Verifica ingombro asse mancante: apri i risultati motore per completarla.')
                value=float(evaluate(c))
                if not math.isfinite(value):raise ValueError('Distanza asse non valida.')
                cache[c.id]=value
            if not passes(c):failed.add(c.id)
        if not failed:
            return tuple(c if c.pareto else replace(c,pareto=True) for c in front)
        active=[c for c in active if c.id not in failed]
    return ()
