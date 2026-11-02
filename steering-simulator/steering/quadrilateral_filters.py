"""Filter completed geometry searches and rebuild the three-objective Pareto."""
from dataclasses import dataclass,replace
from .quadrilateral_search import geometry_pareto_mask


FILTER_KEYS=('quad_filter_spacings','quad_filter_lengths','quad_filter_ties')


@dataclass(frozen=True)
class GeometryFilters:
    spacings: tuple[float,...] | None = None
    lengths: tuple[float,...] | None = None
    ties: tuple[float,...] | None = None


def filters_from_settings(settings):
    return GeometryFilters(*(tuple(settings[key]) if key in settings else None for key in FILTER_KEYS))


def filter_candidates(result,filters):
    kept=[]
    for candidate in result.candidates:
        p=candidate.parameters
        if filters.spacings is not None and p.pivot_spacing not in filters.spacings:continue
        if filters.lengths is not None and p.left.arm_length not in filters.lengths:continue
        if filters.ties is not None and p.tie_length not in filters.ties:continue
        kept.append(candidate)
    flags=geometry_pareto_mask([(c.ackermann_error,-c.evaluation.steering_limit,-c.min_point_motion) for c in kept])
    return tuple(c if c.pareto==flag else replace(c,pareto=flag) for c,flag in zip(kept,flags))
