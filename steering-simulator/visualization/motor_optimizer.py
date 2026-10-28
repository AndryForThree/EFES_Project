"""Streamlit page for a bounded, discrete motor search and Pareto comparison."""
from __future__ import annotations
import csv
from dataclasses import replace
import hashlib
import io
import math
import uuid
from typing import Callable
import streamlit as st
from steering.kinematics import select_pose, solve
from steering.motor import response_csv
from steering.motor_search import SearchSpace, candidate_curve, grid_values, search, prefilter, MAX_DETAILED_SEARCH
from steering.parameters import Parameters, to_json
from .browser_motion import browser_motion
from .pareto import comparison_plot, pareto_plot
from .search_preview import search_preview


@st.cache_data(show_spinner=False, max_entries=32)
def _curve(candidate, target):
    return candidate_curve(candidate,target)


@st.cache_data(show_spinner=False, max_entries=8)
def _reachability(p, space):
    return prefilter(p, space)


def _numbers(value: str) -> tuple[float, ...]:
    try:
        numbers = tuple(dict.fromkeys(float(x.strip()) for x in value.split(',')))
    except ValueError as exc:
        raise ValueError('Inserisci le lunghezze disponibili separate da virgole, per esempio 10, 20, 30.') from exc
    if not numbers or any(not math.isfinite(x) or x <= 0 for x in numbers):
        raise ValueError('Le lunghezze disponibili devono essere finite e positive.')
    return numbers


def _table(candidates):
    return [{'ID':f'C{c.id}', 'Pareto':c.pareto, 'Leva · mm':c.parameters.motor.crank_radius,
             'Astina · mm':c.parameters.motor.connecting_length, 'M X · mm':c.parameters.motor.x,
             'M Y · mm':c.parameters.motor.y, 'Montaggio':'A' if c.parameters.motor.assembly==1 else 'B',
             'S max · °/°':c.metrics.max_sensitivity, 'S min · °/°':c.metrics.min_sensitivity,
             'Variazione · %':100*c.metrics.variation, 'Corsa albero richiesta · °':math.degrees(c.metrics.motor_excursion),
             'Margine di sterzata · °':math.degrees(c.metrics.steering_margin)} for c in candidates]


