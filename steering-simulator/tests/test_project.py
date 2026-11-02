"""Save/open real search results and produce an offline, safe report."""
from datetime import datetime,timezone
import json
import math
import plotly.graph_objects as go
import pytest
from steering.parameters import modular_defaults,to_json,steering_from_lengths
from steering.project import Project,MODEL_VERSION,dumps,loads
from steering.quadrilateral_search import search_quadrilaterals
from steering.motor_search import SearchSpace,search
from visualization.project_controls import restore_project,capture_project
from visualization.project_report import report_html


def sample_project():
    p=steering_from_lengths(modular_defaults(),180.,30.,170.)
    quad=search_quadrilaterals(p,[180.,190.],[30.],[170.,180.],.3)
    motor=search(p,SearchSpace(target=.3,crank_lengths=(10.,20.),rod_lengths=(60.,80.),
                               x_positions=(-80.,-60.),y_positions=(40.,60.),attachment_distances=(80.,90.)))
    assert quad.candidates and motor.feasible
    q=next(c.id for c in quad.candidates if c.pareto)
    m=next(c.id for c in motor.feasible if c.pareto)
    fig=go.Figure(go.Scatter(x=[0,1],y=[0,2]))
    return Project(p,'Prova prof','Note <script>alert("x")</script>',
                   dict(quad_target=math.degrees(.3),quad_wheelbase=200.,quad_selected=q,
                        quad_filter_spacings=[180.],quad_filter_lengths=[30.],quad_filter_ties=[170.,180.],
                        quad_results_view='Movimento',
                        motor_search_selected_id=m,motor_compare=[],
                        search_attachment_mode='Fori specifici',search_attachments='80, 90'),
                   dict(mode='steering',speed=5,angle=.1,steering_angle=.1,motor_angle=0.),
                   dict(quadrilateral_search_result=quad,motor_search_result=motor),
                   {'quad':dict(caption='Confronto salvato',charts={'Curva':fig})},
                   datetime.now(timezone.utc).isoformat())


def test_project_roundtrip_restores_results_and_selection_without_search(monkeypatch):
    project=sample_project()
    payload=dumps(project)
    recovered=loads(payload)
    assert recovered.parameters==project.parameters
    assert recovered.results==project.results
    assert recovered.settings==project.settings
    raw=json.loads(payload)
    assert raw['results']['motor_search_result']['space']['x_positions']==[10.,30.]
    assert raw['results']['motor_search_result']['space']['attachment_distances']==[80.,90.]
    assert {round(c.parameters.actuation_fraction*170) for c in recovered.results['motor_search_result'].feasible}=={80,90}
    state={'configuration':project.parameters,'revision':0,'search_rods':'old'}
    restore_project(state,recovered)
    assert state['snapshot_steering']==.1
    assert state['quad_selected']==project.settings['quad_selected']
    assert state['quadrilateral_search_result']==project.results['quadrilateral_search_result']
    assert loads(dumps(capture_project(state))).results==project.results
    # An incompatible computation model keeps dimensions/settings, discards caches.
    raw['model_version']='different-model'
    old=loads(json.dumps(raw))
    assert old.parameters==project.parameters and not old.results and not old.figures
    assert loads(to_json(project.parameters)).parameters==project.parameters
    raw['configuration']['parameters']['tie_length']=-1
    with pytest.raises(ValueError):loads(json.dumps(raw))


def test_report_is_self_contained_printable_and_escapes_notes():
    project=sample_project()
    html=report_html(project)
    assert '<svg' in html and 'A SX' in html and 'Stampa / Salva PDF' in html
    assert 'plotly.js' in html and 'Confronto salvato' in html
    assert '<script>alert("x")</script>' not in html
    assert '&lt;script&gt;' in html
    assert 'cdn.plot.ly' not in html.split('<script>')[0]
    assert 'Plotly.toImage' in html
