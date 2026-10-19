"""Bounded design exploration. Sampling is screening, never collision proof."""
from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product
import math
import numpy as np
from .clearances import check_clearances, manufacturing_issues
from .kinematics import neutral_branch, neutral_tie_length, sweep, toggle_angles
from .parameters import Parameters
from .singularities import diagnose


@dataclass(frozen=True)
class Evaluation:
    geometrically_valid: bool
    well_conditioned: bool
    manufacturing_ok: bool
    clearance_ok: bool | None
    targets_met: bool
    max_mismatch: float
    min_toggle_distance: float
    ratio_error: float
    right_negative: float | None
    right_positive: float | None
    reasons: tuple[str, ...]
    sampled_poses: int

    @property
    def suitable(self) -> bool:
        return all((self.geometrically_valid, self.well_conditioned,
                    self.manufacturing_ok, self.clearance_ok, self.targets_met))


def evaluate(p: Parameters, count: int = 61) -> Evaluation:
    try:
        p.validate()
    except ValueError as exc:
        return Evaluation(False, False, False, None, False, math.inf, 0, math.inf, None, None, (str(exc),), 0)
    target = p.targets
    samples = sweep(p, -target.left_angle, target.left_angle, count)
    poses = [sample.pose for sample in samples if sample.pose is not None]
    diagnostics = [diagnose(p, pose) for pose in poses]
    valid = len(poses) == len(samples)
    boundaries = toggle_angles(p, -target.left_angle, target.left_angle)
    min_toggle = min((d.toggle_distance for d in diagnostics), default=0.0)
    conditioned = valid and not boundaries and all(
        not (d.near_input_deadpoint or d.near_output_deadpoint) for d in diagnostics
    ) and min_toggle >= target.min_toggle_angle
    mismatch = max((abs(d.mismatch) for d in diagnostics), default=math.inf)
    ratio_error = max((abs(d.ratio-target.target_ratio) if d.ratio is not None else math.inf
                       for d in diagnostics), default=math.inf)
    issues = manufacturing_issues(p)
    reasons = list(issues)
    neutral_ok = abs(neutral_tie_length(p)-p.tie_length) <= p.length_tolerance
    if not neutral_ok:
        reasons.append("Tirante incompatibile con le due staffe nella posa zero prevista.")
    if not valid:
        reasons.append("Una parte dell'intervallo richiesto non ammette chiusura.")
    if not conditioned:
        reasons.append("Punto morto, scarsa trasmissione o margine angolare insufficiente.")
    if mismatch > target.max_mismatch:
        reasons.append("Differenza di orientamento ruote oltre il limite.")
    if ratio_error > target.ratio_tolerance:
        reasons.append("Rapporto di trasmissione fuori dalla fascia obiettivo.")
    negative = samples[0].pose.heading_right if samples[0].pose else None
    positive = samples[-1].pose.heading_right if samples[-1].pose else None
    reached = (negative is not None and positive is not None
               and negative <= -0.98*target.right_angle and positive >= 0.98*target.right_angle)
    same_direction = all(pose.heading_left*pose.heading_right >= -1e-10 for pose in poses)
    if not reached:
        reasons.append("La ruota DX non raggiunge entrambi gli estremi richiesti (tolleranza 2%).")
    if not same_direction:
        reasons.append("Le ruote sterzano in direzioni opposte in parte dell'intervallo.")
    # Include every actual sampled pose; no early kinematic scoring can bypass clearance.
    risks = set()
    for pose in poses:
        for clearance in check_clearances(p, pose):
            if clearance.status in ("risk", "projected"):
                risks.add(f"{clearance.first} / {clearance.second}")
    clearance_ok = not risks if valid and p.physical.use_heights else None
    if risks:
        reasons.append("Ingombri da risolvere: " + ", ".join(sorted(risks)) + ".")
    if not p.physical.use_heights:
        reasons.append("Quote Z disattivate: verifica degli ingombri non conclusiva.")
    targets_met = neutral_ok and reached and same_direction and mismatch <= target.max_mismatch and ratio_error <= target.ratio_tolerance
    return Evaluation(valid, conditioned, not issues, clearance_ok, targets_met, mismatch,
                      min_toggle, ratio_error, negative, positive, tuple(reasons), len(poses))


@dataclass(frozen=True)
class Candidate:
    parameters: Parameters
    evaluation: Evaluation


def explore(p: Parameters, lengths: list[float], angles: list[float], spacings: list[float],
            count: int = 41) -> list[Candidate]:
    """Explore symmetric brackets, preserving wheel offsets, material and Z data.

    Every candidate explicitly gets its neutral tie length; the input is immutable.
    Arm angle is in radians; right arm mirrors about the Y axis.
    """
    if len(lengths)*len(angles)*len(spacings) > 200:
        raise ValueError("Massimo 200 candidati per esplorazione.")
    candidates = []
    for length, angle, spacing in product(lengths, angles, spacings):
        left = replace(p.left, arm_length=float(length), arm_angle=float(angle))
        right = replace(p.right, arm_length=float(length), arm_angle=math.pi-float(angle),
                        axle_x=-left.axle_x, axle_y=left.axle_y, heading_offset=-left.heading_offset)
        candidate = replace(p, pivot_spacing=float(spacing), left=left, right=right, symmetric=True)
        candidate = replace(candidate, tie_length=neutral_tie_length(candidate))
        candidate = replace(candidate, branch=neutral_branch(candidate) or -1)
        candidates.append(Candidate(candidate, evaluate(candidate, count)))
    return sorted(candidates, key=lambda item: (
        not item.evaluation.suitable, len(item.evaluation.reasons),
        item.evaluation.ratio_error, item.evaluation.max_mismatch))