def _csv(rows):
    output = io.StringIO()
    if rows:
        writer=csv.DictWriter(output,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    return output.getvalue()


def render_motor_optimizer(p: Parameters, install: Callable[[Parameters], None]) -> None:
    st.subheader('Ottimizzazione motore')
    st.write('Mantieni questo sterzo e confronta collegamenti costruibili con le lunghezze che hai. '
             'La ricerca usa il centro del tirante (λ = 0,5) e prova entrambi i montaggi A/B.')
    st.caption('Obiettivi: ridurre la sensibilità massima e renderla uniforme nella stessa corsa richiesta. '
               'La configurazione manuale cambia soltanto con Carica nel simulatore.')
    st.caption(f'Filtro ingombri 2D attivo · braccetti {p.physical.link_width:g} mm · '
               f'ruote {p.physical.wheel_diameter:g} × {p.physical.wheel_width:g} mm. '
               'Misure nella scheda Ingombri 2D; tirante, corpo motore e ferramenta esclusi dagli ostacoli.')
    neutral = select_pose(solve(p,0),p.branch)
    y0 = float(neutral.b_left[1])
    st.caption(f'Tirante con ruote dritte: Y = {y0:.2f} mm. Il margine è misurato lungo +Y '
               'dall’asse M al tirante in posa zero, non dall’ingombro del corpo motore.')
    mode=st.radio('Posizione dell’asse motore', ['Zona rettangolare','Posizione fissa'],horizontal=True,key='motor_search_mode')
    a,b,c=st.columns(3)
    target=a.number_input('Sterzata media richiesta · ±°',min_value=1.,max_value=89.9,value=25.,step=1.,key='search_target')
    crank_text=b.text_input('Leve disponibili · mm','10, 20, 30',key='search_cranks',help='Interassi fra fori. Verranno usati soltanto i valori elencati.')
    rod_text=c.text_input('Astine disponibili · mm','40, 50, 60, 70, 80, 90, 100',key='search_rods')
    st.caption('Le lunghezze proposte sono a passi di 10 mm. Puoi sostituirle con l’elenco esatto dei tuoi componenti.')
    a,b,c=st.columns(3)
    if mode=='Zona rettangolare':
        xmin=a.number_input('X minimo asse · mm',value=-100.,step=10.,key='search_xmin')
        xmax=b.number_input('X massimo asse · mm',value=-20.,step=10.,key='search_xmax')
        step=c.number_input('Passo posizioni X/Y · mm',min_value=1.,value=20.,step=1.,key='search_step')
        a,b=st.columns(2)
        behind=a.number_input('Margine minimo dietro tirante neutro · mm',min_value=0.,value=10.,step=1.,key='search_behind')
        rear_max=b.number_input('Distanza massima dietro tirante neutro · mm',min_value=0.,value=50.,step=1.,key='search_rear_max')
    else:
        fixed_x=a.number_input('X asse fisso · mm',value=float(p.motor.x),step=1.,key='search_fixed_x')
        fixed_y=b.number_input('Y asse fisso · mm',value=max(float(p.motor.y),y0+10),step=1.,key='search_fixed_y')
        behind=c.number_input('Margine minimo dietro tirante neutro · mm',min_value=0.,value=10.,step=1.,key='search_fixed_behind')
    space=None
    can_search=False
    try:
        cranks,rods=_numbers(crank_text),_numbers(rod_text)
        if mode=='Zona rettangolare':
            xs=grid_values(xmin,xmax,step)
            ys=tuple(y0+distance for distance in grid_values(behind,rear_max,step))
            bounds=(xmin,xmax,y0+behind,y0+rear_max)
        else:
            if fixed_y<y0+behind-p.length_tolerance:
                raise ValueError('La posizione fissa non rispetta il margine minimo dietro al tirante neutro.')
            xs,ys=(fixed_x,),(fixed_y,)
            bounds=(fixed_x,fixed_x,fixed_y,fixed_y)
        total=len(xs)*len(ys)*len(cranks)*len(rods)*2
        space=SearchSpace(math.radians(target),cranks,rods,xs,ys,behind)
        st.markdown('**Anteprima dei parametri attuali**')
        a,b,c=st.columns(3)
        a.metric('Posizioni motore',len(xs)*len(ys))
        b.metric('Combinazioni per posizione',len(cranks)*len(rods)*2)
        c.metric('Combinazioni teoriche',total)
        st.caption(f'{len(xs)} posizioni X × {len(ys)} posizioni Y × {len(cranks)} leve × '
                   f'{len(rods)} astine × 2 montaggi A/B. Sterzata media richiesta: ±{target:g}°.')
        screening=_reachability(p,space)
        a,b,c=st.columns(3)
        a.metric('Scartate subito',screening.rejected_neutral+screening.rejected_margin)
        b.metric('Scartate sulla corsa',screening.rejected_travel)
        c.metric('Da analizzare',screening.remaining)
        st.caption('Il prefiltro verifica le distanze a ruote dritte e lungo la corsa richiesta, '
                   'per entrambi i montaggi A/B. Non verifica ancora sensibilità o interferenze. '
                   f'Il limite di {MAX_DETAILED_SEARCH} vale solo per i montaggi rimasti da analizzare.')
        if len(xs)*len(ys)<=10000:
            st.plotly_chart(search_preview(p,space,bounds),use_container_width=True,
                            key='motor_search_grid_preview',config={'displaylogo':False})
            st.caption('Ogni punto è una posizione dell’asse M della griglia originale, prima del prefiltro. '
                       'Il rettangolo mostra i limiti impostati: se il passo non divide esattamente il lato, '
                       'l’ultima fila resta prima del bordo. Le linee tratteggiate dello sterzo mostrano '
                       'gli estremi richiesti quando raggiungibili dalla geometria.')
        else:
            st.caption('La griglia contiene più di 10000 posizioni: l’anteprima dei punti è omessa. '
                       'La ricerca resta disponibile se il prefiltro lascia al massimo 10000 montaggi.')
        can_search=screening.remaining<=MAX_DETAILED_SEARCH
        if not can_search:
            st.warning(f'Dopo il prefiltro restano {screening.remaining} montaggi su {total} teorici: '
                       f'massimo {MAX_DETAILED_SEARCH} da analizzare. Riduci la zona o aumenta il passo.')
        elif not screening.remaining:
            st.info('Il prefiltro ha escluso tutte le combinazioni: modifica lunghezze o posizione del motore.')
    except ValueError as exc:
        st.error(str(exc))
        st.caption('Correggi i parametri per aggiornare l’anteprima.')
    run=st.button('Cerca configurazioni',type='primary',disabled=not can_search)
    if run and can_search:
        progress=None
        try:
            progress=st.progress(0,text='Preparazione della ricerca…')
            result=search(p,space,lambda n,total,phase:progress.progress(n/total,text=phase))
            st.session_state.motor_search_result=result
            st.session_state.motor_search_run=uuid.uuid4().hex
            st.session_state.pop('motor_search_selected_id',None)
            st.session_state.pop('motor_search_click',None)
        except ValueError as exc:
            st.error(str(exc))
            if "motor_search_result" in st.session_state:
                st.caption("La ricerca non è stata eseguita: i risultati sotto appartengono alla ricerca precedente.")
        finally:
            if progress is not None:progress.empty()
    result=st.session_state.get('motor_search_result')
    if result is None:
        st.info('Definisci i componenti disponibili e la zona, poi avvia la ricerca. Non parte automaticamente.')
        return
    st.markdown('**Risultati dell’ultima ricerca eseguita**')
    if space is None or space!=result.space:
        st.info('Hai modificato i parametri: l’anteprima sopra è aggiornata, i risultati sotto cambieranno con Cerca configurazioni.')
    if not getattr(result,'collision_checked',False) or result.base.physical!=p.physical:
        st.warning('Questi risultati non sono verificati con gli ingombri 2D attuali. Avvia una nuova ricerca per selezionare configurazioni senza interferenze rilevate.')
        return
    run_id=st.session_state.motor_search_run
    if replace(p,motor=result.base.motor,actuation_fraction=.5,display_range=result.base.display_range)!=result.base:
        st.warning('Questi risultati si riferiscono alla geometria dello sterzo salvata all’avvio della ricerca. '
                   'Avvia una nuova ricerca per usare le modifiche attuali; caricare un candidato ripristina la sua geometria completa.')
    columns=st.columns(3)
    columns[0].metric('Montaggi analizzati',getattr(result,'detailed_tested',result.tested))
    columns[1].metric('Soluzioni ammissibili',len(result.feasible))
    columns[2].metric('Soluzioni Pareto',sum(c.pareto for c in result.feasible))
    if getattr(result,'prefilter_rejected',None):
        st.caption(f'{result.tested} montaggi teorici · {sum(result.prefilter_rejected.values())} esclusi dal prefiltro rapido.')
    st.caption(f'Risultati per ±{math.degrees(result.space.target):.1f}° di sterzata media, '
               f'{result.sample_count} pose comuni a ogni candidato. '
               'Verificati chiusura, continuità, punti morti e interferenze 2D nelle pose campionate.')
    with st.expander('Motivi di esclusione'):
        st.dataframe([{'Motivo':reason,'Montaggi esclusi':count} for reason,count in result.rejected.items()],hide_index=True,use_container_width=True)
    if not result.feasible:
        st.warning('Nessuna soluzione nella zona e con i pezzi indicati. Prova ad ampliare la zona, aggiungere lunghezze o ridurre la sterzata richiesta.')
        return
    candidates={c.id:c for c in result.feasible if c.pareto}
    if st.session_state.get('motor_search_selected_id') not in candidates:
        st.session_state.motor_search_selected_id=next(iter(candidates))
    selected_id=st.session_state.motor_search_selected_id
    a,b=st.columns([2,1])
    color=a.selectbox('Colore dei punti',['Corsa albero richiesta','Margine di sterzata oltre la richiesta'],key='motor_pareto_color')
    include=b.checkbox('Mostra anche soluzioni dominate',True,key='motor_pareto_dominated')
    figure=pareto_plot(list(result.feasible),selected_id,'motor_excursion' if color=='Corsa albero richiesta' else 'steering_margin',include)
    selection=st.plotly_chart(figure,use_container_width=True,key=f'motor_pareto_{run_id}',
                              on_select='rerun',selection_mode='points',config={'displaylogo':False})
    points=selection.selection.points
    if points:
        custom=points[-1].get('customdata')
        clicked=int(custom[0]) if custom else None
        token=(run_id,clicked)
        if clicked in candidates and token!=st.session_state.get('motor_search_click'):
            st.session_state.motor_search_click=token
            st.session_state.motor_search_selected_id=clicked
            st.rerun()
    st.caption('Puoi selezionare e confrontare solo le soluzioni Pareto, dal menu o cliccando sui rombi. In basso a sinistra è meglio; '
               'i rombi Pareto sono i compromessi non dominati. '
               'Variazione = (S massima − S minima) / S media, usando |dm/dφ|.')
    selected_id=st.selectbox('Configurazione selezionata',list(candidates),key='motor_search_selected_id',
                              format_func=lambda i:f'C{i} · leva {candidates[i].parameters.motor.crank_radius:g} / astina {candidates[i].parameters.motor.connecting_length:g} mm')
    selected=candidates[selected_id]
    motor=selected.parameters.motor
    st.write(f'**C{selected.id}** · M = ({motor.x:g}, {motor.y:g}) mm · leva **{motor.crank_radius:g} mm** · '
             f'astina **{motor.connecting_length:g} mm** · montaggio **{"A" if motor.assembly==1 else "B"}** · attacco centrale')
    a,b,c=st.columns(3)
    a.metric('Sensibilità massima · °/°',f'{selected.metrics.max_sensitivity:.4f}')
    b.metric('Variazione della sensibilità',f'{100*selected.metrics.variation:.1f}%')
    c.metric('Corsa albero richiesta',f'{math.degrees(selected.metrics.motor_excursion):.1f}°')
    if st.button('Carica nel simulatore',type='primary',key='apply_motor_search'):
        install(selected.parameters)
        st.rerun()
    compare_key=f'motor_search_compare_{run_id}'
    if compare_key in st.session_state:
        previous=st.session_state[compare_key]
        valid=[i for i in previous if i in candidates]
        if valid!=previous:
            st.session_state[compare_key]=valid
    other_ids=st.multiselect('Confronta con altre configurazioni · massimo 2',list(candidates),max_selections=2,
                               format_func=lambda i:f'C{i}',key=compare_key)
    ids=list(dict.fromkeys([selected_id,*other_ids]))
    absolute=st.checkbox('Mostra la sensibilità in valore assoluto',True,key='motor_search_absolute')
    curves=[(i,_curve(candidates[i],result.space.target)) for i in ids]
    st.plotly_chart(comparison_plot(curves,absolute),use_container_width=True,key='motor_search_curves',config={'displaylogo':False})
    st.caption('Le curve coprono tutte la stessa sterzata richiesta. Un segno negativo nel rapporto indica il verso del montaggio, '
               'non un difetto: i due obiettivi confrontano il valore assoluto.')
    with st.expander('Anteprima animata della configurazione selezionata',expanded=True):
        target=result.space.target
        preview_parameters=replace(selected.parameters,display_range=target)
        preview_interval=replace(selected.interval,mean_lower=-target,mean_upper=target,
                                 phi_at_lower=math.radians(curves[0][1][0]['motor_deg']),
                                 phi_at_upper=math.radians(curves[0][1][-1]['motor_deg']))
        candidate_signature=hashlib.sha256(('candidate:'+to_json(preview_parameters)).encode()).hexdigest()
        st.caption('Anteprima limitata alla corsa richiesta, verificata per le interferenze 2D. '
                   'Il margine cinematico oltre questa corsa non è una verifica degli ingombri.')
        browser_motion(preview_parameters,candidate_signature,preview_interval,key='motor_search_preview')
    a,b=st.columns(2)
    a.download_button('↓ Risultati ricerca CSV',_csv(_table(result.feasible)),'motor-search-results.csv','text/csv',use_container_width=True)
    b.download_button('↓ Curva selezionata CSV',response_csv(curves[0][1]),f'motor-candidate-{selected_id}.csv','text/csv',use_container_width=True)
    with st.expander('Tabella delle configurazioni ammissibili'):
        st.dataframe(_table(result.feasible),hide_index=True,use_container_width=True)
