"""Physical hole spacings, modular candidates and motor-independent comparison."""
from dataclasses import replace
import math
import pytest
from steering.kinematics import select_pose, solve
from steering.parameters import Parameters, Motor, modular_defaults, steering_from_lengths
from steering.quadrilateral_search import search_quadrilaterals


def test_three_lengths_derive_inclination_and_keep_straight_neutral():
    p=steering_from_lengths(Parameters(),190.,30.,170.)
    pose=select_pose(solve(p,0),p.branch)
    assert p.pivot_spacing==190.
    assert math.sin(p.left.arm_angle-math.pi/2)==pytest.approx(-1/3)
    assert pose.heading_left==pytest.approx(0,abs=1e-12)
    assert pose.heading_right==pytest.approx(0,abs=1e-12)
    assert pose.closure_error < p.length_tolerance
    assert modular_defaults().left.arm_length==30.
    for spacing,tie in [(180.,240.),(180.,250.)]:
        with pytest.raises(ValueError,match='impossibile o allineata'):
            steering_from_lengths(Parameters(),spacing,30.,tie)


def test_search_filters_unbuildable_cases_and_ignores_motor():
    p=modular_defaults()
    result=search_quadrilaterals(p,[180.,190.],[20.,30.],[150.,180.,240.],math.radians(25))
    other=search_quadrilaterals(replace(p,motor=Motor(10000.,10000.,1.,1.)),
                              [180.,190.],[20.,30.],[150.,180.,240.],math.radians(25))
    assert result.tested==12
    assert len(result.candidates)+result.rejected_closure+result.rejected_range==12
    assert result.rejected_closure and result.candidates
    assert [(c.id,c.evaluation,c.wheel_difference) for c in result.candidates]==[
        (c.id,c.evaluation,c.wheel_difference) for c in other.candidates]
    for c in result.candidates:
        q=c.parameters
        assert q.pivot_spacing%10==q.left.arm_length%10==q.tie_length%10==0
        assert c.evaluation.steering_limit>result.target
        assert (c.left_reference+c.right_reference)/2==pytest.approx(result.target)
    with pytest.raises(ValueError,match='multipli'):
        search_quadrilaterals(p,[185.],[30.],[180.],.4)


def test_ackermann_reference_uses_wheel_centers_and_has_no_zero_singularity():
    from steering.quadrilateral_search import ackermann_curve
    p=modular_defaults()
    curve=ackermann_curve(p,200.,math.radians(25))
    assert curve['error'][0]==0
    outer=curve['outer'][-1]
    track=230.  # 180 mm pivots + two 25 mm outward wheel offsets
    expected=math.atan2(200*math.sin(outer),200*math.cos(outer)-track*math.sin(outer))
    assert curve['ideal'][-1]==pytest.approx(expected)
    assert curve['error'][-1]<0  # parallelogram under-steers the inner wheel
    assert 1/math.tan(outer)-1/math.tan(expected)==pytest.approx(track/200)
    shorter=ackermann_curve(p,100.,math.radians(25))
    assert shorter['ideal'][-1]>expected


def test_ackermann_pareto_matches_pairwise_dominance():
    result=search_quadrilaterals(modular_defaults(),[160.,180.,200.],[20.,30.,40.],
                                [140.,160.,180.,200.],math.radians(25),wheelbase=200.)
    assert result.ackermann_checked and result.wheelbase==200.
    assert result.candidates
    for c in result.candidates:
        dominates=lambda other:(other.ackermann_error<=c.ackermann_error and
                                other.evaluation.steering_limit>=c.evaluation.steering_limit and
                                other.min_point_motion>=c.min_point_motion and
                                (other.ackermann_error<c.ackermann_error or
                                 other.evaluation.steering_limit>c.evaluation.steering_limit or
                                 other.min_point_motion>c.min_point_motion))
        assert c.pareto==(not any(dominates(other) for other in result.candidates))
    with pytest.raises(ValueError,match='passo virtuale'):
        search_quadrilaterals(modular_defaults(),[180.],[30.],[180.],.4,wheelbase=0)



def test_point_motion_matches_physical_displacement_and_uses_both_directions():
    import numpy as np
    from steering.kinematics import steering_input
    from steering.quadrilateral_search import point_motion_curve
    p=steering_from_lengths(replace(modular_defaults(),actuation_fraction=.2),190.,30.,170.)
    curve=point_motion_curve(p,.4,11)
    assert len(curve['movement'])==21
    def point(mean):
        return select_pose(solve(p,steering_input(p,mean)),p.branch).point
    h=1e-6
    for index in (0,10,20):
        mean=curve['mean'][index]
        numerical=np.linalg.norm((point(mean+h)-point(mean-h))/(2*h))*math.pi/180
        assert curve['movement'][index]==pytest.approx(numerical,rel=1e-7)
    parallel=point_motion_curve(modular_defaults(),.4)
    assert np.all(parallel['movement']==30*math.pi/180)


def test_third_objective_changes_the_actual_pareto_front():
    result=search_quadrilaterals(modular_defaults(),[180.],[20.,30.],[180.],.4)
    assert result.motion_checked
    by_length={c.parameters.left.arm_length:c for c in result.candidates}
    assert by_length[20.].ackermann_error==by_length[30.].ackermann_error
    assert not by_length[20.].pareto and by_length[30.].pareto
    assert by_length[30.].min_point_motion==pytest.approx(30*math.pi/180)
