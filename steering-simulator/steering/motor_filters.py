"""Pure filtering of completed searches: no geometry solving and no mutation."""
from dataclasses import dataclass,replace
import math
import numpy as np
from .motor_search import pareto_mask


FILTER_KEYS=('motor_filter_cranks','motor_filter_rods','motor_filter_assemblies',
             'motor_filter_xmin','motor_filter_xmax','motor_filter_ymin','motor_filter_ymax','motor_filter_rear')


@dataclass(frozen=True)
class MotorFilters:
    crank_lengths: tuple[float,...] | None = None
    rod_lengths: tuple[float,...] | None = None
    assemblies: tuple[int,...] = (1,-1)
    x_bounds: tuple[float,float] | None = None  # public coordinates from A SX
    y_bounds: tuple[float,float] | None = None
    rear_only: bool = False


def filters_from_settings(settings):
    def bounds(low,high):
        return (settings[low],settings[high]) if low in settings and high in settings else None
    return MotorFilters(tuple(settings['motor_filter_cranks']) if 'motor_filter_cranks' in settings else None,
                        tuple(settings['motor_filter_rods']) if 'motor_filter_rods' in settings else None,
                        tuple(settings.get('motor_filter_assemblies',(1,-1))),
                        bounds('motor_filter_xmin','motor_filter_xmax'),bounds('motor_filter_ymin','motor_filter_ymax'),
                        settings.get('motor_filter_rear',False))


def filter_candidates(result, filters):
    for bounds in (filters.x_bounds,filters.y_bounds):
        if bounds is not None and (not all(math.isfinite(v) for v in bounds) or bounds[0]>bounds[1]):
            raise ValueError('Zona del filtro non valida: minimo ≤ massimo, con valori finiti.')
    if filters.rear_only and not getattr(result,'rear_clearance_checked',False):
        raise ValueError('Rilancia una volta la ricerca per calcolare la distanza della leva dal tirante mobile.')
    kept=[]
    for candidate in result.feasible:
        p=candidate.parameters;m=p.motor
        if filters.crank_lengths is not None and m.crank_radius not in filters.crank_lengths:continue
        if filters.rod_lengths is not None and m.connecting_length not in filters.rod_lengths:continue
        if m.assembly not in filters.assemblies:continue
        if filters.x_bounds and not filters.x_bounds[0]<=m.x+p.pivot_spacing/2<=filters.x_bounds[1]:continue
        if filters.y_bounds and not filters.y_bounds[0]<=m.y<=filters.y_bounds[1]:continue
        if filters.rear_only and (candidate.rear_clearance is None or candidate.rear_clearance<=p.length_tolerance):continue
        kept.append(candidate)
    front=pareto_mask(np.array([(c.metrics.max_sensitivity,c.metrics.variation) for c in kept]))
    return tuple(c if c.pareto==flag else replace(c,pareto=flag) for c,flag in zip(kept,front))
