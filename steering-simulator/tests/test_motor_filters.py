"""Result exploration preserves originals, promotes Pareto points and never solves geometry."""
from dataclasses import replace
import pytest
from steering.motor_search import SearchSpace,search
from steering.parameters import Parameters
from steering.motor_filters import MotorFilters,filter_candidates


def test_filters_recompute_pareto_without_solving_or_mutating(monkeypatch):
    import steering.motor_search as solver
    original=search(Parameters(),SearchSpace(target=.3,crank_lengths=(10.,20.),rod_lengths=(60.,80.),
                                            x_positions=(-80.,-60.),y_positions=(40.,60.)))
    assert original.rear_clearance_checked
    template=original.feasible[0]
    records=[]
    for i,(crank,rod,x,y,assembly,gap) in enumerate(((10.,60.,-80.,40.,1,-1.),(20.,80.,-60.,60.,-1,2.),(30.,80.,-60.,60.,-1,3.)),1):
        p=replace(template.parameters,motor=replace(template.parameters.motor,crank_radius=crank,connecting_length=rod,x=x,y=y,assembly=assembly))
        records.append(replace(template,id=i,parameters=p,metrics=replace(template.metrics,max_sensitivity=float(i),variation=i/10),
                               pareto=i==1,rear_clearance=gap))
    result=replace(original,feasible=tuple(records))
    def forbidden(*args,**kwargs):raise AssertionError('Filters must not run kinematics/search')
    for name in ('search','solve','sample_steering','build_range','_response'):
        monkeypatch.setattr(solver,name,forbidden)
    filters=MotorFilters(crank_lengths=(20.,30.),rod_lengths=(80.,),assemblies=(-1,),x_bounds=(30.,30.),y_bounds=(60.,60.))
    filtered=filter_candidates(result,filters)
    assert [c.id for c in filtered]==[2,3]
    assert [c.pareto for c in filtered]==[True,False]
    assert result.feasible[1].pareto is False
    rear=filter_candidates(result,MotorFilters(rear_only=True))
    assert [c.id for c in rear]==[2,3] and rear[0].pareto
    assert filter_candidates(result,MotorFilters(crank_lengths=()))==()
    assert filter_candidates(result,MotorFilters())==result.feasible
    with pytest.raises(ValueError,match='Zona'):
        filter_candidates(result,MotorFilters(x_bounds=(30.,10.)))
    with pytest.raises(ValueError,match='Rilancia'):
        filter_candidates(replace(result,rear_clearance_checked=False),MotorFilters(rear_only=True))
