"""Immutable geometry and versioned, validated configuration persistence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import math
from typing import Any


@dataclass(frozen=True)
class Bracket:
    arm_length: float = 25.0
    arm_angle: float = math.pi / 2  # angle from +X, measured in global zero pose
    axle_x: float = -25.0
    axle_y: float = 0.0
    heading_offset: float = 0.0  # angle relative to forward (0, -1)


@dataclass(frozen=True)
class Physical:
    wheel_diameter: float = 60.0
    wheel_width: float = 18.0
    link_width: float = 10.0


TRANSMISSION_WARNING_SINE = 0.05  # Internal diagnostic threshold; never a motion limit.


@dataclass(frozen=True)
class Motor:
    x: float = -60.0
    y: float = 25.0
    crank_radius: float = 15.0
    connecting_length: float = 60.0
    assembly: int = 1


@dataclass(frozen=True)
class Parameters:
    pivot_spacing: float = 180.0
    left: Bracket = field(default_factory=Bracket)
    right: Bracket = field(default_factory=lambda: Bracket(axle_x=25.0))
    tie_length: float = 180.0
    physical: Physical = field(default_factory=Physical)
    display_range: float = math.radians(45)
    actuation_fraction: float = 0.5
    branch: int = -1
    symmetric: bool = True
    motor: Motor = field(default_factory=Motor)

    @property
    def scale(self) -> float:
        return max(self.pivot_spacing, self.tie_length,
                   self.left.arm_length, self.right.arm_length, 1e-12)

    @property
    def length_tolerance(self) -> float:
        return self.scale * 1e-10

    def validate(self) -> None:
        def finite(value: Any) -> None:
            if isinstance(value, dict):
                for item in value.values():
                    finite(item)
            elif type(value) is not bool and (
                not isinstance(value, (int, float)) or not math.isfinite(value)
            ):
                raise ValueError("Ogni parametro deve essere un numero finito.")
        finite(asdict(self))
        for group in (self, self.left, self.right, self.physical, self.motor):
            for name, value in asdict(group).items():
                if type(value) is bool and name not in ("symmetric",):
                    raise ValueError(f"{name}: un booleano non è una dimensione.")
        for name, value in (("Interasse", self.pivot_spacing), ("Tirante", self.tie_length),
                            ("Braccio SX", self.left.arm_length), ("Braccio DX", self.right.arm_length)):
            if value <= self.length_tolerance:
                raise ValueError(f"{name}: lunghezza nulla, negativa o numericamente degenere.")
        for name, value in asdict(self.physical).items():
            if value <= 0:
                raise ValueError(f"{name} deve essere positivo.")
        if type(self.branch) is not int or self.branch not in (-1, 1):
            raise ValueError("Ramo ammesso: -1 oppure +1.")
        if type(self.symmetric) is not bool:
            raise ValueError("La modalità simmetrica deve essere un booleano.")
        if self.symmetric and not all(math.isclose(a, b, abs_tol=1e-9) for a, b in (
            (self.right.arm_length, self.left.arm_length),
            (math.remainder(self.right.arm_angle + self.left.arm_angle - math.pi, 2*math.pi), 0),
            (self.right.axle_x, -self.left.axle_x), (self.right.axle_y, self.left.axle_y),
            (self.right.heading_offset, -self.left.heading_offset),
        )):
            raise ValueError("La configurazione simmetrica contiene staffe non speculari.")
        if not 0 <= self.actuation_fraction <= 1:
            raise ValueError("λ deve appartenere a [0, 1].")
        if not 0 < self.display_range <= math.pi/2:
            raise ValueError("Intervallo visualizzato: maggiore di 0 e fino a 90°.")
        if self.motor.crank_radius <= 0 or self.motor.connecting_length <= 0:
            raise ValueError("Le lunghezze della leva motore e dell'astina devono essere positive.")
        if type(self.motor.assembly) is not int or self.motor.assembly not in (-1, 1):
            raise ValueError("Montaggio della leva motore: +1 oppure −1.")


def symmetric_steering(template: Parameters, arm_length: float, tie_length: float,
                       inclination: float) -> Parameters:
    """Straight wheels at neutral; positive inclination points arms outward.

    B_L.x = -d/2 - L sin(beta), B_R.x = d/2 + L sin(beta),
    so t = d + 2 L sin(beta). Angles are radians, lengths mm.
    """
    if not all(math.isfinite(v) for v in (arm_length, tie_length, inclination)):
        raise ValueError("Le dimensioni e l'inclinazione devono essere finite.")
    if not -math.pi/2 < inclination < math.pi/2:
        raise ValueError("L'inclinazione deve essere compresa fra −90° e +90° esclusi.")
    spacing = tie_length - 2*arm_length*math.sin(inclination)
    if spacing <= max(arm_length, tie_length, 1e-12)*1e-10:
        raise ValueError("Il tirante è troppo corto per questa inclinazione e lunghezza del braccio: interasse perni non positivo.")
    left = replace(template.left, arm_length=arm_length,
                   arm_angle=math.pi/2+inclination, heading_offset=0.0)
    right = replace(left, arm_angle=math.pi/2-inclination, axle_x=-left.axle_x)
    result = replace(template, pivot_spacing=spacing, left=left, right=right,
                     tie_length=tie_length, symmetric=True, branch=-1)
    result.validate()
    return result


def validate_symmetric_setup(p: Parameters) -> None:
    """Reject unsupported imports instead of silently changing their dimensions."""
    p.validate()
    expected = symmetric_steering(p, p.left.arm_length, p.tie_length,
                                  p.left.arm_angle-math.pi/2)
    if (not p.symmetric or p.branch != -1
            or abs(p.pivot_spacing-expected.pivot_spacing) > p.length_tolerance
            or p.left.heading_offset != 0 or p.right.heading_offset != 0):
        raise ValueError("La configurazione deve avere staffe simmetriche, ruote dritte a zero e interasse coerente con tirante e inclinazione.")


def to_json(parameters: Parameters) -> str:
    parameters.validate()
    return json.dumps({"schema_version": 6, "units": {"length": "mm", "angle": "rad"},
                       "parameters": asdict(parameters)}, indent=2, allow_nan=False)


def from_json(contents: str | bytes) -> Parameters:
    try:
        if len(contents) > 100_000:
            raise ValueError("Configurazione troppo grande (massimo 100 kB).")
        raw = json.loads(contents)
        if set(raw) != {"schema_version", "units", "parameters"} or raw["schema_version"] not in (5, 6):
            raise ValueError("Formato non supportato: serve schema_version 5 o 6, con geometria del motore.")
        if raw["units"] != {"length": "mm", "angle": "rad"}:
            raise ValueError("Unità richieste: mm e rad.")
        data = dict(raw["parameters"])
        data["left"] = Bracket(**data["left"])
        data["right"] = Bracket(**data["right"])
        data["physical"] = Physical(**data["physical"])
        data["motor"] = Motor(**data["motor"])
        p = Parameters(**data)
        p.validate()
        return p
    except (TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError(f"Struttura della configurazione non valida: {exc}") from exc
