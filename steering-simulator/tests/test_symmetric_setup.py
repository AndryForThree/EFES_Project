"""The simplified controls must keep both wheels straight at neutral."""
from dataclasses import replace
import math
import pytest
from steering.kinematics import solve, select_pose
from steering.parameters import Parameters, symmetric_steering, validate_symmetric_setup


@pytest.mark.parametrize('length,inclination', [(25, 0), (25, 30), (25, -30), (40, 20)])
def test_controls_produce_straight_wheels_and_close_the_tie(length, inclination):
    p = symmetric_steering(Parameters(), length, 180, math.radians(inclination))
    validate_symmetric_setup(p)
    pose = select_pose(solve(p, 0), p.branch)
    assert pose is not None
    assert pose.heading_left == pytest.approx(0, abs=1e-12)
    assert pose.heading_right == pytest.approx(0, abs=1e-12)
    assert pose.b_left[0] == pytest.approx(-90)
    assert pose.b_right[0] == pytest.approx(90)
    assert pose.b_left[1] == pytest.approx(pose.b_right[1])
    assert pose.closure_error < p.length_tolerance
    assert p.right.axle_x == -p.left.axle_x
    if inclination > 0:
        assert p.pivot_spacing < p.tie_length
    elif inclination < 0:
        assert p.pivot_spacing > p.tie_length


def test_incompatible_dimensions_are_rejected():
    with pytest.raises(ValueError, match='interasse'):
        symmetric_steering(Parameters(), 100, 20, math.radians(30))
    with pytest.raises(ValueError, match='90'):
        symmetric_steering(Parameters(), 25, 180, math.pi/2)
    with pytest.raises(ValueError, match='ruote dritte'):
        validate_symmetric_setup(replace(Parameters(), tie_length=185))
