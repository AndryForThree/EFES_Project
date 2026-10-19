from dataclasses import replace
import math
import numpy as np
import pytest
from steering.geometry import arm_vector
from steering.parameters import Parameters, Bracket
from steering.kinematics import (BranchTracker, neutral_branch, neutral_tie_length,
                                 select_pose, solve, sweep, toggle_angles)


@pytest.mark.parametrize("angle", [-25, -15, 0, 15, 25])
def test_parallelogram(angle):
    p = Parameters()
    pose = select_pose(solve(p, math.radians(angle)), p.branch)
    assert pose is not None
    assert pose.theta_right == pytest.approx(pose.theta_left, abs=1e-12)
    assert pose.closure_error < p.length_tolerance
    assert neutral_branch(p) == -1
    if angle == 0:
        np.testing.assert_allclose(pose.b_left, [-90, 25], atol=1e-12)
        np.testing.assert_allclose(pose.b_right, [90, 25], atol=1e-12)


@pytest.mark.parametrize("length", [25, 40])
def test_rigid_bodies_and_point_arc(length):
    p = Parameters(left=Bracket(arm_length=length), right=Bracket(arm_length=length, axle_x=25))
    for sample in sweep(p, -.75, .75):
        s = sample.pose
        assert s is not None
        for bracket, a, b, c in ((p.left, s.a_left, s.b_left, s.c_left),
                                 (p.right, s.a_right, s.b_right, s.c_right)):
            assert np.linalg.norm(c-a) == pytest.approx(math.hypot(bracket.axle_x, bracket.axle_y))
            assert np.linalg.norm(b-a) == pytest.approx(bracket.arm_length)
            assert np.linalg.norm(c-b) == pytest.approx(np.linalg.norm(np.array([bracket.axle_x, bracket.axle_y])-arm_vector(bracket)))
        assert np.linalg.norm(s.b_right-s.b_left) == pytest.approx(p.tie_length)
        np.testing.assert_allclose(s.point, [-length*math.sin(s.theta_left), length*math.cos(s.theta_left)], atol=1e-10)


def test_invalid_and_degenerate():
    assert solve(replace(Parameters(), tie_length=10), 0).status == "impossible"
    assert solve(replace(Parameters(), left=Bracket(arm_length=0)), 0).status == "degenerate"
    p = Parameters(pivot_spacing=25, tie_length=25, left=Bracket(arm_angle=0), symmetric=False)
    assert solve(p, 0).status == "coincident"


def test_asymmetric_closure_and_all_solutions():
    p = Parameters(left=Bracket(arm_length=30, arm_angle=1.4),
                   right=Bracket(arm_length=40, arm_angle=1.7, axle_x=32, axle_y=8), symmetric=False)
    p = replace(p, tie_length=neutral_tie_length(p))
    assert min(abs(s.theta_right) for s in solve(p, 0).poses) < 1e-12
    for angle in np.linspace(-.5, .5, 81):
        result = solve(p, angle)
        assert len(result.poses) == 2
        assert {s.branch for s in result.poses} == {-1, 1}
        for s in result.poses:
            assert s.closure_error < p.length_tolerance


def test_continuity_in_both_directions_and_branches():
    for branch in (-1, 1):
        tracker = BranchTracker(replace(Parameters(), branch=branch))
        previous = None
        for angle in np.concatenate([np.linspace(-.7, .7, 200), np.linspace(.7, -.7, 200)]):
            pose = tracker.move(angle)
            assert not tracker.stop_reason
            assert pose.branch == branch
            if previous is not None:
                assert abs(pose.theta_right-previous.theta_right) < .1
            previous = pose


def test_tracker_does_not_skip_toggles_or_invalid_ranges():
    tracker = BranchTracker(Parameters())
    before = tracker.move(math.radians(80))
    after = tracker.move(math.radians(100))
    assert after is before
    assert tracker.stop_reason
    assert toggle_angles(Parameters(), -math.pi, math.pi) == pytest.approx([-math.pi/2, math.pi/2])
    assert tracker.move(math.radians(70)).theta_left == pytest.approx(math.radians(70))
    assert not tracker.stop_reason


def test_sweep_splits_at_exact_boundary():
    samples = sweep(Parameters(), math.radians(80), math.radians(100), count=10)
    assert any(s.status == "tangent" for s in samples)
    assert samples[0].segment != samples[-1].segment


@pytest.mark.parametrize("scale", [1e-5, 1, 1e6])
def test_scale_aware_solver(scale):
    p = Parameters(pivot_spacing=180*scale, tie_length=180*scale,
                   left=Bracket(arm_length=25*scale, axle_x=-25*scale),
                   right=Bracket(arm_length=25*scale, axle_x=25*scale))
    pose = select_pose(solve(p, .3), -1)
    assert pose.theta_right == pytest.approx(.3, abs=1e-12)
    assert pose.closure_error <= p.length_tolerance


def test_random_closure_cases():
    rng = np.random.default_rng(2026)
    found = 0
    for _ in range(100):
        p = Parameters(pivot_spacing=float(rng.uniform(80, 240)),
                       left=Bracket(arm_length=float(rng.uniform(10, 60)), arm_angle=float(rng.uniform(.8, 2.3))),
                       right=Bracket(arm_length=float(rng.uniform(10, 60)), arm_angle=float(rng.uniform(.8, 2.3)), axle_x=25),
                       symmetric=False)
        p = replace(p, tie_length=neutral_tie_length(p))
        for pose in solve(p, float(rng.uniform(-.6, .6))).poses:
            found += 1
            assert pose.closure_error <= 10*p.length_tolerance
            assert np.linalg.norm(pose.b_right-pose.a_right) == pytest.approx(p.right.arm_length, rel=1e-9)
    assert found > 100
