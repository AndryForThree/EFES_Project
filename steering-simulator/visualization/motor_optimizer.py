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
from steering.motor import response_csv,at_steering
from steering.motor_search import SearchSpace, candidate_curve, chassis_grid_values, search, prefilter, central_attachment_holes, MAX_FEASIBLE_CANDIDATES
from steering.parameters import Parameters, to_json
from steering.motor_filters import FILTER_KEYS,filters_from_settings,filter_candidates
from steering.motor_axis import axis_pareto,candidate_axis_clearance
from .browser_motion import browser_motion
from .project_controls import remember_figures
from .pareto import comparison_plot, pareto_plot
from .search_preview import search_preview
from .mounting import mounting_plot, mounting_rows

FILTER_UI_KEYS=('motor_filter_x_range','motor_filter_y_range','motor_filter_axis_diameter')


def _curve(candidate, target):
    # Pareto membership and a cached clearance do not change the response curve.
    return _cached_curve(replace(candidate,pareto=False,rear_clearance=None),target)


@st.cache_data(show_spinner=False, max_entries=32)
def _cached_curve(candidate, target):
    return candidate_curve(candidate,target)


@st.cache_data(show_spinner=False, max_entries=8)
def _reachability(p, space):
    return prefilter(p, space)


@st.cache_data(show_spinner=False,max_entries=8)
def _grid_preview(p,space,bounds):
    return search_preview(p,space,bounds)


def _numbers(value: str, allow_zero: bool = False) -> tuple[float, ...]:
    try:
        numbers = tuple(dict.fromkeys(float(x.strip()) for x in value.split(',')))
    except ValueError as exc:
        raise ValueError('Inserisci le lunghezze disponibili separate da virgole, per esempio 10, 20, 30.') from exc
    if not numbers or any(not math.isfinite(x) or (x < 0 if allow_zero else x <= 0) for x in numbers):
        raise ValueError('Inserisci valori finiti e non negativi.' if allow_zero else 'Le lunghezze disponibili devono essere finite e positive.')
    return numbers


def _table(candidates,axis_cache=None,axis_diameter=0.):
    if not candidates:return []
    base=candidates[0].parameters
    pose=select_pose(solve(base,0.),base.branch)
    rows=[]
    for c in candidates:
        point=pose.b_left+c.parameters.actuation_fraction*(pose.b_right-pose.b_left)
        rows.append({'ID':f'C{c.id}', 'Pareto':c.pareto, 'Leva · mm':c.parameters.motor.crank_radius,
             'Astina · mm':c.parameters.motor.connecting_length, 'M X · mm':c.parameters.motor.x+c.parameters.pivot_spacing/2,
             'M Y · mm':c.parameters.motor.y,
             'Foro T da B SX · mm':c.parameters.actuation_fraction*c.parameters.tie_length,
             'Foro T da B DX · mm':(1-c.parameters.actuation_fraction)*c.parameters.tie_length,
             'T zero X · mm':float(point[0]+base.pivot_spacing/2),
             'T zero Y · mm':float(point[1]), 'Montaggio':'A' if c.parameters.motor.assembly==1 else 'B',
             'Distanza minima leva dietro tirante · mm':getattr(c,'rear_clearance',None),
             'S max · °/°':c.metrics.max_sensitivity, 'S min · °/°':c.metrics.min_sensitivity,
             'Variazione · %':100*c.metrics.variation, 'Corsa albero richiesta · °':math.degrees(c.metrics.motor_excursion),
             'Margine di sterzata · °':math.degrees(c.metrics.steering_margin)})
    if axis_diameter>0:
        for row,candidate in zip(rows,candidates):
            row['Diametro ingombro asse · mm']=axis_diameter
            value=(axis_cache or {}).get(candidate.id)
            row['Spazio minimo asse · mm']=value-axis_diameter/2 if value is not None else None
    return rows


