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
from .parameters import Motor, Parameters, validate_symmetric_setup
from .interferences import prepare_obstacles, motor_interference


MAX_DETAILED_SEARCH = 10000
MAX_PREFILTER_COMBINATIONS = 2000000


@dataclass(frozen=True)
class SearchSpace:
    target: float = math.radians(25)
    crank_lengths: tuple[float, ...] = (10., 20., 30.)
    rod_lengths: tuple[float, ...] = (40., 50., 60., 70., 80., 90., 100.)
    x_positions: tuple[float, ...] = (-100., -80., -60., -40., -20.)
    y_positions: tuple[float, ...] = (35., 55., 75.)
    min_behind: float = 10.


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


@dataclass(frozen=True)
class SearchResult:
    base: Parameters
    space: SearchSpace
    tested: int
    feasible: tuple[MotorCandidate, ...]
    rejected: dict[str, int]
    sample_count: int = 241
    collision_checked: bool = False
    detailed_tested: int = 0
    prefilter_rejected: dict[str, int] = field(default_factory=dict)


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
    # Original (crank, rod, x, y) indices; only retain choices if usable by search.
    choices: tuple[tuple[int, int, int, int], ...]

    @property
    def rejected(self):
        return {name: count for name, count in (
            ('Asse motore fuori dal margine dietro al tirante neutro', self.rejected_margin),
            ('Prefiltro: collegamento impossibile o allineato a ruote dritte', self.rejected_neutral),
            ('Prefiltro: collegamento impossibile o allineato nella corsa richiesta', self.rejected_travel),
        ) if count}


def prefilter(p: Parameters, space: SearchSpace) -> Reachability:
    """Cheap assembly-independent triangle inequalities, before the detailed cap.

    Distances along the common sampled path are computed once per motor position,
    then tested against all length pairs using NumPy. Both A/B share this test.
    Only up to MAX_DETAILED_SEARCH/2 surviving pairs need to be retained.
    """
    validate_symmetric_setup(p)
    base = replace(p, actuation_fraction=.5)
    limit, _ = steering_limit(base, respect_display=False)
    if not math.isfinite(space.target) or not 0 < space.target < min(limit, math.pi/2)-1e-8:
        raise ValueError(f"Richiedi una sterzata positiva inferiore al limite dello sterzo ({math.degrees(limit):.2f}°).")
    axes = (space.crank_lengths, space.rod_lengths, space.x_positions, space.y_positions)
    if any(not values or any(not math.isfinite(v) for v in values) for values in axes):
        raise ValueError("Inserisci almeno un valore finito per ogni dimensione e posizione.")
    if min(space.crank_lengths+space.rod_lengths) <= 0:
        raise ValueError("Le lunghezze disponibili devono essere positive.")
    if not math.isfinite(space.min_behind) or space.min_behind < 0:
        raise ValueError("Il margine dietro al tirante deve essere finito e non negativo.")
    total = math.prod(len(values) for values in axes)*2
    if total > MAX_PREFILTER_COMBINATIONS:
        raise ValueError(f"{total} combinazioni teoriche: massimo {MAX_PREFILTER_COMBINATIONS} per il prefiltro rapido. Riduci la griglia o le liste di lunghezze.")
    samples = sample_steering(base, space.target)
    neutral = samples.points[len(samples.means)//2]
    radii = np.repeat(space.crank_lengths, len(space.rod_lengths))
    rods = np.tile(space.rod_lengths, len(space.crank_lengths))
    difference, reach = np.abs(radii-rods), radii+rods
    tolerance = np.maximum(np.maximum(base.scale, radii), rods)*1e-10
    remaining = rejected_neutral = rejected_travel = rejected_margin = 0
    choices = []
    for xi, x in enumerate(space.x_positions):
        for yi, y in enumerate(space.y_positions):
            if y < neutral[1]+space.min_behind-base.length_tolerance:
                rejected_margin += len(radii)*2
                continue
            center = np.array([x, y])
            d0 = float(np.linalg.norm(neutral-center))
            neutral_ok = (d0 > tolerance) & (d0-difference > tolerance) & (reach-d0 > tolerance)
            rejected_neutral += int(np.count_nonzero(~neutral_ok))*2
            if not np.any(neutral_ok):
                continue
            distances = np.linalg.norm(samples.points-center, axis=1)
            dmin, dmax = float(distances.min()), float(distances.max())
            travel_ok = neutral_ok & (dmin > tolerance) & (dmin-difference > tolerance) & (reach-dmax > tolerance)
            count = int(np.count_nonzero(travel_ok))*2
            rejected_travel += int(np.count_nonzero(neutral_ok & ~travel_ok))*2
            remaining += count
            slots = MAX_DETAILED_SEARCH//2-len(choices)
            if slots > 0:
                choices.extend((int(i)//len(space.rod_lengths), int(i)%len(space.rod_lengths), xi, yi)
                               for i in np.flatnonzero(travel_ok)[:slots])
    return Reachability(total, remaining, rejected_neutral, rejected_travel, rejected_margin,
                        tuple(choices) if remaining <= MAX_DETAILED_SEARCH else ())


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
    if screening.remaining > MAX_DETAILED_SEARCH:
        raise ValueError(f"Dopo il prefiltro restano {screening.remaining} montaggi su {screening.total} teorici: "
                         f"massimo {MAX_DETAILED_SEARCH} da analizzare. Riduci la zona o aumenta il passo.")
    base = replace(p, actuation_fraction=.5)
    samples = sample_steering(base, space.target)
    obstacles = prepare_obstacles(base, samples.left_angles, samples.right_angles)
    accepted, rejected = [], Counter(screening.rejected)
    done = 0
    for ri, si, xi, yi in screening.choices:
        radius, rod = space.crank_lengths[ri], space.rod_lengths[si]
        x, y = space.x_positions[xi], space.y_positions[yi]
        for assembly_index, assembly in enumerate((1, -1)):
            # Keep IDs stable relative to the unfiltered Cartesian product.
            index = (((ri*len(space.rod_lengths)+si)*len(space.x_positions)+xi)*len(space.y_positions)+yi)*2+assembly_index+1
            candidate = replace(base, motor=Motor(x, y, radius, rod, assembly))
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
                    accepted.append(MotorCandidate(index, candidate, interval, metrics))
            done += 1
            if progress is not None and (done % 10 == 0 or done == screening.remaining):
                progress(done, screening.remaining, f"{done}/{screening.remaining} analisi · {len(accepted)} ammissibili")
    if progress is not None and not screening.remaining:
        progress(1, 1, 'Tutte le combinazioni sono state escluse dal prefiltro rapido.')
    objectives = np.array([(c.metrics.max_sensitivity, c.metrics.variation) for c in accepted])
    mask = pareto_mask(objectives)
    accepted = [replace(c, pareto=front) for c, front in zip(accepted, mask)]
    accepted.sort(key=lambda c: (not c.pareto, c.metrics.max_sensitivity, c.metrics.variation, c.id))
    return SearchResult(base, space, screening.total, tuple(accepted), dict(rejected), collision_checked=True,
                        detailed_tested=done, prefilter_rejected=screening.rejected)


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
