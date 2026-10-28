from dataclasses import replace
import json
import math
import pytest
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


def test_capacity_is_an_output_independent_of_slider_and_wheel_sizes():
    p = Parameters()
    result = evaluate(p)
    assert result.geometrically_valid
    assert result.steering_limit == pytest.approx(math.pi/2)
    assert result.at_deadpoint
    changed = replace(p, display_range=math.radians(10), physical=replace(p.physical, wheel_width=300))
    assert evaluate(changed) == result


def test_exploration_ranks_by_range_and_preserves_original():
    p = Parameters()
    original = to_json(p)
    results = explore(p, [25], [0.0, math.radians(30)], [180])
    assert len(results) == 2
    assert results[0].evaluation.steering_limit >= results[1].evaluation.steering_limit
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
    for removed in ('Spessore', 'Diametro_foro', 'Diametro_perno', 'Rondella', 'Quota_', 'L_taglio'):
        assert removed not in text
    assert 'targets' not in json.loads(to_json(p))['parameters']
    assert set(json.loads(to_json(p))['parameters']['physical']) == {'wheel_width', 'wheel_diameter', 'link_width'}
