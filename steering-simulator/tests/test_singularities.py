from dataclasses import replace
import math
import numpy as np
import pytest
from steering.parameters import Parameters, Bracket
from steering.kinematics import solve, select_pose, neutral_tie_length
from steering.singularities import diagnose


@pytest.mark.parametrize("angle", [-math.pi/2, math.pi/2])
def test_tangency_no_division_by_zero(angle):
    p = Parameters()
    result = solve(p, angle)
    assert result.status == "tangent"
    d = diagnose(p, result.poses[0])
    assert d.ratio is None
    assert d.point_velocity is None
    assert d.near_input_deadpoint and d.near_output_deadpoint
    assert d.toggle_distance == pytest.approx(0, abs=1e-12)


def test_ratio_and_analytic_velocity():
    p = Parameters()
    for theta in np.linspace(-.7, .7, 20):
        pose = select_pose(solve(p, theta), -1)
        d = diagnose(p, pose)
        assert d.ratio == pytest.approx(1)
        np.testing.assert_allclose(d.point_velocity, [-25*math.cos(theta), -25*math.sin(theta)], atol=1e-10)
        assert d.toggle_distance == pytest.approx(math.pi/2-abs(theta))


def test_asymmetric_derivatives_against_finite_difference():
    p = Parameters(left=Bracket(arm_length=30, arm_angle=1.4),
                   right=Bracket(arm_length=40, arm_angle=1.7, axle_x=25), symmetric=False)
    p = replace(p, tie_length=neutral_tie_length(p), actuation_fraction=.3)
    for theta in np.linspace(-.4, .4, 11):
        d = diagnose(p, select_pose(solve(p, theta), -1))
        step = 1e-6
        before = select_pose(solve(p, theta-step), -1)
        after = select_pose(solve(p, theta+step), -1)
        assert d.ratio == pytest.approx((after.theta_right-before.theta_right)/(2*step), rel=1e-6)
        np.testing.assert_allclose(d.point_velocity, (after.point-before.point)/(2*step), atol=1e-6)


def test_engineering_warning_does_not_report_large_finite_ratio():
    p = Parameters()
    d = diagnose(p, select_pose(solve(p, math.radians(89)), -1))
    assert d.near_output_deadpoint
    assert d.ratio is None


def test_heading_offsets_not_confused_with_bracket_angles():
    p = Parameters(left=Bracket(heading_offset=.1), right=Bracket(axle_x=25, heading_offset=-.2), symmetric=False)
    pose = select_pose(solve(p, .3), -1)
    assert pose.heading_left == pytest.approx(.4)
    assert pose.heading_right == pytest.approx(.1)
    assert diagnose(p, pose).mismatch == pytest.approx(-.3)
