"""Portable project JSON: explicit records only, never executable serialization."""
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import plotly.graph_objects as go
from .parameters import Parameters,to_json,from_json,validate_symmetric_setup
from .optimization import Evaluation
from .motor import MotorRange
from .motor_search import SearchSpace,SearchResult,MotorCandidate,Metrics,MAX_FEASIBLE_CANDIDATES
from .quadrilateral_search import GeometrySearch,GeometryCandidate
from .motor_filters import FILTER_KEYS
from .quadrilateral_filters import FILTER_KEYS as QUAD_FILTER_KEYS

FORMAT='steering-lab-project'
MAX_BYTES=256*1024*1024
_MODEL_FILES=('parameters.py','kinematics.py','motor.py','motor_search.py','interferences.py','quadrilateral_search.py','reference.py')
MODEL_VERSION=hashlib.sha256(b''.join(Path(__file__).with_name(f).read_bytes() for f in _MODEL_FILES)).hexdigest()[:16]
SETTING_KEYS={
 'quad_spacings','quad_lengths','quad_ties','quad_target','quad_wheelbase','quad_selected','quad_compare',
 'quad_show_dominated','quad_pareto_view','motor_search_mode','search_target','search_cranks','search_rods',
 'search_xmin_asx','search_xmax_asx','search_step','search_behind','search_rear_max','search_fixed_x_asx',
 'search_fixed_y','search_fixed_behind','motor_search_selected_id','motor_results_view',
 'motor_compare','search_attachment_mode','search_attachments',
}
SETTING_KEYS.update((*FILTER_KEYS,*QUAD_FILTER_KEYS))
SETTING_KEYS.update(('quad_results_view','motor_filter_axis_diameter'))
ENUMS={'search_attachment_mode':{'Fori più vicini al centro','Fori specifici'},'quad_pareto_view':{'3D','2D · proiezione'},'motor_search_mode':{'Zona rettangolare','Posizione fissa'},
       'motor_results_view':{'Movimento','Curve','Quote e CSV'},
       'quad_results_view':{'Movimento','Curve','Ackermann','Quote e CSV'}}
TEXT_KEYS={'quad_spacings','quad_lengths','quad_ties','search_cranks','search_rods','search_attachments'}
BOOL_KEYS={'quad_show_dominated','motor_filter_rear'}


@dataclass
class Project:
    parameters: Parameters
    name: str
    notes: str
    settings: dict
    simulation: dict
    results: dict
    figures: dict
    saved_at: str
    model_version: str=MODEL_VERSION


def _config(data):
    p=from_json(json.dumps(data,allow_nan=False))
    validate_symmetric_setup(p)
    return p


def _parameters(p):
    return json.loads(to_json(p))