def _csv(rows):
    output = io.StringIO()
    if rows:
        writer=csv.DictWriter(output,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    return output.getvalue()


@st.cache_data(show_spinner=False,max_entries=16)
def _preview_interval(candidate,target):
    p=candidate.parameters;interval=candidate.interval
    lower=at_steering(p,-target,interval.neutral_phi)
    upper=at_steering(p,target,interval.neutral_phi)
    if lower is None or upper is None:
        raise ValueError('Impossibile ricostruire la corsa della soluzione selezionata.')
    return replace(interval,mean_lower=-target,mean_upper=target,
                   phi_at_lower=lower.phi-interval.neutral_phi,phi_at_upper=upper.phi-interval.neutral_phi)


def _render_result_filters(result):
    with st.expander('Filtra e confronta i risultati',expanded=True):
        st.caption('Filtri applicati alle soluzioni conservate: nessuna nuova ricerca. Il Pareto viene ricalcolato sul sottoinsieme rimasto.')
        if st.button('Azzera filtri',key='motor_filters_reset'):
            for key in (*FILTER_KEYS,*FILTER_UI_KEYS):st.session_state.pop(key,None)
            st.session_state.motor_filter_rear=False
            st.session_state.motor_filter_axis_diameter=0.
        a,b,c=st.columns(3)
        for column,label,options,key in (
            (a,'Leve incluse · mm',sorted(set(result.space.crank_lengths)),'motor_filter_cranks'),
            (b,'Astine incluse · mm',sorted(set(result.space.rod_lengths)),'motor_filter_rods'),
            (c,'Montaggi inclusi',[1,-1],'motor_filter_assemblies')):
            if key in st.session_state:
                st.session_state[key]=[v for v in st.session_state[key] if v in options]
            column.multiselect(label,options,default=options,key=key,
                               format_func=(lambda v:'A' if v==1 else 'B') if key=='motor_filter_assemblies' else (lambda v:f'{v:g}'))
        a,b=st.columns(2)
        for column,axis,values in ((a,'x',[c.parameters.motor.x+c.parameters.pivot_spacing/2 for c in result.feasible]),
                                   (b,'y',[c.parameters.motor.y for c in result.feasible])):
            low=f'motor_filter_{axis}min';high=f'motor_filter_{axis}max'
            selected=(float(st.session_state.get(low,min(values))),float(st.session_state.get(high,max(values))))
            if selected[0]>selected[1]:
                st.error('Zona filtro non valida: usa Azzera filtri per ripristinare i limiti.');return None
            minimum=min(min(values),*selected);maximum=max(max(values),*selected)
            if minimum<maximum:
                selected=column.slider(f'Zona motore {axis.upper()} · mm da A SX',float(minimum),float(maximum),
                                       value=selected,step=10.,key=f'motor_filter_{axis}_range')
            else:
                column.caption(f'Motore {axis.upper()} = {minimum:g} mm da A SX · posizione unica')
            st.session_state[low],st.session_state[high]=selected
        ready=getattr(result,'rear_clearance_checked',False)
        st.checkbox('Leva M–Q sempre dietro al tirante mobile',value=ready,key='motor_filter_rear',disabled=not ready,
                    help='Tutto il rettangolo della leva deve restare dietro al bordo posteriore del tirante in ogni posa campionata. Il contatto esclude la soluzione.')
        if not ready:
            st.info('Per usare il nuovo vincolo, rilancia una volta la ricerca. Poi puoi attivarlo e disattivarlo senza ripetere i calcoli.')
        diameter=st.slider('Diametro ingombro asse M · mm',0.,300.,value=30.,step=1.,key='motor_filter_axis_diameter',
                           help='Disco fisso centrato su M. 30 mm è il diametro, non il raggio; 0 disattiva il vincolo. La leva M–Q collegata all’asse è esclusa.')
        st.caption('Asse M: controlli sui fronti Pareto, memorizzati per configurazione. '
                   'Le geometrie dominate restano disponibili per le selezioni successive.')
        st.caption('Coordinate motore da A SX. Il controllo leva segue posizione e inclinazione attuali del tirante '
                   f'nelle {result.sample_count} pose della corsa richiesta e considera la larghezza dei braccetti.')
    try:
        fixed=filter_candidates(result,filters_from_settings(st.session_state))
        cache=st.session_state.setdefault('motor_axis_cache',{})
        status=None;new_checks=0
        def evaluate_axis(candidate):
            nonlocal status,new_checks
            if status is None:status=st.status('Verifica ingombro asse sui fronti Pareto…',expanded=False)
            value=candidate_axis_clearance(candidate,result.space.target,result.sample_count)
            new_checks+=1
            if new_checks%5==0:status.update(label=f'Ingombro asse · {new_checks} configurazioni verificate…')
            return value
        try:
            filtered=axis_pareto(fixed,diameter,cache,evaluate_axis)
        except Exception:
            if status is not None:status.update(label='Verifica ingombro asse interrotta',state='error')
            raise
        else:
            if status is not None:status.update(label=f'Ingombro asse · {new_checks} nuove verifiche',state='complete')
        if diameter>0:
            checked=sum(c.id in cache for c in fixed)
            st.caption(f'{len(fixed)} candidati rispettano i filtri fissi · {checked} con verifica asse memorizzata · '
                       f'{len(filtered)} sul Pareto verificato. Non tutte le geometrie dominate vengono controllate.')
    except ValueError as exc:
        st.error(str(exc));return None
    a,b,c=st.columns(3)
    a.metric('Soluzioni Pareto disponibili',sum(c.pareto for c in filtered),
             f'{sum(c.pareto for c in filtered)-sum(c.pareto for c in result.feasible)} rispetto al fronte originale',delta_color='off')
    if filtered:
        original_s=min(c.metrics.max_sensitivity for c in result.feasible)
        original_v=min(c.metrics.variation for c in result.feasible)
        best_s=min(c.metrics.max_sensitivity for c in filtered)
        best_v=min(c.metrics.variation for c in filtered)
        b.metric('Migliore S massima · °/°',f'{best_s:.4f}',f'{best_s-original_s:+.4f}',delta_color='inverse')
        c.metric('Minima variazione',f'{100*best_v:.2f}%',f'{100*(best_v-original_v):+.2f} punti %',delta_color='inverse')
        st.caption(f'{sum(c.pareto for c in filtered)} soluzioni sul nuovo Pareto. '
                   'Le differenze sono rispetto alla ricerca originale; i due migliori valori possono appartenere a configurazioni diverse.')
    return filtered


def render_motor_optimizer(p: Parameters, install: Callable[[Parameters], None]) -> None:
    st.session_state.setdefault('project_figures',{}).pop('motor_search',None)
    st.subheader('Ottimizzazione motore')
    with st.expander('Impostazioni della ricerca',expanded='motor_search_result' not in st.session_state):
        st.write('Mantieni questo sterzo e confronta collegamenti costruibili con le lunghezze che hai. '
                 'La ricerca prova i fori disponibili sul tirante ed entrambi i montaggi A/B, mantenendo il motore sulla griglia telaio.')
        st.caption('Obiettivi: ridurre la sensibilità massima e renderla uniforme nella stessa corsa richiesta. '
                   'La configurazione manuale cambia soltanto con Carica nel simulatore.')
        st.caption(f'Filtro ingombri 2D attivo · braccetti {p.physical.link_width:g} mm · '
                   f'ruote {p.physical.wheel_diameter:g} × {p.physical.wheel_width:g} mm. '
                   f'giunti B/Q Ø{p.physical.q_joint_diameter:g} mm. '
                   'Misure nella scheda Ingombri 2D. B viene verificato contro leva, astina e Q; corpo motore e altra ferramenta esclusi.')
        neutral = select_pose(solve(p,0),p.branch)
        y0 = float(neutral.b_left[1])
        st.caption(f'Tirante con ruote dritte: Y = {y0:.2f} mm. Il margine è misurato lungo +Y '
                   'dall’asse M al tirante in posa zero, non dall’ingombro del corpo motore.')
        st.caption('Origine A SX = (0, 0). Coordinate e griglia telaio 10 × 10 mm usano lo stesso riferimento. '
                   'Il margine dal tirante ritaglia la zona ammessa, senza spostare la griglia.')
        mode=st.radio('Posizione dell’asse motore', ['Zona rettangolare','Posizione fissa'],horizontal=True,key='motor_search_mode')
        a,b,c=st.columns(3)
        target=a.number_input('Sterzata media richiesta · ±°',min_value=1.,max_value=89.9,value=25.,step=1.,key='search_target')
        crank_text=b.text_input('Leve disponibili · mm','10, 20, 30',key='search_cranks',help='Interassi fra fori. Verranno usati soltanto i valori elencati.')
        rod_text=c.text_input('Astine disponibili · mm','40, 50, 60, 70, 80, 90, 100',key='search_rods')
        st.caption('Le lunghezze proposte sono a passi di 10 mm. Puoi sostituirle con l’elenco esatto dei tuoi componenti.')
        holes_mode=st.radio('Attacco T sul tirante', ['Fori più vicini al centro','Fori specifici'],
                            horizontal=True,key='search_attachment_mode')
        central=central_attachment_holes(p)
        if holes_mode=='Fori specifici':
            holes_text=st.text_input('Fori T disponibili da B SX · mm',', '.join(f'{v:g}' for v in central),
                                    key='search_attachments',help='Distanze lungo il tirante, dal centro del perno B SX. Multipli di 10 mm, separati da virgole.')
        else:
            holes_text=', '.join(f'{v:g}' for v in central)
        st.caption(f'Tirante {p.tie_length:g} mm · fori centrali proposti: '+', '.join(f'{v:g} mm' for v in central)+
                   '. Il passo dei fori è riferito al tirante: T si muove e non deve cadere sulla griglia fissa del telaio.')
        a,b,c=st.columns(3)
        if mode=='Zona rettangolare':
            xmin=a.number_input('X minimo asse · mm',value=float(st.session_state.get('search_xmin',-p.pivot_spacing/2)+p.pivot_spacing/2),step=10.,key='search_xmin_asx')
            xmax=b.number_input('X massimo asse · mm',value=float(st.session_state.get('search_xmax',80.-p.pivot_spacing/2)+p.pivot_spacing/2),step=10.,key='search_xmax_asx')
            step=c.number_input('Passo ricerca X/Y · mm',min_value=10.,value=10.,step=10.,key='search_step',
                                help='Griglia telaio fissa da 10 mm. Un passo 20 mm prova un nodo ogni due; il passo deve essere multiplo di 10.')
            a,b=st.columns(2)
            behind=a.number_input('Margine minimo dietro tirante neutro · mm',min_value=0.,value=10.,step=1.,key='search_behind')
            rear_max=b.number_input('Distanza massima dietro tirante neutro · mm',min_value=0.,value=50.,step=1.,key='search_rear_max')
        else:
            initial_x=chassis_grid_values(p.motor.x+p.pivot_spacing/2,p.motor.x+p.pivot_spacing/2+10)[0]
            fixed_x=a.number_input('X asse fisso · mm',value=float(initial_x),step=10.,key='search_fixed_x_asx')
            initial_y=max(float(p.motor.y),y0+10)
            initial_y=chassis_grid_values(initial_y,initial_y+10)[0]
            fixed_y=b.number_input('Y asse fisso · mm',value=float(initial_y),step=10.,key='search_fixed_y')
            behind=c.number_input('Margine minimo dietro tirante neutro · mm',min_value=0.,value=10.,step=1.,key='search_fixed_behind')
        space=None
        can_search=False
        try:
            cranks,rods=_numbers(crank_text),_numbers(rod_text)
            holes=_numbers(holes_text,allow_zero=True)
            if mode=='Zona rettangolare':
                xs=tuple(x-p.pivot_spacing/2 for x in chassis_grid_values(xmin,xmax,step))
                ys=chassis_grid_values(y0+behind,y0+rear_max,step)
                bounds=(xmin-p.pivot_spacing/2,xmax-p.pivot_spacing/2,y0+behind,y0+rear_max)
            else:
                if fixed_y<y0+behind-p.length_tolerance:
                    raise ValueError('La posizione fissa non rispetta il margine minimo dietro al tirante neutro.')
                xs,ys=(fixed_x-p.pivot_spacing/2,),(fixed_y,)
                bounds=(fixed_x-p.pivot_spacing/2,fixed_x-p.pivot_spacing/2,fixed_y,fixed_y)
            total=len(xs)*len(ys)*len(cranks)*len(rods)*len(holes)*2
            space=SearchSpace(math.radians(target),cranks,rods,xs,ys,behind,holes)
            st.markdown('**Anteprima dei parametri attuali**')
            a,b,c=st.columns(3)
            a.metric('Posizioni motore',len(xs)*len(ys))
            b.metric('Combinazioni per posizione',len(cranks)*len(rods)*len(holes)*2)
            c.metric('Combinazioni teoriche',total)
            st.caption(f'{len(xs)} posizioni X × {len(ys)} posizioni Y × {len(cranks)} leve × '
                       f'{len(rods)} astine × {len(holes)} fori T × 2 montaggi A/B. Sterzata media richiesta: ±{target:g}°.')
            screening=_reachability(p,space)
            a,b,c=st.columns(3)
            a.metric('Scartate subito',screening.rejected_neutral+screening.rejected_margin)
            b.metric('Scartate sulla corsa',screening.rejected_travel)
            c.metric('Da analizzare',screening.remaining)
            st.caption('Il prefiltro verifica le distanze a ruote dritte e lungo la corsa richiesta, '
                       'per entrambi i montaggi A/B. Non verifica ancora sensibilità o interferenze. '
                       f'Si conservano solo le soluzioni ammissibili: massimo {MAX_FEASIBLE_CANDIDATES}. ')
            if len(xs)*len(ys)<=10000:
                st.plotly_chart(_grid_preview(p,space,bounds),use_container_width=True,
                                key='motor_search_grid_preview',config={'displaylogo':False})
                st.caption('Ogni punto è una posizione dell’asse M della griglia originale, prima del prefiltro. '
                           'Il rettangolo mostra i limiti impostati: sono usati solo nodi telaio interni alla zona, '
                           'anche quando i bordi non coincidono con la griglia. Le linee tratteggiate dello sterzo mostrano '
                           'gli estremi richiesti quando raggiungibili dalla geometria.')
            else:
                st.caption('La griglia contiene più di 10000 posizioni: l’anteprima dei punti è omessa. '
                           'Il numero di punti mostrati non limita la ricerca.')
            can_search=True
            if screening.remaining > MAX_FEASIBLE_CANDIDATES:
                st.info(f'{screening.remaining} montaggi da analizzare: la ricerca può partire. '
                        f'Si interrompe solo se supera {MAX_FEASIBLE_CANDIDATES} soluzioni ammissibili dopo tutti i controlli.')
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
                for key in (*FILTER_KEYS,*FILTER_UI_KEYS):st.session_state.pop(key,None)
                st.session_state.pop('motor_axis_cache',None)
                st.session_state.motor_search_result=result
                st.session_state.motor_search_run=uuid.uuid4().hex
                st.session_state.pop('motor_search_selected_id',None)
                st.session_state.pop('motor_search_click',None)
                st.session_state.pop('motor_compare',None)
            except ValueError as exc:
                st.error(str(exc))
                if "motor_search_result" in st.session_state:
                    st.caption("La ricerca non è stata completata: i risultati sotto appartengono alla ricerca precedente.")
            finally:
                if progress is not None:progress.empty()
    result=st.session_state.get('motor_search_result')
    if result is None:
        st.info('Definisci i componenti disponibili e la zona, poi avvia la ricerca. Non parte automaticamente.')
        return
    st.markdown('**Risultati dell’ultima ricerca eseguita**')
    if space is None or space!=result.space:
        st.info('Hai modificato i parametri: l’anteprima sopra è aggiornata, i risultati sotto cambieranno con Cerca configurazioni.')
    if not getattr(result,'b_clearance_checked',False) or not getattr(result,'attachment_grid_checked',False) or not getattr(result,'mounting_grid_checked',False) or not getattr(result,'q_clearance_checked',False) or result.base.physical!=p.physical:
        st.warning('Rilancia la ricerca: questi risultati non sono verificati con gli ingombri B/Q, i fori modulari e la griglia attuali.')
        return
    run_id=st.session_state.motor_search_run
    if replace(p,motor=result.base.motor,actuation_fraction=result.base.actuation_fraction,display_range=result.base.display_range)!=result.base:
        st.warning('Questi risultati si riferiscono alla geometria dello sterzo salvata all’avvio della ricerca. '
                   'Avvia una nuova ricerca per usare le modifiche attuali; caricare un candidato ripristina la sua geometria completa.')
    st.caption(f'{result.detailed_tested} montaggi analizzati · {len(result.feasible)} soluzioni conservate · '
               f'corsa verificata ±{math.degrees(result.space.target):g}° in {result.sample_count} pose.')
    if not result.feasible:
        with st.expander('Motivi di esclusione'):
            st.dataframe([{'Motivo':reason,'Montaggi':count} for reason,count in result.rejected.items()],hide_index=True)
        st.warning('Nessuna soluzione nella zona e con i pezzi indicati. Prova ad ampliare la zona, aggiungere lunghezze o ridurre la sterzata richiesta.')
        return
    filtered=_render_result_filters(result)
    if filtered is None:return
    if not filtered:
        st.info('Nessuna soluzione soddisfa questi filtri. Modificali o usa Azzera filtri; la ricerca originale è conservata.')
        return
    candidates={c.id:c for c in filtered if c.pareto}
    if st.session_state.get('motor_search_selected_id') not in candidates:
        st.session_state.motor_search_selected_id=next(iter(candidates))
    selected_id=st.session_state.motor_search_selected_id
    figure=pareto_plot(list(filtered),selected_id,None,False,reference=result.feasible)
    filter_token=hashlib.sha256(repr((filters_from_settings(st.session_state),st.session_state.motor_filter_axis_diameter)).encode()).hexdigest()[:12]
    selection=st.plotly_chart(figure,use_container_width=True,key=f'motor_pareto_{run_id}_{filter_token}',
                              on_select='rerun',selection_mode='points',config={'displaylogo':False})
    points=selection.selection.points
    if points:
        custom=points[-1].get('customdata')
        clicked=int(custom[0]) if custom else None
        token=(run_id,filter_token,clicked)
        if clicked in candidates and token!=st.session_state.get('motor_search_click'):
            st.session_state.motor_search_click=token
            st.session_state.motor_search_selected_id=clicked
            st.rerun()
    st.caption('Blu: Pareto dopo i filtri · grigio: Pareto originale. In basso a sinistra è meglio. Scegli un punto blu o usa il menu.')
    selected_id=st.selectbox('Configurazione selezionata',list(candidates),key='motor_search_selected_id',
                              format_func=lambda i:f'C{i} · leva {candidates[i].parameters.motor.crank_radius:g} / astina {candidates[i].parameters.motor.connecting_length:g} mm · T a {candidates[i].parameters.actuation_fraction*candidates[i].parameters.tie_length:g} mm da B SX')
    selected=candidates[selected_id]
    motor=selected.parameters.motor
    st.write(f'**C{selected.id}** · M = ({motor.x+selected.parameters.pivot_spacing/2:g}, {motor.y:g}) mm · leva **{motor.crank_radius:g} mm** · '
             f'astina **{motor.connecting_length:g} mm** · montaggio **{"A" if motor.assembly==1 else "B"}** · foro T a **{selected.parameters.actuation_fraction*selected.parameters.tie_length:g} mm da B SX**')
    st.caption(f'Quote di montaggio da A SX: X = {motor.x+selected.parameters.pivot_spacing/2:g} mm, Y = {motor.y:g} mm. '
               'Entrambe appartengono alla griglia da 10 mm; il caricamento conserva esattamente queste coordinate.')
    a,b,c=st.columns(3)
    a.metric('Sensibilità massima · °/°',f'{selected.metrics.max_sensitivity:.4f}')
    b.metric('Variazione della sensibilità',f'{100*selected.metrics.variation:.1f}%')
    c.metric('Corsa albero richiesta',f'{math.degrees(selected.metrics.motor_excursion):.1f}°')
    if st.button('Carica nel simulatore',type='primary',key='apply_motor_search'):
        install(selected.parameters)
        st.rerun()
    view=st.radio('Visualizzazione della soluzione',['Movimento','Curve','Quote e CSV'],horizontal=True,
                  key='motor_results_view',label_visibility='collapsed')
    # Durable comparison state survives hiding the Curve widgets.
    compare_key=f'motor_search_compare_{run_id}'
    stored=st.session_state.get(compare_key,st.session_state.get('motor_compare',[]))
    valid=[i for i in stored if i in candidates and i!=selected_id]
    st.session_state.motor_compare=valid
    if compare_key in st.session_state:st.session_state[compare_key]=valid
    charts={'Pareto motore':figure}
    if view=='Movimento':
        target=result.space.target
        preview_parameters=replace(selected.parameters,display_range=target)
        preview_interval=_preview_interval(replace(selected,pareto=False,rear_clearance=None),target)
        candidate_signature=hashlib.sha256(('candidate:'+to_json(preview_parameters)).encode()).hexdigest()
        browser_motion(preview_parameters,candidate_signature,preview_interval,key='motor_search_preview',
                       motor_axis_diameter=st.session_state.motor_filter_axis_diameter)
        st.caption(f'Animazione nella corsa verificata di ±{math.degrees(target):g}° di sterzata media.')
    elif view=='Curve':
        def keep_comparison():
            st.session_state.motor_compare=list(st.session_state[compare_key])
        other_ids=st.multiselect('Confronta con altre soluzioni Pareto · massimo 2',
                                 [i for i in candidates if i!=selected_id],default=valid,max_selections=2,
                                 format_func=lambda i:f'C{i}',key=compare_key,on_change=keep_comparison)
        ids=[selected_id,*other_ids]
        curves=[(i,_curve(candidates[i],result.space.target)) for i in ids]
        charts['Risposta e sensibilità']=comparison_plot(curves,True)
        st.plotly_chart(charts['Risposta e sensibilità'],use_container_width=True,key='motor_search_curves',config={'displaylogo':False})
        st.caption('Stessa corsa per tutte le curve. Sensibilità mostrata in valore assoluto: gradi di sterzo medio per grado di motore.')
    else:
        charts['Quote di montaggio']=mounting_plot(selected.parameters,st.session_state.motor_filter_axis_diameter)
        st.plotly_chart(charts['Quote di montaggio'],use_container_width=True,key='motor_mounting_dimensions',config={'displaylogo':False})
        st.dataframe([{'Quota':name,'Valore':value} for name,value in mounting_rows(selected.parameters)],hide_index=True,use_container_width=True)
        clearance=getattr(selected,'rear_clearance',None)
        if clearance is not None:
            st.caption(f'Spazio minimo della leva dietro al tirante mobile: {clearance:.3f} mm. '
                       'Un valore positivo soddisfa il vincolo nelle pose campionate.')
        a,b=st.columns(2)
        rows=_table(filtered,st.session_state.get('motor_axis_cache',{}),st.session_state.motor_filter_axis_diameter)
        a.download_button('Risultati filtrati CSV',_csv(rows),'motor-search-filtered.csv','text/csv',use_container_width=True)
        b.download_button('Curva selezionata CSV',response_csv(_curve(selected,result.space.target)),
                          f'motor-candidate-{selected_id}.csv','text/csv',use_container_width=True)
        with st.expander('Tabella e motivi di esclusione'):
            st.dataframe(rows,hide_index=True,use_container_width=True)
            st.dataframe([{'Motivo':reason,'Montaggi':count} for reason,count in result.rejected.items()],hide_index=True)
    if st.session_state.motor_filter_axis_diameter>0:
        available=st.session_state.motor_axis_cache.get(selected_id)
        if available is not None:st.caption(f'Asse Ø{st.session_state.motor_filter_axis_diameter:g} mm · minimo spazio residuo {available-st.session_state.motor_filter_axis_diameter/2:.3f} mm nella corsa verificata.')
    caption=f'Collegamento motore · C{selected_id} · {len(filtered)}/{len(result.feasible)} soluzioni'
    remember_figures('motor_search',caption,charts)
