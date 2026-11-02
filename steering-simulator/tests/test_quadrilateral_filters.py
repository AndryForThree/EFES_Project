"""Explore the saved geometry set without evaluating its kinematics again."""
from steering.parameters import modular_defaults
from steering.quadrilateral_search import search_quadrilaterals
from steering.quadrilateral_filters import GeometryFilters,filter_candidates,filters_from_settings


def test_dimension_filters_promote_a_dominated_geometry_without_recalculation(monkeypatch):
    import steering.quadrilateral_search as solver
    result=search_quadrilaterals(modular_defaults(),[180.],[20.,30.],[180.],.3)
    assert [c.parameters.left.arm_length for c in result.candidates if c.pareto]==[30.]
    def forbidden(*args,**kwargs):raise AssertionError('Filtering must not evaluate geometry')
    for name in ('search_quadrilaterals','evaluate','ackermann_curve','point_motion_curve'):
        monkeypatch.setattr(solver,name,forbidden)
    filters=filters_from_settings(dict(quad_filter_spacings=[180.],quad_filter_lengths=[20.],quad_filter_ties=[180.]))
    filtered=filter_candidates(result,filters)
    assert len(filtered)==1 and filtered[0].pareto
    assert filtered[0].parameters.left.arm_length==20.
    assert not next(c for c in result.candidates if c.id==filtered[0].id).pareto
    assert filter_candidates(result,GeometryFilters())==result.candidates
    assert filter_candidates(result,GeometryFilters(spacings=()))==()
    assert filter_candidates(result,GeometryFilters(ties=(170.,)))==()
