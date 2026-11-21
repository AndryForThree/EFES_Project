"""Compact always-visible project actions and state restoration."""
from datetime import datetime,timezone
import re
import hashlib
import unicodedata
import uuid
import streamlit as st
from steering.project import Project,MODEL_VERSION,SETTING_KEYS,dumps,loads
from steering.export import freecad_json
from steering.parameters import to_json
from steering.kinematics import select_pose,solve
from steering.singularities import diagnose


def remember_figures(section,caption,charts):
    st.session_state.setdefault('project_figures',{})[section]=dict(caption=caption,charts=charts)


def capture_project(state):
    settings={key:state[key] for key in SETTING_KEYS if key in state}
    run=state.get('motor_search_run')
    if run and f'motor_search_compare_{run}' in state:
        settings['motor_compare']=list(state[f'motor_search_compare_{run}'])
    results={key:state[key] for key in ('quadrilateral_search_result','motor_search_result','motor_results','technical_result','motor_axis_cache') if key in state}
    simulation=dict(state.get('simulation_state',{}))
    simulation.update(angle=state.get('snapshot_angle',0.),steering_angle=state.get('snapshot_steering',0.),
                      motor_angle=state.get('snapshot_motor',0.))
    return Project(state['configuration'],state.get('project_name','Progetto sterzo'),state.get('project_notes',''),
                   settings,simulation,results,dict(state.get('project_figures',{})),datetime.now(timezone.utc).isoformat())


def restore_project(state,project):
    # Runs before widgets are created; uploaded content never sets arbitrary state.
    for key in list(state):
        if (key in SETTING_KEYS or key in ('quadrilateral_search_result','motor_search_result','motor_results','technical_result','motor_axis_cache',
            'quad_run','quad_click','motor_search_run','motor_search_click','steering_motion','project_figures',
            '_project_name_edit','_project_notes_edit','motor_filter_x_range','motor_filter_y_range','_quad_compare_widget')
            or re.match(r'^p\d+_',key) or key.startswith(('motor_search_compare_','motor_pareto_'))):
            state.pop(key,None)
    state['configuration']=project.parameters
    state['revision']=state.get('revision',0)+1
    state['project_name']=project.name;state['project_notes']=project.notes
    state.update(project.settings)
    state['simulation_state']=project.simulation
    state['snapshot_angle']=project.simulation['angle']
    state['snapshot_steering']=project.simulation['steering_angle']
    state['snapshot_motor']=project.simulation['motor_angle']
    state['project_restoring']=True
    compatible=project.model_version==MODEL_VERSION
    if compatible:
        state.update(project.results)
        state['project_figures']=project.figures
        if 'technical_result' in state:
            result=state['technical_result']
            pose=select_pose(solve(project.parameters,result['angle']),project.parameters.branch)
            result.update(pose=pose,diagnostics=diagnose(project.parameters,pose) if pose else None)
        if 'quadrilateral_search_result' in state:state['quad_run']=uuid.uuid4().hex
        if 'motor_search_result' in state:
            run=uuid.uuid4().hex;state['motor_search_run']=run
            state[f'motor_search_compare_{run}']=project.settings.get('motor_compare',[])
    state['project_notice']=(f'Progetto «{project.name}» aperto.' if compatible else
        'Progetto aperto. Il modello di calcolo è diverso: configurazione e impostazioni ripristinate; '
        'i risultati salvati non vengono riutilizzati. Rilancia le analisi necessarie.')


def filename(name):
    name=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode()
    return re.sub(r'[^a-zA-Z0-9_-]+','_',name).strip('_') or 'progetto_sterzo'


