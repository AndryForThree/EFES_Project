"""Discrete chassis-grid search, independent of motor geometry and objectives."""
from dataclasses import dataclass, replace
from itertools import product
import math
import numpy as np
from .parameters import Parameters, on_modular_grid, steering_from_lengths
from .kinematics import steering_input
from .optimization import Evaluation, evaluate


@dataclass(frozen=True)
class GeometryCandidate:
    id: int
    parameters: Parameters
    evaluation: Evaluation
    left_reference: float
    right_reference: float
    ackermann_error: float = math.inf
    neutral_track: float = 0.
    pareto: bool = False
    min_point_motion: float = 0.  # mm per degree of mean steering

    @property
    def wheel_difference(self):
        # Positive steering turns right, hence the inner wheel is DX.
        return self.right_reference-self.left_reference


@dataclass(frozen=True)
class GeometrySearch:
    target: float
    tested: int
    rejected_closure: int
    rejected_range: int
    candidates: tuple[GeometryCandidate, ...]
    wheelbase: float = 200.
    rejected_track: int = 0
    sample_count: int = 241
    ackermann_checked: bool = False
    motion_checked: bool = False
    point_fraction: float = .5


def ackermann_curve(p: Parameters, wheelbase: float, target: float, count: int = 241):
    """Angles in radians; positive turns right (outer=SX, inner=DX).

    Fixed ideal track is measured between neutral wheel centers, not A pivots.
    cot(outer)-cot(inner)=track/wheelbase, evaluated without dividing by sin(0).
    Symmetry makes the negative steering half identical after swapping wheels.
    """
    track = p.pivot_spacing+p.right.axle_x-p.left.axle_x
    if not math.isfinite(wheelbase) or wheelbase <= 0:
        raise ValueError('Il passo virtuale deve essere finito e positivo.')
    if track <= p.length_tolerance:
        raise ValueError('La carreggiata fra i centri delle ruote a zero deve essere positiva.')
    means = np.linspace(0., target, count)
    outer = (means.copy() if p.tie_length == p.pivot_spacing else
             np.array([steering_input(p, float(m)) for m in means]))
    inner = 2*means-outer
    outer[0] = inner[0] = 0.
    ideal = np.arctan2(wheelbase*np.sin(outer), wheelbase*np.cos(outer)-track*np.sin(outer))
    return dict(mean=means, outer=outer, inner=inner, ideal=ideal, error=inner-ideal)


def point_motion_curve(p: Parameters, target: float, count: int = 241):
    """Analytic |dT/dm| in mm/degree over both steering directions.

    T is the material attachment point selected by lambda. Only lambda=0.5
    makes its speed necessarily even in mean steering; sample both halves.
    There are count samples per half, sharing neutral (2*count-1 in total).
    """
    means = np.linspace(-target, target, 2*count-1)
    d, t, length = p.pivot_spacing, p.tie_length, p.left.arm_length
    beta = p.left.arm_angle-math.pi/2
    if d == t:
        delta = np.zeros_like(means)
        delta_prime = np.zeros_like(means)
    else:
        root = np.sqrt(t*t-d*d*np.sin(means)**2)
        u = -d*np.cos(means)+root
        sine = u/(2*length)
        cosine = np.sqrt(np.maximum(0., 1-sine*sine))
        delta = np.arcsin(np.clip(sine,-1.,1.))-beta
        delta_prime = (d*np.sin(means)-d*d*np.sin(means)*np.cos(means)/root)/(2*length*cosine)
    left = p.left.arm_angle+means+delta
    right = p.right.arm_angle+means-delta
    a = length*np.column_stack([-np.sin(left),np.cos(left)])
    b = length*np.column_stack([-np.sin(right),np.cos(right)])
    velocity = ((1-p.actuation_fraction)*(1+delta_prime[:,None])*a
                +p.actuation_fraction*(1-delta_prime[:,None])*b)
    movement = np.linalg.norm(velocity,axis=1)*math.pi/180
    if d == t:
        movement[:] = length*math.pi/180
    return dict(mean=means, movement=movement)


def geometry_pareto_mask(objectives):
    """All objectives minimized; exact ties remain nondominated in any dimension."""
    objectives=np.asarray(objectives,dtype=float)
    return [not np.any(np.all(objectives<=point,axis=1) & np.any(objectives<point,axis=1))
            for point in objectives]


def search_quadrilaterals(p, spacings, lengths, ties, target, progress=None, *, wheelbase=200.):
    if not math.isfinite(wheelbase) or wheelbase <= 0:
        raise ValueError('Il passo virtuale deve essere finito e positivo.')
    axes = tuple(tuple(dict.fromkeys(values)) for values in (spacings, lengths, ties))
    if any(not values or any(not on_modular_grid(v) for v in values) for values in axes):
        raise ValueError('Interassi e lunghezze disponibili devono essere multipli positivi di 10 mm.')
    if not math.isfinite(target) or not 0 < target < math.pi/2:
        raise ValueError('La sterzata richiesta deve essere compresa fra 0° e 90° esclusi.')
    total = math.prod(len(values) for values in axes)
    if total > 2000:
        raise ValueError(f'{total} combinazioni: massimo 2000 per la ricerca del quadrilatero.')
    candidates = []
    closure = capacity = invalid_track = 0
    for index, (spacing, length, tie) in enumerate(product(*axes), 1):
        try:
            candidate = steering_from_lengths(p, spacing, length, tie)
        except ValueError:
            closure += 1
        else:
            result = evaluate(candidate)
            if not result.geometrically_valid or result.steering_limit <= target+1e-8:
                capacity += 1
            elif candidate.pivot_spacing+candidate.right.axle_x-candidate.left.axle_x <= candidate.length_tolerance:
                invalid_track += 1
            else:
                curve = ackermann_curve(candidate, wheelbase, target)
                error = float(np.max(np.abs(curve['error'])))
                motion = float(point_motion_curve(candidate,target)['movement'].min())
                track = candidate.pivot_spacing+candidate.right.axle_x-candidate.left.axle_x
                candidates.append(GeometryCandidate(index, candidate, result, float(curve['outer'][-1]),
                                                    float(curve['inner'][-1]), error, track, min_point_motion=motion))
        if progress and (index % 10 == 0 or index == total):
            progress(index, total)
    objectives = np.array([(c.ackermann_error, -c.evaluation.steering_limit, -c.min_point_motion) for c in candidates])
    candidates = [replace(c, pareto=front) for c, front in zip(candidates, geometry_pareto_mask(objectives))]
    candidates.sort(key=lambda c: (not c.pareto, -c.evaluation.steering_limit, c.ackermann_error, c.id))
    return GeometrySearch(target, total, closure, capacity, tuple(candidates), wheelbase=wheelbase,
                          rejected_track=invalid_track, ackermann_checked=True, motion_checked=True,
                          point_fraction=p.actuation_fraction)
