"""Discrete motor search with explicit constraints and two Pareto objectives.

All sensitivity metrics use the same requested mean-steering interval. Candidate
lengths are exactly the supplied hole spacings. No manual state is mutated.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field, replace
import math
from typing import Callable
import numpy as np
from .kinematics import select_pose, solve, steering_input, steering_limit
from .motor import MotorRange, build_range, mean_point_velocity
from .parameters import Motor, Parameters, validate_symmetric_setup, on_modular_grid
from .interferences import prepare_obstacles, motor_interference, crank_rear_clearance


MAX_FEASIBLE_CANDIDATES = 50000
MAX_PREFILTER_COMBINATIONS = 2000000


@dataclass(frozen=True)
class SearchSpace:
    target: float = math.radians(25)
    crank_lengths: tuple[float, ...] = (10., 20., 30.)
    rod_lengths: tuple[float, ...] = (40., 50., 60., 70., 80., 90., 100.)
    x_positions: tuple[float, ...] = (-100., -80., -60., -40., -20.)
    y_positions: tuple[float, ...] = (40., 60., 80.)
    min_behind: float = 10.
    attachment_distances: tuple[float, ...] = ()  # mm from B SX along the rod; empty = nearest central holes


@dataclass(frozen=True)
class Metrics:
    max_sensitivity: float
    min_sensitivity: float
    mean_sensitivity: float
    variation: float  # (max |S| - min |S|) / mean |S|
    motor_excursion: float  # radians across the requested steering interval
    steering_margin: float  # minimum mean-angle margin beyond either target


@dataclass(frozen=True)
class MotorCandidate:
    id: int
    parameters: Parameters
    interval: MotorRange
    metrics: Metrics
    pareto: bool = False
    rear_clearance: float | None = None  # signed mm behind current rod, minimum across sampled travel


@dataclass(frozen=True)
class SearchResult:
    base: Parameters
    space: SearchSpace
    tested: int
    feasible: tuple[MotorCandidate, ...]
    rejected: dict[str, int]
    sample_count: int = 241
    collision_checked: bool = False
    q_clearance_checked: bool = False
    mounting_grid_checked: bool = False
    detailed_tested: int = 0
    prefilter_rejected: dict[str, int] = field(default_factory=dict)
    attachment_grid_checked: bool = False
    rear_clearance_checked: bool = False
    b_clearance_checked: bool = False


@dataclass(frozen=True)
class SteeringSamples:
    means: np.ndarray
    points: np.ndarray
    velocities: np.ndarray
    left_angles: np.ndarray
    right_angles: np.ndarray


def grid_values(lower: float, upper: float, step: float) -> tuple[float, ...]:
    if not all(math.isfinite(v) for v in (lower, upper, step)) or step <= 0 or upper < lower:
        raise ValueError("Zona non valida: minimo ≤ massimo e passo positivo.")
    count = math.floor((upper-lower)/step+1e-10)+1
    if count > 1000:
        raise ValueError("Troppi punti nella zona: aumenta il passo di ricerca.")
    return tuple(lower+i*step for i in range(count))


def chassis_grid_values(lower: float, upper: float, step: float = 10., origin: float = 0.):
    """Nodes on a fixed 10 mm chassis grid, cropped to bounds without shifting it.

    A coarser search step skips nodes from the first valid node inside the box.
    X origin is -d/2 (A SX) in the centered drawing; Y origin is zero.
    """
    if not all(math.isfinite(v) for v in (lower,upper,step,origin)) or upper < lower:
        raise ValueError('Zona non valida: limiti finiti e minimo ≤ massimo.')
    if not on_modular_grid(step):
        raise ValueError('Il passo di ricerca deve essere un multiplo positivo di 10 mm.')
    first=origin+10*math.ceil((lower-origin)/10-1e-10)
    if first > upper+1e-9:
        raise ValueError('La zona non contiene nodi della griglia telaio da 10 mm.')
    return grid_values(first,max(first,upper),step)


def _grid_node(value,origin=0.):
    n=(value-origin)/10
    return math.isfinite(n) and math.isclose(n,round(n),rel_tol=0.,abs_tol=1e-9)


def on_chassis_grid(p: Parameters,x: float,y: float):
    return on_modular_grid(p.pivot_spacing) and _grid_node(x,-p.pivot_spacing/2) and _grid_node(y)


def central_attachment_holes(p: Parameters) -> tuple[float, ...]:
    """Nearest holes to the midpoint, on the rod's own 10 mm pitch."""
    midpoint=p.tie_length/2
    return tuple(dict.fromkeys(10.*i for i in (math.floor(midpoint/10),math.ceil(midpoint/10))
                               if 0 <= 10.*i <= p.tie_length))