def _json_default(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(f'Tipo non esportabile: {type(value).__name__}')


def _motor_dump(result):
    space=asdict(result.space)
    space['x_positions']=[x+result.base.pivot_spacing/2 for x in result.space.x_positions]
    return dict(base=_parameters(result.base),space=space,tested=result.tested,rejected=result.rejected,
                sample_count=result.sample_count,collision_checked=result.collision_checked,
                q_clearance_checked=result.q_clearance_checked,mounting_grid_checked=result.mounting_grid_checked,
                detailed_tested=result.detailed_tested,prefilter_rejected=result.prefilter_rejected,
                attachment_grid_checked=getattr(result,'attachment_grid_checked',False),
                rear_clearance_checked=getattr(result,'rear_clearance_checked',False),
                b_clearance_checked=getattr(result,'b_clearance_checked',False),
                feasible=[dict(id=c.id,configuration=_parameters(c.parameters),interval=asdict(c.interval),
                               metrics=asdict(c.metrics),pareto=c.pareto,rear_clearance=getattr(c,'rear_clearance',None)) for c in result.feasible])


def _motor_load(data):
    d=dict(data);base=_config(d.pop('base'));space=dict(d.pop('space'))
    for key in ('crank_lengths','rod_lengths','x_positions','y_positions'):
        space[key]=tuple(space[key])
    space['attachment_distances']=tuple(space.get('attachment_distances',()))
    space['x_positions']=tuple(x-base.pivot_spacing/2 for x in space['x_positions'])
    candidates=tuple(MotorCandidate(c['id'],_config(c['configuration']),MotorRange(**c['interval']),
                                    Metrics(**c['metrics']),c['pareto'],c.get('rear_clearance')) for c in d.pop('feasible'))
    _validate_candidates(candidates,MAX_FEASIBLE_CANDIDATES)
    if any(c.rear_clearance is not None and (type(c.rear_clearance) not in (float,int) or not math.isfinite(c.rear_clearance)) for c in candidates):
        raise ValueError('Distanza posteriore della leva non valida.')
    if d.get('rear_clearance_checked',False) and any(c.rear_clearance is None for c in candidates):
        raise ValueError('Distanza posteriore della leva mancante.')
    return SearchResult(base=base,space=SearchSpace(**space),feasible=candidates,**d)


def _quad_dump(result):
    d=asdict(result)
    d['candidates']=[dict(id=c.id,configuration=_parameters(c.parameters),evaluation=asdict(c.evaluation),
                          left_reference=c.left_reference,right_reference=c.right_reference,
                          ackermann_error=c.ackermann_error,neutral_track=c.neutral_track,
                          min_point_motion=c.min_point_motion,pareto=c.pareto) for c in result.candidates]
    return d


def _quad_load(data):
    d=dict(data);candidates=[]
    for record in d.pop('candidates'):
        c=dict(record);p=_config(c.pop('configuration'));evaluation=c.pop('evaluation')
        evaluation['reasons']=tuple(evaluation.get('reasons',()))
        candidates.append(GeometryCandidate(parameters=p,evaluation=Evaluation(**evaluation),**c))
    _validate_candidates(candidates,2000)
    return GeometrySearch(candidates=tuple(candidates),**d)


def _validate_candidates(candidates,limit):
    ids=[c.id for c in candidates]
    if len(ids)>limit or len(set(ids))!=len(ids) or any(type(i) is not int or i<1 for i in ids):
        raise ValueError('Elenco candidati non valido.')
    if any(type(c.pareto) is not bool for c in candidates) or (candidates and not any(c.pareto for c in candidates)):
        raise ValueError('Fronte Pareto non valido.')


def clean_settings(settings):
    if not isinstance(settings,dict):raise ValueError('Impostazioni progetto non valide.')
    result={}
    for key,value in settings.items():
        if key not in SETTING_KEYS:continue
        if key in ENUMS:
            if value not in ENUMS[key]:raise ValueError(f'Opzione non valida: {key}.')
        elif key in TEXT_KEYS:
            if not isinstance(value,str) or len(value)>5000:raise ValueError('Elenco dimensioni non valido.')
        elif key in BOOL_KEYS:
            if type(value) is not bool:raise ValueError('Opzione booleana non valida.')
        elif key in ('motor_filter_cranks','motor_filter_rods','motor_filter_assemblies',*QUAD_FILTER_KEYS):
            if (not isinstance(value,list) or len(value)>2000000 or
                any(type(v) not in (int,float) or not math.isfinite(v) or
                    (v not in (1,-1) if key=='motor_filter_assemblies' else v<=0) for v in value)):
                raise ValueError('Filtro componenti non valido.')
        elif key in ('quad_compare','motor_compare'):
            if not isinstance(value,list) or len(value)>2 or any(type(i) is not int or i<1 for i in value):
                raise ValueError('Confronto candidati non valido.')
        elif key in ('quad_selected','motor_search_selected_id'):
            if type(value) is not int or value<1:raise ValueError('Selezione candidato non valida.')
        else:
            if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Parametro numerico non valido.')
            if key in ('quad_target','search_target') and not 1<=value<=89.9:raise ValueError('Sterzata richiesta non valida.')
            if key=='quad_wheelbase' and value<.1:raise ValueError('Passo virtuale non valido.')
            if key=='motor_filter_axis_diameter' and not 0<=value<=300:raise ValueError('Diametro asse non valido.')
            if key=='search_step' and value<10:raise ValueError('Passo ricerca non valido.')
            if key in ('search_behind','search_rear_max','search_fixed_behind') and value<0:raise ValueError('Margine non valido.')
        result[key]=value
    return result


def clean_simulation(data):
    if not isinstance(data,dict):raise ValueError('Posa non valida.')
    result={'mode':data.get('mode') or 'steering','speed':data.get('speed') or 5}
    if result['mode'] not in ('motor','steering'):raise ValueError('Comando simulazione non valido.')
    if result['speed'] not in (1,2,5,10,20):raise ValueError('Velocità non valida.')
    for key in ('angle','steering_angle','motor_angle'):
        value=data.get(key,0.)
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
            raise ValueError('Angolo salvato non valido.')
        if value is not None and abs(value)>2*math.pi:raise ValueError('Angolo salvato fuori intervallo.')
        result[key]=value
    return result


def _axis_cache(data,result):
    if not isinstance(data,dict) or len(data)>MAX_FEASIBLE_CANDIDATES:
        raise ValueError('Verifiche asse non valide.')
    ids={c.id for c in result.feasible} if result is not None else set()
    cache={}
    for key,value in data.items():
        index=int(key)
        if index not in ids or type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError('Verifica asse senza candidato valido o con distanza non finita.')
        cache[index]=float(value)
    return cache


def dumps(project):
    results={}
    for key,value in project.results.items():
        if key=='quadrilateral_search_result':results[key]=_quad_dump(value)
        elif key=='motor_search_result':results[key]=_motor_dump(value)
        elif key=='motor_axis_cache':results[key]=_axis_cache(value,project.results.get('motor_search_result'))
        elif key in ('motor_results','technical_result'):
            results[key]={k:(json.loads(v.to_json()) if isinstance(v,go.Figure) else v)
                          for k,v in value.items() if k not in ('pose','diagnostics')}
    figures={}
    for section,record in project.figures.items():
        figures[section]={'caption':record['caption'],
                          'charts':{name:json.loads(fig.to_json()) for name,fig in record['charts'].items()}}
    raw=dict(format=FORMAT,schema_version=1,model_version=project.model_version,coordinate_origin='A_SX',
             saved_at=project.saved_at,metadata=dict(name=project.name,notes=project.notes),
             configuration=_parameters(project.parameters),settings=clean_settings(project.settings),
             simulation=clean_simulation(project.simulation),results=results,figures=figures)
    text=json.dumps(raw,ensure_ascii=False,allow_nan=False,default=_json_default)
    if len(text.encode())>MAX_BYTES:raise ValueError(f'Progetto troppo grande (massimo {MAX_BYTES//1024**2} MB).')
    return text


def _figure(spec):
    fig=go.Figure(spec)
    if any(trace.type not in ('scatter','scattergl','scatter3d') for trace in fig.data):
        raise ValueError('Tipo di grafico non supportato nel progetto.')
    return fig


def loads(text):
    try:
        if len(text.encode() if isinstance(text,str) else text)>MAX_BYTES:raise ValueError(f'Progetto troppo grande (massimo {MAX_BYTES//1024**2} MB).')
        def bad_constant(value):raise ValueError(f'Numero JSON non valido: {value}')
        def finite_float(value):
            number=float(value)
            if not math.isfinite(number):raise ValueError('Numero JSON fuori intervallo.')
            return number
        raw=json.loads(text,parse_constant=bad_constant,parse_float=finite_float)
        if raw.get('format')!=FORMAT:
            p=_config(raw)
            return Project(p,'Configurazione importata','',{},clean_simulation({}),{},{},datetime.now(timezone.utc).isoformat())
        if raw.get('schema_version')!=1 or raw.get('coordinate_origin')!='A_SX':
            raise ValueError('Formato progetto non supportato.')
        meta=raw['metadata'];name=meta['name'];notes=meta['notes']
        if not isinstance(name,str) or not 1<=len(name)<=120 or not isinstance(notes,str) or len(notes)>10000:
            raise ValueError('Nome o note del progetto non validi.')
        if raw['model_version']!=MODEL_VERSION:
            return Project(_config(raw['configuration']),name,notes,clean_settings(raw['settings']),
                           clean_simulation(raw['simulation']),{},{},raw['saved_at'],raw['model_version'])
        results={}
        for key,value in raw['results'].items():
            if key=='quadrilateral_search_result':results[key]=_quad_load(value)
            elif key=='motor_search_result':results[key]=_motor_load(value)
            elif key in ('motor_results','technical_result'):
                results[key]={k:(_figure(v) if k in ('figure','top_view') else v)
                              for k,v in value.items() if k in ('figure','top_view','angle','steering','rows')}
        if 'motor_axis_cache' in raw['results']:
            results['motor_axis_cache']=_axis_cache(raw['results']['motor_axis_cache'],results.get('motor_search_result'))
        figures={section:dict(caption=record['caption'],charts={name:_figure(spec) for name,spec in record['charts'].items()})
                 for section,record in raw['figures'].items()}
        return Project(_config(raw['configuration']),name,notes,clean_settings(raw['settings']),
                       clean_simulation(raw['simulation']),results,figures,raw['saved_at'],raw['model_version'])
    except (TypeError,KeyError,AttributeError,OverflowError,RecursionError,json.JSONDecodeError) as exc:
        raise ValueError(f'Progetto non valido: {exc}') from exc
