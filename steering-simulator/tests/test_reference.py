"""The same A SX datum for plots, controls and saved/legacy projects."""
from dataclasses import asdict,replace
import csv
import io
import json
import pytest
from steering.parameters import Parameters,Motor,steering_from_lengths,to_json,from_json
from steering.reference import chassis_point,chassis_pose
from steering.kinematics import select_pose,solve,sweep
from steering.export import onshape_variables,sweep_csv
from visualization.top_view import top_view


def test_json_new_origin_and_legacy_preserve_the_same_mechanism():
    p=steering_from_lengths(Parameters(),190.,30.,170.)
    p=replace(p,motor=Motor(75.,40.,20.,60.))
    raw=json.loads(to_json(p))
    assert raw['coordinate_origin']=='A_SX'
    assert raw['parameters']['motor']['x']==170.
    assert from_json(json.dumps(raw))==p
    old=dict(schema_version=7,units=dict(length='mm',angle='rad'),parameters=asdict(p))
    assert from_json(json.dumps(old))==p
    raw['coordinate_origin']='unknown'
    with pytest.raises(ValueError,match='Origine'):
        from_json(json.dumps(raw))


def test_plot_and_exports_share_a_left_zero():
    p=steering_from_lengths(Parameters(),190.,30.,170.)
    pose=select_pose(solve(p,0),p.branch)
    converted=chassis_pose(p,pose)
    assert converted.a_left[0]==0 and converted.a_right[0]==190
    assert pose.a_left[0]==-95  # solver data not mutated by rendering
    fig=top_view(p,pose,[])
    pivots=next(t for t in fig.data if t.text is not None and 'A SX · O (0,0)' in t.text)
    assert list(pivots.x)==[0,190]
    samples=sweep(p,0,.1,3)
    rows=list(csv.DictReader(io.StringIO(sweep_csv(p,samples))))
    assert float(rows[0]['Tx_mm'])==pytest.approx(chassis_point(p,pose.point)[0])
    assert 'Motore_X = 35 mm' in onshape_variables(p)  # -60 + 95
    assert 'A SX = (0, 0)' in onshape_variables(p)