def attachment_distances(p: Parameters, space: SearchSpace) -> tuple[float, ...]:
    holes=space.attachment_distances or central_attachment_holes(p)
    if (not holes or len(set(holes))!=len(holes) or
        any(not math.isfinite(v) or v < 0 or v > p.tie_length or not _grid_node(v) for v in holes)):
        raise ValueError('Gli attacchi T devono essere fori distinti a passo 10 mm, tra 0 e la lunghezza del tirante, misurati da B SX.')
    return tuple(holes)


def _attachment_paths(p: Parameters, space: SearchSpace):
    holes=attachment_distances(p,space)
    if len(holes)==1:
        return (sample_steering(replace(p,actuation_fraction=holes[0]/p.tie_length),space.target),)
    # T and its velocity are affine in the material position along B SX–B DX.
    left=sample_steering(replace(p,actuation_fraction=0.),space.target)
    right=sample_steering(replace(p,actuation_fraction=1.),space.target)
    return tuple(SteeringSamples(left.means,
                 left.points+(distance/p.tie_length)*(right.points-left.points),
                 left.velocities+(distance/p.tie_length)*(right.velocities-left.velocities),
                 left.left_angles,left.right_angles) for distance in holes)


def sample_steering(p: Parameters, target: float, count: int = 241) -> SteeringSamples:
    means = np.linspace(-target, target, count)
    points, velocities, lefts, rights = [], [], [], []
    for mean in means:
        left = steering_input(p, float(mean))
        pose = select_pose(solve(p, left), p.branch, 2*float(mean)-left)
        if pose is None:
            raise ValueError("Lo sterzo non copre l'intervallo richiesto.")
        velocity = mean_point_velocity(p, pose, float(mean))
        if velocity is None:
            raise ValueError("L'intervallo richiesto raggiunge una singolarità dello sterzo.")
        points.append(pose.point)
        velocities.append(velocity)
        lefts.append(pose.heading_left)
        rights.append(pose.heading_right)
    return SteeringSamples(means, np.array(points), np.array(velocities), np.array(lefts), np.array(rights))


@dataclass(frozen=True)
class Reachability:
    total: int
    remaining: int
    rejected_neutral: int
    rejected_travel: int
    rejected_margin: int

    @property
    def rejected(self):
        return {name: count for name, count in (
            ('Asse motore fuori dal margine dietro al tirante neutro', self.rejected_margin),
            ('Prefiltro: collegamento impossibile o allineato a ruote dritte', self.rejected_neutral),
            ('Prefiltro: collegamento impossibile o allineato nella corsa richiesta', self.rejected_travel),
        ) if count}


def prefilter(p: Parameters, space: SearchSpace) -> Reachability:
    """Count reachable assemblies without retaining their Cartesian-product indices."""
    validate_symmetric_setup(p)
    base = p
    limit, _ = steering_limit(base, respect_display=False)
    if not math.isfinite(space.target) or not 0 < space.target < min(limit, math.pi/2)-1e-8:
        raise ValueError(f"Richiedi una sterzata positiva inferiore al limite dello sterzo ({math.degrees(limit):.2f}°).")
    axes = (space.crank_lengths, space.rod_lengths, space.x_positions, space.y_positions)
    if any(not values or any(not math.isfinite(v) for v in values) for values in axes):
        raise ValueError("Inserisci almeno un valore finito per ogni dimensione e posizione.")
    if not on_modular_grid(base.pivot_spacing):
        raise ValueError('L’interasse dei perni A deve essere multiplo di 10 mm per usare la griglia telaio.')
    if any(not _grid_node(x,-base.pivot_spacing/2) for x in space.x_positions) or any(not _grid_node(y) for y in space.y_positions):
        raise ValueError('Le posizioni motore devono appartenere alla griglia telaio 10 × 10 mm, riferita ad A SX.')
    if min(space.crank_lengths+space.rod_lengths) <= 0:
        raise ValueError("Le lunghezze disponibili devono essere positive.")
    if not math.isfinite(space.min_behind) or space.min_behind < 0:
        raise ValueError("Il margine dietro al tirante deve essere finito e non negativo.")
    holes = attachment_distances(base,space)
    total = math.prod(len(values) for values in axes)*len(holes)*2
    if total > MAX_PREFILTER_COMBINATIONS:
        raise ValueError(f"{total} combinazioni teoriche: massimo {MAX_PREFILTER_COMBINATIONS} per il prefiltro rapido. Riduci la griglia o le liste di lunghezze.")
    remaining = rejected_neutral = rejected_travel = rejected_margin = 0
    for _,_,_,indices,neutral,travel,margin in _reachability_batches(base,space,_attachment_paths(base,space)):
        remaining += len(indices)*2
        rejected_neutral += neutral
        rejected_travel += travel
        rejected_margin += margin
    return Reachability(total, remaining, rejected_neutral, rejected_travel, rejected_margin)


