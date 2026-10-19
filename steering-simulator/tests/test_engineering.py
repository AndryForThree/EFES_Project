from dataclasses import replace
import json
import math
import numpy as np
import pytest
from steering.clearances import check_clearances, manufacturing_issues, polygon_distance
from steering.geometry import rectangle
from steering.export import onshape_variables, sweep_csv
from steering.kinematics import select_pose, solve, sweep
from steering.optimization import evaluate, explore
from steering.parameters import Parameters, from_json, to_json


def test_configuration_roundtrip():
    p = Parameters()
    assert from_json(to_json(p)) == p


@pytest.mark.parametrize("change", [
    lambda d: d.update(tie_length=-1), lambda d: d.update(pivot_spacing=float('nan')),
    lambda d: d.update(branch=2), lambda d: d.update(branch=True),
    lambda d: d.update(actuation_fraction=2), lambda d: d.update(unrecognized=12),
    lambda d: d['left'].update(arm_length=30),
])
def test_bad_json_rejected(change):
    raw = json.loads(to_json(Parameters()))
    change(raw['parameters'])
    with pytest.raises(ValueError):
        from_json(json.dumps(raw))


def test_invalid_units_rejected():
    raw = json.loads(to_json(Parameters()))
    raw['units']['angle'] = 'deg'
    with pytest.raises(ValueError):
        from_json(json.dumps(raw))


def test_polygon_clearance():
    a = rectangle(np.zeros(2), 2, 2)
    assert polygon_distance(a, rectangle(np.array([3, 0]), 2, 2)) == pytest.approx(1)
    assert polygon_distance(a, rectangle(np.array([.5, 0]), 2, 2)) == 0


def test_height_separation_between_moving_components():
    p = Parameters()
    p = replace(p, physical=replace(p.physical, wheel_width=80))
    pose = select_pose(solve(p, 0), -1)
    hits = check_clearances(p, pose)
    assert any(c.status == 'risk' and {c.first, c.second} == {'Braccio SX', 'Ruota SX'} for c in hits)
    raised = replace(p, physical=replace(p.physical, wheel_axle_z=100))
    assert all(c.status == 'separated' for c in check_clearances(raised, pose) if 'Ruota' in c.first+c.second)
    projected = replace(p, physical=replace(p.physical, use_heights=False))
    assert all(c.status == 'projected' for c in check_clearances(projected, pose))


def test_interfering_design_not_falsely_approved():
    p = Parameters()
    p = replace(p, physical=replace(p.physical, wheel_width=80))
    assert not manufacturing_issues(p)
    result = evaluate(p, count=9)
    assert result.geometrically_valid and result.well_conditioned
    assert result.targets_met
    assert not result.clearance_ok
    assert not result.suitable
    assert result.reasons


def test_exploration_uses_clearance_and_preserves_original():
    p = Parameters()
    p = replace(p, physical=replace(p.physical, wheel_width=80))
    original = to_json(p)
    results = explore(p, [25, 40], [math.pi/2], [180], count=5)
    assert len(results) == 2
    assert all(not c.evaluation.suitable for c in results)
    assert to_json(p) == original


def test_exports():
    p = Parameters()
    text = onshape_variables(p)
    assert 'Interasse_sterzo = 180 mm' in text
    assert '#Offset_ruota_X_SX' in text
    assert 'Angolo_braccio_SX = 90 deg' in text
    data = sweep_csv(p, sweep(p, -.1, .1, 3))
    assert len(data.splitlines()) == 4
    assert 'mm_per_rad' in data
