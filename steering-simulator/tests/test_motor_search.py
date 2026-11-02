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
    space=SearchSpace(crank_lengths=(10.,20.),rod_lengths=(60.,80.),x_positions=(-80.,-60.),y_positions=(40.,60.))
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
    impossible=SearchSpace(crank_lengths=(10.,),rod_lengths=(20.,),x_positions=(10000.,),y_positions=(40.,))
    report=search(p,impossible)
    assert not report.feasible
    assert sum(report.rejected.values())==report.tested
    outside=replace(impossible,y_positions=(20.,))
    report=search(p,outside)
    assert sum(report.rejected.values())==report.tested
    assert all('margine' in reason for reason in report.rejected)
    with pytest.raises(ValueError):search(p,replace(impossible,target=math.pi/2))


def test_fast_reachability_distinguishes_neutral_and_travel():
    from steering.motor_search import prefilter
    base=SearchSpace(crank_lengths=(10.,),rod_lengths=(20.,),x_positions=(0.,),y_positions=(50.,),target=math.radians(30))
    result=prefilter(Parameters(),base)
    assert result.total==2 and result.rejected_neutral==0
    assert result.rejected_travel==2 and result.remaining==0
    tangent=prefilter(Parameters(),replace(base,crank_lengths=(25.,),rod_lengths=(10.,),y_positions=(40.,)))
    assert tangent.rejected_neutral==2 and tangent.remaining==0


def test_large_raw_grid_is_allowed_when_fast_filter_removes_it(monkeypatch):
    import steering.motor_search as module
    def unexpected(*args):
        raise AssertionError('Impossible candidates must not reach detailed analysis')
    monkeypatch.setattr(module,'_response',unexpected)
    space=SearchSpace(crank_lengths=tuple(range(1,101)),rod_lengths=tuple(range(1,101)),
                      x_positions=(10000.,),y_positions=(40.,))
    progress=[]
    result=search(Parameters(),space,lambda n,total,text:progress.append(n/total))
    assert result.tested==20000 and result.detailed_tested==0
    assert sum(result.prefilter_rejected.values())==20000
    assert sum(result.rejected.values())==20000 and not result.feasible
    assert progress[-1]==1
    # Reachable trials above the old cap still run when detailed checks reject them.
    dense=replace(space,crank_lengths=tuple(range(50,151)),rod_lengths=tuple(range(50,151)),
                  x_positions=(0.,),y_positions=(80.,),target=.01)
    monkeypatch.setattr(module,'MAX_FEASIBLE_CANDIDATES',2)
    monkeypatch.setattr(module,'_response',lambda *_:(None,'Escluso dal controllo dettagliato'))
    screening=module.prefilter(Parameters(),dense)
    assert screening.remaining > 10000
    assert not hasattr(screening,'choices')  # No retained Cartesian-product index list.
    result=search(Parameters(),dense)
    assert result.detailed_tested==screening.remaining
    assert not result.feasible
    assert sum(result.rejected.values())==result.tested


def test_only_fully_feasible_candidates_count_toward_runtime_memory_limit(monkeypatch):
    import steering.motor_search as module
    space=SearchSpace(target=.3,crank_lengths=(10.,20.),rod_lengths=(60.,80.),
                      x_positions=(-80.,-60.),y_positions=(40.,60.))
    baseline=search(Parameters(),space)
    count=len(baseline.feasible)
    assert count>1 and baseline.detailed_tested>count
    monkeypatch.setattr(module,'MAX_FEASIBLE_CANDIDATES',count)
    assert search(Parameters(),space)==baseline  # Exactly the cap is allowed.
    monkeypatch.setattr(module,'MAX_FEASIBLE_CANDIDATES',count-1)
    with pytest.raises(ValueError,match=f'{count}ª.*analisi'):
        search(Parameters(),space)


def test_chassis_grid_is_not_shifted_by_tie_height_or_centered_view():
    from steering.motor_search import chassis_grid_values,on_chassis_grid,prefilter
    from steering.parameters import steering_from_lengths
    p=steering_from_lengths(Parameters(),190.,30.,170.)
    y0=math.sqrt(30**2-10**2)
    xs=chassis_grid_values(-100,-20,10,origin=-p.pivot_spacing/2)
    ys=chassis_grid_values(y0+10,y0+50,10)
    assert xs[0]==-95. and ys==(40.,50.,60.,70.)
    assert all(on_chassis_grid(p,x,y) for x in xs for y in ys)
    assert all(y>=y0+10 and y<=y0+50 for y in ys)
    assert chassis_grid_values(y0+10,y0+50,20)==(40.,60.)
    with pytest.raises(ValueError,match='multiplo'):
        chassis_grid_values(0,100,15)
    with pytest.raises(ValueError,match='nodi'):
        chassis_grid_values(1,9,10)
    bad=SearchSpace(x_positions=(-90.,),y_positions=(40.,))
    with pytest.raises(ValueError,match='griglia telaio'):
        prefilter(p,bad)


def test_offset_attachment_holes_preserve_chassis_grid_and_real_kinematics():
    from steering.parameters import steering_from_lengths
    from steering.motor_search import central_attachment_holes,prefilter,on_chassis_grid
    from steering.reference import mounting_coordinates
    p=steering_from_lengths(Parameters(),180.,30.,170.)
    assert central_attachment_holes(p)==(80.,90.)
    space=SearchSpace(target=.3,crank_lengths=(10.,20.),rod_lengths=(60.,80.),
                      x_positions=(-80.,-60.),y_positions=(40.,60.),attachment_distances=(80.,90.))
    result=search(p,space)
    assert result.attachment_grid_checked and result.tested==64
    assert result.tested==len(result.feasible)+sum(result.rejected.values())
    assert len({c.id for c in result.feasible})==len(result.feasible)
    for distance in (80.,90.):
        candidate=next(c for c in result.feasible if c.parameters.actuation_fraction*p.tie_length==pytest.approx(distance))
        q=candidate.parameters
        assert on_chassis_grid(q,q.motor.x,q.motor.y)
        assert q.motor.x in space.x_positions and q.motor.y in space.y_positions
        points=mounting_coordinates(q)
        assert np.linalg.norm(points['T']-points['B_SX'])==pytest.approx(distance)
        assert points['T'][0]==pytest.approx(5.+distance)
        assert points['M'][0]%10==pytest.approx(0.)
        assert np.linalg.norm(points['Q']-points['T'])==pytest.approx(q.motor.connecting_length)
        assert np.linalg.norm(points['Q']-points['M'])==pytest.approx(q.motor.crank_radius)
        rows=candidate_curve(candidate,space.target)
        for row in (rows[0],rows[len(rows)//2],rows[-1]):
            actual=at_steering(q,math.radians(row['steering_mean_deg']),candidate.interval.neutral_phi)
            assert actual.sensitivity==pytest.approx(row['sensitivity_deg_per_deg'],rel=1e-8)
            assert actual.phi-candidate.interval.neutral_phi==pytest.approx(math.radians(row['motor_deg']),abs=1e-10)
    for invalid in ((85.,),(180.,),(-10.,),(80.,80.)):
        with pytest.raises(ValueError,match='attacchi T'):
            prefilter(p,replace(space,attachment_distances=invalid))