def _reachability_batches(base, space, paths):
    """One motor position at a time; temporary masks are discarded on advance."""
    radii = np.repeat(space.crank_lengths, len(space.rod_lengths))
    rods = np.tile(space.rod_lengths, len(space.crank_lengths))
    difference, reach = np.abs(radii-rods), radii+rods
    tolerance = np.maximum(np.maximum(base.scale, radii), rods)*1e-10
    for hi, samples in enumerate(paths):
        neutral = samples.points[len(samples.means)//2]
        for xi, x in enumerate(space.x_positions):
            for yi, y in enumerate(space.y_positions):
                if y < neutral[1]+space.min_behind-base.length_tolerance:
                    yield hi,xi,yi,(),0,0,len(radii)*2
                    continue
                center = np.array([x, y])
                d0 = float(np.linalg.norm(neutral-center))
                neutral_ok = (d0 > tolerance) & (d0-difference > tolerance) & (reach-d0 > tolerance)
                rejected_neutral = int(np.count_nonzero(~neutral_ok))*2
                if not np.any(neutral_ok):
                    yield hi,xi,yi,(),rejected_neutral,0,0
                    continue
                distances = np.linalg.norm(samples.points-center, axis=1)
                dmin, dmax = float(distances.min()), float(distances.max())
                travel_ok = neutral_ok & (dmin > tolerance) & (dmin-difference > tolerance) & (reach-dmax > tolerance)
                rejected_travel = int(np.count_nonzero(neutral_ok & ~travel_ok))*2
                yield hi,xi,yi,np.flatnonzero(travel_ok),rejected_neutral,rejected_travel,0


def _reachable_choices(base, space, paths):
    for hi,xi,yi,indices,_,_,_ in _reachability_batches(base,space,paths):
        for index in indices:
            ri,si=divmod(int(index),len(space.rod_lengths))
            yield hi,ri,si,xi,yi


def _response(p: Parameters, samples: SteeringSamples):
    """Vectorized exact inverse actuator geometry; no interpolated link lengths."""
    motor = p.motor
    delta = samples.points-np.array([motor.x, motor.y])
    h = np.linalg.norm(delta, axis=1)
    r, s = motor.crank_radius, motor.connecting_length
    tolerance = max(p.scale, r, s)*1e-10
    margin = np.minimum(r+s-h, h-abs(r-s))
    if np.any(h <= tolerance) or np.any(margin <= tolerance):
        return None, "Collegamento impossibile o leva–astina allineate nella corsa richiesta"
    e = delta/h[:, None]
    a = (h*h+(r-s)*(r+s))/(2*h)
    q2 = ((r+s+h)*(r+s-h)*(h+r-s)*(h-r+s))/(4*h*h)
    perpendicular_e = np.column_stack([-e[:, 1], e[:, 0]])
    crank = a[:, None]*e+motor.assembly*np.sqrt(np.maximum(0., q2))[:, None]*perpendicular_e
    pin = crank+np.array([motor.x, motor.y])
    rod = samples.points-pin
    crank_velocity = np.column_stack([-crank[:, 1], crank[:, 0]])
    numerator = np.einsum('ij,ij->i', rod, crank_velocity)
    denominator = np.einsum('ij,ij->i', rod, samples.velocities)
    if np.any(np.abs(numerator)/(s*r) <= 1e-8) or np.any(np.abs(denominator)/(s*max(p.left.arm_length, p.right.arm_length)) <= 1e-8):
        return None, "Punto morto nella corsa richiesta"
    if np.any(numerator*numerator[len(numerator)//2] <= 0) or np.any(denominator*denominator[len(denominator)//2] <= 0):
        return None, "Risposta non monotona nella corsa richiesta"
    sensitivity = numerator/denominator
    absolute_phi = np.unwrap(np.arctan2(crank[:, 1], crank[:, 0]))
    phi = absolute_phi-absolute_phi[len(absolute_phi)//2]
    if np.max(np.abs(phi)) >= math.pi-1e-10:
        return None, "Corsa motore oltre 180° dalla posa centrale"
    return (phi, sensitivity, pin), ""


def pareto_mask(objectives: np.ndarray) -> list[bool]:
    """Minimize both objectives; equal solutions do not dominate each other."""
    if len(objectives) == 0:
        return []
    order = sorted(range(len(objectives)), key=lambda i: (objectives[i, 0], objectives[i, 1]))
    result = [False]*len(objectives)
    best = math.inf
    previous = None
    previous_front = False
    for index in order:
        pair = tuple(objectives[index])
        if pair == previous:
            result[index] = previous_front
        else:
            result[index] = pair[1] < best
            if result[index]:
                best = pair[1]
        previous, previous_front = pair, result[index]
    return result


def search(p: Parameters, space: SearchSpace,
           progress: Callable[[int, int, str], None] | None = None) -> SearchResult:
    screening = prefilter(p, space)
    base = p
    holes = attachment_distances(base,space)
    paths = _attachment_paths(base,space)
    obstacles = prepare_obstacles(base, paths[0].left_angles, paths[0].right_angles)
    accepted, rejected = [], Counter(screening.rejected)
    done = 0
    progress_step=max(10,math.ceil(screening.remaining/200))
    for hi, ri, si, xi, yi in _reachable_choices(base,space,paths):
        samples=paths[hi]
        radius, rod = space.crank_lengths[ri], space.rod_lengths[si]
        x, y = space.x_positions[xi], space.y_positions[yi]
        for assembly_index, assembly in enumerate((1, -1)):
            # Keep IDs stable relative to the unfiltered Cartesian product.
            index = ((((hi*len(space.crank_lengths)+ri)*len(space.rod_lengths)+si)*len(space.x_positions)+xi)*len(space.y_positions)+yi)*2+assembly_index+1
            candidate = replace(base, actuation_fraction=holes[hi]/base.tie_length, motor=Motor(x, y, radius, rod, assembly))
            values, reason = _response(candidate, samples)
            if values is not None:
                collision = motor_interference(candidate, samples.points, values[2], obstacles)
                if collision:
                    values, reason = None, collision
            if values is None:
                rejected[reason] += 1
            else:
                interval = build_range(candidate)
                if (not interval.valid or interval.mean_lower >= -space.target-1e-8
                        or interval.mean_upper <= space.target+1e-8):
                    rejected["Punto morto o limite del ramo prima della sterzata richiesta"] += 1
                else:
                    phi, sensitivity, _ = values
                    magnitude = np.abs(sensitivity)
                    maximum, minimum, average = float(magnitude.max()), float(magnitude.min()), float(magnitude.mean())
                    metrics = Metrics(maximum, minimum, average, (maximum-minimum)/average,
                                      abs(float(phi[-1]-phi[0])), min(-space.target-interval.mean_lower, interval.mean_upper-space.target))
                    if len(accepted) >= MAX_FEASIBLE_CANDIDATES:
                        raise ValueError(f"Superato il limite di {MAX_FEASIBLE_CANDIDATES} soluzioni ammissibili: "
                                         f"trovata la {len(accepted)+1}ª dopo {done+1} analisi. "
                                         "Ricerca interrotta per contenere la memoria; restringi la zona o le liste dei componenti. "
                                         "I risultati parziali non vengono pubblicati.")
                    accepted.append(MotorCandidate(index, candidate, interval, metrics,
                                                   rear_clearance=crank_rear_clearance(candidate,values[2],obstacles)))
            done += 1
            if progress is not None and (done % progress_step == 0 or done == screening.remaining):
                progress(done, screening.remaining, f"{done}/{screening.remaining} analisi · {len(accepted)} ammissibili")
    if progress is not None and not screening.remaining:
        progress(1, 1, 'Tutte le combinazioni sono state escluse dal prefiltro rapido.')
    objectives = np.array([(c.metrics.max_sensitivity, c.metrics.variation) for c in accepted])
    mask = pareto_mask(objectives)
    for i,front in enumerate(mask):
        accepted[i]=replace(accepted[i],pareto=front)
    accepted.sort(key=lambda c: (not c.pareto, c.metrics.max_sensitivity, c.metrics.variation, c.id))
    return SearchResult(base, space, screening.total, tuple(accepted), dict(rejected), collision_checked=True, q_clearance_checked=True, mounting_grid_checked=True,
                        detailed_tested=done, prefilter_rejected=screening.rejected, attachment_grid_checked=True, rear_clearance_checked=True, b_clearance_checked=True)


def candidate_curve(candidate: MotorCandidate, target: float, count: int = 241) -> list[dict]:
    samples = sample_steering(candidate.parameters, target, count)
    values, reason = _response(candidate.parameters, samples)
    if values is None:
        raise ValueError(reason)
    phi, sensitivity, _ = values
    return [{"motor_deg": math.degrees(float(angle)), "steering_mean_deg": math.degrees(float(mean)),
             "wheel_left_deg": math.degrees(float(left)), "wheel_right_deg": math.degrees(float(right)),
             "sensitivity_deg_per_deg": float(s)}
            for angle, mean, left, right, s in zip(phi, samples.means, samples.left_angles, samples.right_angles, sensitivity)]
