"""Constrained discrete search, fair objectives, Pareto dominance and immutability."""
from dataclasses import replace
import math
import numpy as np
import pytest
from steering.motor import at_steering
from steering.motor_search import SearchSpace, candidate_curve, grid_values, pareto_mask, search
from steering.parameters import Parameters, to_json


def test_pareto_agrees_with_strict_pairwise_dominance():
    objectives=np.array([(1,4),(2,2),(4,1),(3,3),(2,4),(2,2),(1,5),(1,4)],dtype=float)
    expected=[not any(np.all(other<=point) and np.any(other<point) for other in objectives) for point in objectives]
    assert pareto_mask(objectives)==expected
    assert pareto_mask(np.empty((0,2)))==[]


def test_position_grid_stays_inside_requested_box():
    assert grid_values(-20,5,10)==(-20,-10,0)
    with pytest.raises(ValueError):grid_values(0,10,0)


def test_discrete_constraints_metrics_and_manual_state():
    p=replace(Parameters(),actuation_fraction=.3)
    before=to_json(p)
    space=SearchSpace(crank_lengths=(10.,20.),rod_lengths=(60.,80.),x_positions=(-80.,-60.),y_positions=(35.,55.))
    report=search(p,space)
    assert report.tested==32
    assert report.feasible
    assert report.tested==len(report.feasible)+sum(report.rejected.values())
    assert to_json(p)==before
    objective=np.array([(c.metrics.max_sensitivity,c.metrics.variation) for c in report.feasible])
    assert [c.pareto for c in report.feasible]==pareto_mask(objective)
    for candidate in report.feasible:
        q=candidate.parameters
        assert q.motor.crank_radius in space.crank_lengths
        assert q.motor.connecting_length in space.rod_lengths
        assert q.motor.x in space.x_positions and q.motor.y in space.y_positions
        assert q.motor.y>=25+space.min_behind
        assert q.actuation_fraction==.5
        assert candidate.interval.mean_lower < -space.target
        assert candidate.interval.mean_upper > space.target
    candidate=report.feasible[0]
    rows=candidate_curve(candidate,space.target)
    assert len(rows)==241
    assert rows[0]['steering_mean_deg']==pytest.approx(-25)
    assert rows[-1]['steering_mean_deg']==pytest.approx(25)
    for row in (rows[0],rows[120],rows[-1]):
        state=at_steering(candidate.parameters,math.radians(row['steering_mean_deg']),candidate.interval.neutral_phi)
        assert state.phi-candidate.interval.neutral_phi==pytest.approx(math.radians(row['motor_deg']),abs=1e-10)
        assert state.sensitivity==pytest.approx(row['sensitivity_deg_per_deg'],rel=1e-8)
        assert state.closure_error<1e-7
    sensitivity=np.abs([row['sensitivity_deg_per_deg'] for row in rows])
    assert candidate.metrics.max_sensitivity==pytest.approx(sensitivity.max())
    assert candidate.metrics.variation==pytest.approx((sensitivity.max()-sensitivity.min())/sensitivity.mean())


def test_constraints_reject_without_fabricating_candidates():
    p=Parameters()
    impossible=SearchSpace(crank_lengths=(10.,),rod_lengths=(20.,),x_positions=(10000.,),y_positions=(35.,))
    report=search(p,impossible)
    assert not report.feasible
    assert sum(report.rejected.values())==report.tested
    outside=replace(impossible,y_positions=(25.,))
    report=search(p,outside)
    assert sum(report.rejected.values())==report.tested
    assert all('margine' in reason for reason in report.rejected)
    with pytest.raises(ValueError):search(p,replace(impossible,target=math.pi/2))


def test_fast_reachability_distinguishes_neutral_and_travel():
    from steering.motor_search import prefilter
    base=SearchSpace(crank_lengths=(10.,),rod_lengths=(20.,),x_positions=(0.,),y_positions=(51.,))
    result=prefilter(Parameters(),base)
    assert result.total==2 and result.rejected_neutral==0
    assert result.rejected_travel==2 and result.remaining==0
    tangent=prefilter(Parameters(),replace(base,crank_lengths=(30.,),rod_lengths=(10.,),y_positions=(45.,)))
    assert tangent.rejected_neutral==2 and tangent.remaining==0


def test_large_raw_grid_is_allowed_when_fast_filter_removes_it(monkeypatch):
    import steering.motor_search as module
    def unexpected(*args):
        raise AssertionError('Impossible candidates must not reach detailed analysis')
    monkeypatch.setattr(module,'_response',unexpected)
    space=SearchSpace(crank_lengths=tuple(range(1,101)),rod_lengths=tuple(range(1,101)),
                      x_positions=(10000.,),y_positions=(35.,))
    progress=[]
    result=search(Parameters(),space,lambda n,total,text:progress.append(n/total))
    assert result.tested==20000 and result.detailed_tested==0
    assert sum(result.prefilter_rejected.values())==20000
    assert sum(result.rejected.values())==20000 and not result.feasible
    assert progress[-1]==1
    # The cap still rejects a grid with too many genuinely reachable assemblies.
    dense=replace(space,crank_lengths=tuple(range(50,151)),rod_lengths=tuple(range(50,151)),
                  x_positions=(0.,),y_positions=(75.,),target=.01)
    with pytest.raises(ValueError,match='Dopo il prefiltro'):
        search(Parameters(),dense)
