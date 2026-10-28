"""Exact steering capacity and candidate comparison, without tuning objectives."""
from dataclasses import dataclass
from itertools import product
from .kinematics import steering_input, steering_limit
from .parameters import Parameters, symmetric_steering, validate_symmetric_setup


@dataclass(frozen=True)
class Evaluation:
    geometrically_valid: bool
    steering_limit: float  # mean wheel angle in radians, capped at 90 degrees
    at_deadpoint: bool
    left_positive: float
    right_positive: float
    reasons: tuple[str, ...] = ()


def evaluate(p: Parameters) -> Evaluation:
    try:
        validate_symmetric_setup(p)
        limit, at_deadpoint = steering_limit(p, respect_display=False)
        left = steering_input(p, limit)
        return Evaluation(True, limit, at_deadpoint, left, 2*limit-left)
    except ValueError as exc:
        return Evaluation(False, 0.0, False, 0.0, 0.0, (str(exc),))


@dataclass(frozen=True)
class Candidate:
    parameters: Parameters
    evaluation: Evaluation


def explore(p: Parameters, lengths: list[float], inclinations: list[float], tie_lengths: list[float]) -> list[Candidate]:
    if len(lengths)*len(inclinations)*len(tie_lengths) > 200:
        raise ValueError("Massimo 200 candidati per esplorazione.")
    candidates = []
    for length, inclination, tie_length in product(lengths, inclinations, tie_lengths):
        candidate = symmetric_steering(p, float(length), float(tie_length), float(inclination))
        candidates.append(Candidate(candidate, evaluate(candidate)))
    return sorted(candidates, key=lambda c: (not c.evaluation.geometrically_valid, -c.evaluation.steering_limit))
