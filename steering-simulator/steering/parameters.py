"""Immutable geometry and versioned, validated configuration persistence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    arm_width: float = 10.0
    arm_thickness: float = 2.0
    rod_width: float = 10.0
    rod_thickness: float = 2.0
    bracket_width: float = 10.0  # projected horizontal axle support
    bracket_thickness: float = 2.0
    hole_diameter: float = 4.2
    pivot_diameter: float = 4.0
    bolt_head_diameter: float = 7.0
    washer_diameter: float = 9.0
    washer_thickness: float = 1.0
    spacer_height: float = 1.0
    end_margin: float = 5.0
    wheel_diameter: float = 60.0
    wheel_width: float = 18.0
    bracket_z: float = 2.0  # lower surface
    arm_z: float = 4.0
    rod_z: float = 8.0
    wheel_axle_z: float = 8.0
    use_heights: bool = True


@dataclass(frozen=True)
class Targets:
    left_angle: float = math.radians(25)
    right_angle: float = math.radians(25)
    max_mismatch: float = math.radians(2)
    target_ratio: float = 1.0
    ratio_tolerance: float = 0.15
    min_toggle_angle: float = math.radians(10)
    clearance: float = 1.0
    warning_sine: float = 0.05  # normalized |d dot B'| / (t * arm length)


@dataclass(frozen=True)
class Parameters:
    pivot_spacing: float = 180.0
    left: Bracket = field(default_factory=Bracket)
    right: Bracket = field(default_factory=lambda: Bracket(axle_x=25.0))
    tie_length: float = 180.0
    physical: Physical = field(default_factory=Physical)
    targets: Targets = field(default_factory=Targets)
    display_range: float = math.radians(45)
    actuation_fraction: float = 0.5
    branch: int = -1
    symmetric: bool = True

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
        for group in (self, self.left, self.right, self.physical, self.targets):
            for name, value in asdict(group).items():
                if type(value) is bool and name not in ("symmetric", "use_heights"):
                    raise ValueError(f"{name}: un booleano non è una dimensione.")
        for name, value in (("Interasse", self.pivot_spacing), ("Tirante", self.tie_length),
                            ("Braccio SX", self.left.arm_length), ("Braccio DX", self.right.arm_length)):
            if value <= self.length_tolerance:
                raise ValueError(f"{name}: lunghezza nulla, negativa o numericamente degenere.")
        for name, value in asdict(self.physical).items():
            if name.endswith("_z") or name == "use_heights":
                continue
            if value <= 0:
                raise ValueError(f"{name} deve essere positivo.")
        if type(self.branch) is not int or self.branch not in (-1, 1):
            raise ValueError("Ramo ammesso: -1 oppure +1.")
        if type(self.symmetric) is not bool or type(self.physical.use_heights) is not bool:
            raise ValueError("Modalità simmetrica e quote Z devono essere booleani.")
        if self.symmetric and not all(math.isclose(a, b, abs_tol=1e-9) for a, b in (
            (self.right.arm_length, self.left.arm_length),
            (math.remainder(self.right.arm_angle + self.left.arm_angle - math.pi, 2*math.pi), 0),
            (self.right.axle_x, -self.left.axle_x), (self.right.axle_y, self.left.axle_y),
            (self.right.heading_offset, -self.left.heading_offset),
        )):
            raise ValueError("La configurazione simmetrica contiene staffe non speculari.")
        if not 0 <= self.actuation_fraction <= 1:
            raise ValueError("λ deve appartenere a [0, 1].")
        if not 0 < self.display_range <= math.pi:
            raise ValueError("Intervallo visualizzato: maggiore di 0 e fino a 180°.")
        if not 0 < self.targets.warning_sine < 1:
            raise ValueError("Soglia normalizzata di allarme: tra 0 e 1.")
        for name in ("left_angle", "right_angle"):
            if not 0 < getattr(self.targets, name) < math.pi:
                raise ValueError("Gli angoli obiettivo devono essere tra 0 e 180° esclusi.")
        for name in ("max_mismatch", "ratio_tolerance", "min_toggle_angle", "clearance"):
            if getattr(self.targets, name) < 0:
                raise ValueError(f"{name} non può essere negativo.")


def to_json(parameters: Parameters) -> str:
    parameters.validate()
    return json.dumps({"schema_version": 2, "units": {"length": "mm", "angle": "rad"},
                       "parameters": asdict(parameters)}, indent=2, allow_nan=False)


def from_json(contents: str | bytes) -> Parameters:
    try:
        if len(contents) > 100_000:
            raise ValueError("Configurazione troppo grande (massimo 100 kB).")
        raw = json.loads(contents)
        if set(raw) != {"schema_version", "units", "parameters"} or raw["schema_version"] != 2:
            raise ValueError("Formato non supportato: serve schema_version 2, senza basetta. I vecchi file non vengono convertiti automaticamente.")
        if raw["units"] != {"length": "mm", "angle": "rad"}:
            raise ValueError("Unità richieste: mm e rad.")
        data = dict(raw["parameters"])
        data["left"] = Bracket(**data["left"])
        data["right"] = Bracket(**data["right"])
        data["physical"] = Physical(**data["physical"])
        data["targets"] = Targets(**data["targets"])
        p = Parameters(**data)
        p.validate()
        return p
    except (TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError(f"Struttura della configurazione non valida: {exc}") from exc
