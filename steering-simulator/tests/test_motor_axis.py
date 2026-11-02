"""Footprint geometry and lazy, reversible certification of the exact Pareto."""
from dataclasses import replace
import numpy as np
import pytest
from steering.parameters import Parameters,Motor
from steering.motor_search import SearchSpace,search,pareto_mask
from steering.interferences import Obstacle,rectangles
from steering.motor_axis import axis_pareto,axis_clearance_from_poses,candidate_axis_clearance


def test_shaft_reservation_uses_full_travel_and_shared_joint_radii():
    p=replace(Parameters(),motor=Motor(0.,0.,20.,20.),physical=replace(Parameters().physical,link_width=2.))
    pins=np.tile([20.,0.],(3,1));points=np.tile([20.,20.],(3,1))
    assert axis_clearance_from_poses(p,points,pins,())==pytest.approx(15.)  # Q, not its attached crank
    centers=np.array([[10.,0.],[5.,0.],[10.,0.]])
    obstacle=Obstacle('ruota',rectangles(centers,np.tile([1.,0.],(3,1)),np.tile([0.,1.],(3,1))))
    assert axis_clearance_from_poses(p,points,pins,(obstacle,))==pytest.approx(4.)
    centers=np.tile([12.,0.],(3,1))
    obstacle=Obstacle('braccio SX',rectangles(centers,np.tile([1.,0.],(3,1)),np.tile([0.,1.],(3,1))),joint_center=centers)
    assert axis_clearance_from_poses(p,points,pins,(obstacle,))==pytest.approx(7.)


def test_lazy_pareto_promotes_reuses_and_recovers_candidates():
    result=search(Parameters(),SearchSpace(target=.3,crank_lengths=(10.,20.),rod_lengths=(60.,80.),
                                          x_positions=(-80.,-60.),y_positions=(40.,60.)))
    template=result.feasible[0]
    assert np.isfinite(candidate_axis_clearance(template,.3))
    candidates=tuple(replace(template,id=i,metrics=replace(template.metrics,max_sensitivity=float(i),variation=float(i)),pareto=i==1)
                     for i in (1,2,3))
    values={1:5.,2:15.,3:30.};calls=[];cache={}
    def evaluate(c):calls.append(c.id);return values[c.id]
    assert [c.id for c in axis_pareto(candidates,20.,cache,evaluate)]==[2]
    assert calls==[1,2] and 3 not in cache
    assert [c.id for c in axis_pareto(candidates,21.,cache,evaluate)]==[2] and calls==[1,2]
    assert [c.id for c in axis_pareto(candidates,8.,cache,evaluate)]==[1] and calls==[1,2]
    # Contact rejects candidate 2, promotes and evaluates the previously dominated 3.
    assert [c.id for c in axis_pareto(candidates,30.,cache,evaluate)]==[3]
    assert calls==[1,2,3]
    assert axis_pareto(candidates,0.,cache)==candidates
    assert axis_pareto(candidates,100.,cache)==()
    assert not candidates[1].pareto  # original front never modified
    for diameter in (8.,20.,30.,40.):
        valid=[c for c in candidates if values[c.id]>diameter/2+c.parameters.length_tolerance]
        flags=pareto_mask(np.array([(c.metrics.max_sensitivity,c.metrics.variation) for c in valid]))
        assert [c.id for c in axis_pareto(candidates,diameter,cache)]==[c.id for c,flag in zip(valid,flags) if flag]