@st.dialog('Apri progetto')
def open_dialog():
    uploaded=st.file_uploader('Progetto o configurazione JSON',type=['json'],key='open_project_upload')
    st.caption('Accetta anche i precedenti JSON di sola configurazione. Il progetto sostituisce la sessione corrente.')
    if uploaded is None:return
    try:
        content=uploaded.getvalue()
        digest=hashlib.sha256(content).hexdigest()
        cached=st.session_state.get('_project_upload_preview')
        if not cached or cached[0]!=digest:
            with st.spinner('Lettura del progetto…'):
                st.session_state._project_upload_preview=(digest,loads(content))
        project=st.session_state._project_upload_preview[1]
        st.write(f'**{project.name}** · {len(project.results)} gruppi di risultati salvati')
        if project.model_version!=MODEL_VERSION:
            st.warning('Versione del modello differente: saranno recuperate le impostazioni, ma le analisi andranno ricalcolate.')
        if st.button('Apri questo progetto',type='primary'):
            st.session_state.pending_project=project
            st.rerun()
    except ValueError as exc:
        st.error(str(exc))


@st.dialog('Salva progetto')
def save_dialog():
    name=st.text_input('Nome progetto',value=st.session_state.project_name,key='_project_name_edit',max_chars=120)
    notes=st.text_area('Note',value=st.session_state.project_notes,key='_project_notes_edit',max_chars=10000)
    st.session_state.project_name=name
    st.session_state.project_notes=notes
    st.caption('Salva anche ricerche, risultati, confronti e grafici disponibili. '
               'Per conservare la posa, metti prima in pausa l’animazione o rilascia lo slider.')
    if not st.session_state.project_name.strip():
        st.info('Inserisci un nome per il progetto.');return
    try:
        with st.spinner('Preparazione del progetto…'):
            project=capture_project(st.session_state)
            data=dumps(project)
        st.download_button('Scarica progetto',data,filename(project.name)+'.json','application/json',type='primary',on_click='ignore')
        with st.expander('Solo configurazione geometrica'):
            st.download_button('Scarica solo configurazione',to_json(project.parameters),filename(project.name)+'_config.json',
                               'application/json',on_click='ignore')
    except (ValueError,TypeError) as exc:
        st.error(f'Impossibile salvare: {exc}')
    with st.expander('Meccanismo FreeCAD'):
        st.caption('Esporta la configurazione attiva e le pose del settore motore continuo. Salva il file nella cartella '
                   'CAD/Telaio_Modulare come sterzo_cad.json, poi esegui Sterzo.FCMacro e Sterzo_Movimento.FCMacro.')
        try:
            st.download_button('Scarica meccanismo FreeCAD',freecad_json(st.session_state.configuration),
                               'sterzo_cad.json','application/json',on_click='ignore')
        except ValueError as exc:
            st.warning(str(exc))



@st.dialog('Esporta report',width='large')
def report_dialog():
    from .project_report import report_html
    project=capture_project(st.session_state)
    with st.spinner('Preparazione della relazione…'):
        report=report_html(project)
    st.download_button('Scarica report HTML',report,filename(project.name)+'_report.html','text/html',type='primary',on_click='ignore')
    st.caption('File autonomo, senza connessione internet. Aprilo nel browser: contiene il pulsante Stampa / Salva PDF. '
               'Include i grafici disponibili, senza avviare nuove ricerche.')


def render_project_toolbar():
    st.session_state.setdefault('project_name','Progetto sterzo')
    st.session_state.setdefault('project_notes','')
    st.markdown('''<style>.st-key-project_toolbar{position:sticky;top:3.5rem;z-index:50;background:white;
        border-bottom:1px solid #e4eaf0;padding:8px 0 12px;margin-bottom:16px}
        .st-key-project_toolbar h3{margin:0;padding:0}</style>''',unsafe_allow_html=True)
    with st.container(key='project_toolbar'):
        title,a,b,c=st.columns([2.6,1,1,1.5],vertical_alignment='center')
        title.markdown('### Steering Lab')
        title.caption(st.session_state.project_name)
        if a.button('Apri',use_container_width=True,key='project_open'):open_dialog()
        if b.button('Salva',type='primary',use_container_width=True,key='project_save'):save_dialog()
        if c.button('Esporta report',use_container_width=True,key='project_report'):report_dialog()
    if 'project_notice' in st.session_state:
        st.success(st.session_state.pop('project_notice'))
