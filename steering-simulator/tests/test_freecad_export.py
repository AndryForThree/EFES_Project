"""The CAD snapshot must retain the solver's geometry and public origin."""
from dataclasses import replace
import json
import math
import numpy as np
import pytest
from steering.export import freecad_json
from steering.parameters import modular_defaults


def test_freecad_snapshot_preserves_lengths_and_origin():
    p = modular_defaults()
    d = json.loads(freecad_json(p))
    points = d['points']
    assert d['coordinate_origin'] == 'A_SX'
    assert points['A_SX'] == [0, 0]
    assert points['A_DX'] == [p.pivot_spacing, 0]
    for a, b, length in [('A_SX', 'B_SX', p.left.arm_length),
                         ('A_DX', 'B_DX', p.right.arm_length),
                         ('B_SX', 'B_DX', p.tie_length),
                         ('M', 'Q', p.motor.crank_radius),
                         ('Q', 'T', p.motor.connecting_length)]:
        assert math.dist(points[a], points[b]) == pytest.approx(length)
    np.testing.assert_allclose(points['T'], np.array(points['B_SX']) + p.actuation_fraction * (
        np.array(points['B_DX'])-points['B_SX']))
    assert points['M'] == [p.motor.x+p.pivot_spacing/2, p.motor.y]


def test_freecad_uses_active_wheel_dimensions_without_snapping():
    p = modular_defaults()
    p = replace(p, physical=replace(p.physical, wheel_diameter=61.3, wheel_width=17.8))
    d = json.loads(freecad_json(p))
    assert d['wheel']['diameter'] == 61.3
    assert d['wheel']['width'] == 17.8
    assert d['units'] == {'length': 'mm', 'angle': 'rad'}


def test_freecad_rejects_motor_without_neutral_closure():
    p = modular_defaults()
    p = replace(p, motor=replace(p.motor, x=10000))
    with pytest.raises(ValueError, match='motore'):
        freecad_json(p)


def test_freecad_motion_contains_exact_closed_poses_and_neutral():
    from steering.motor import at_steering, build_range
    p = modular_defaults()
    d = json.loads(freecad_json(p))
    assert d['version'] == 2
    frames = d['motion']['frames']
    assert len(frames) == 201
    assert d['motion']['neutral_index'] == 100
    assert frames[100]['steering'] == 0
    assert frames[100]['points']['Q'] == d['points']['Q']
    interval = build_range(p)
    assert frames[0]['steering'] == interval.mean_lower
    assert frames[-1]['steering'] == interval.mean_upper
    assert all(a['steering'] < b['steering'] for a, b in zip(frames, frames[1:]))
    for frame in frames:
        state = at_steering(p, frame['steering'], frames[100]['phi'])
        np.testing.assert_allclose(frame['points']['Q'], state.pin+[p.pivot_spacing/2, 0], atol=1e-10)
        assert math.dist(frame['points']['Q'], frame['points']['T']) == pytest.approx(p.motor.connecting_length)
