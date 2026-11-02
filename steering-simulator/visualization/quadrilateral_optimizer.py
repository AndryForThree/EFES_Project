"""Choose a buildable quadrilateral before searching for a motor linkage."""
from dataclasses import replace
import csv
import io
import hashlib
import math
import uuid
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from steering.motor import MotorRange
from steering.quadrilateral_filters import FILTER_KEYS,filter_candidates,filters_from_settings
from steering.kinematics import solve,select_pose
from steering.reference import chassis_pose
from steering.parameters import steering_from_lengths, to_json
from steering.quadrilateral_search import search_quadrilaterals, ackermann_curve, point_motion_curve
from .browser_motion import browser_motion
from .project_controls import remember_figures


def _numbers(text):
    try:
        values=tuple(dict.fromkeys(float(v.strip()) for v in text.split(',')))
    except ValueError as exc:
        raise ValueError('Inserisci misure in mm separate da virgole.') from exc
    return values


def _label(c):
    p=c.parameters
    return f'Q{c.id} · A {p.pivot_spacing:g} / braccio {p.left.arm_length:g} / tirante {p.tie_length:g} mm'


def _csv(rows):
    output=io.StringIO()
    if rows:
        writer=csv.DictWriter(output,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return output.getvalue()


def _table(candidates):
    return [{'ID':f'Q{c.id}','Pareto':c.pareto,'Interasse A · mm':c.parameters.pivot_spacing,
             'Braccio · mm':c.parameters.left.arm_length,'Tirante · mm':c.parameters.tie_length,
             'Inclinazione · °':math.degrees(c.parameters.left.arm_angle-math.pi/2),
             'Errore Ackermann max · °':math.degrees(c.ackermann_error),
             'Sterzata massima · ±°':math.degrees(c.evaluation.steering_limit),
             'Movimento minimo T · mm/°':c.min_point_motion,'Carreggiata · mm':c.neutral_track} for c in candidates]


@st.cache_data(show_spinner=False,max_entries=32)
def _curves(p,wheelbase,target,count):
    return ackermann_curve(p,wheelbase,target,count),point_motion_curve(p,target,count)


def _render_filters(result):
    with st.expander('Filtra e confronta i risultati',expanded=True):
        st.caption('Escludi misure dai risultati già calcolati. Nessuna nuova ricerca; il Pareto si aggiorna sui tre obiettivi.')
        if st.button('Azzera filtri',key='quad_filters_reset'):
            for key in FILTER_KEYS:st.session_state.pop(key,None)
        for column,label,key,values in zip(st.columns(3),
            ('Interassi A inclusi · mm','Bracci inclusi · mm','Tiranti inclusi · mm'),FILTER_KEYS,
            ([c.parameters.pivot_spacing for c in result.candidates],
             [c.parameters.left.arm_length for c in result.candidates],
             [c.parameters.tie_length for c in result.candidates])):
            options=sorted(set(values))
            if key in st.session_state:st.session_state[key]=[v for v in st.session_state[key] if v in options]
            column.multiselect(label,options,default=options,key=key,format_func=lambda v:f'{v:g}')
    filtered=filter_candidates(result,filters_from_settings(st.session_state))
    a,b,c=st.columns(3)
    a.metric('Geometrie rimaste',len(filtered),f'{len(filtered)-len(result.candidates)} rispetto alla ricerca',delta_color='off')
    if filtered:
        error=min(v.ackermann_error for v in filtered);base_error=min(v.ackermann_error for v in result.candidates)
        travel=max(v.evaluation.steering_limit for v in filtered);base_travel=max(v.evaluation.steering_limit for v in result.candidates)
        motion=max(v.min_point_motion for v in filtered);base_motion=max(v.min_point_motion for v in result.candidates)
        b.metric('Massima sterzata · ±°',f'{math.degrees(travel):.2f}',f'{math.degrees(travel-base_travel):+.2f}')
        c.metric('Miglior movimento minimo T · mm/°',f'{motion:.4f}',f'{motion-base_motion:+.4f}')
        st.caption(f'{sum(v.pareto for v in filtered)} geometrie sul Pareto filtrato. '
                   f'Minimo errore Ackermann {math.degrees(error):.3f}° (differenza {math.degrees(error-base_error):+.3f}°). '
                   'Differenze rispetto alla ricerca originale; i migliori valori possono appartenere a geometrie diverse.')
    return filtered


def render_quadrilateral_optimizer(p, install):
    st.session_state.setdefault('project_figures',{}).pop('quadrilateral',None)
    st.subheader('Ricerca quadrilatero · griglia 10 × 10 mm')
    with st.expander('Impostazioni della ricerca',expanded='quadrilateral_search_result' not in st.session_state):
        st.write('Scegli gli interassi disponibili: l’inclinazione viene ricavata per mantenere simmetria, '
                 'ruote dritte a zero e bracci verso il retro. Il collegamento motore non entra nella ricerca.')
        st.caption('Griglia telaio riferita al perno A SX: A SX = (0, 0), A DX = (d, 0). '
                   'Il disegno e tutte le coordinate usano A SX come origine; d = 190 mm corrisponde a 19 passi. '
                   'I giunti mobili B non devono appartenere alla griglia del telaio.')
        with st.form('quadrilateral_search'):
            a,b,c=st.columns(3)
            spacings=a.text_input('Interassi perni A disponibili · mm','160, 170, 180, 190, 200',key='quad_spacings')
            lengths=b.text_input('Bracci disponibili · mm','20, 30, 40',key='quad_lengths')
            ties=c.text_input('Tiranti disponibili · mm','140, 150, 160, 170, 180, 190, 200',key='quad_ties')
            a,b=st.columns(2)
            wheelbase=b.number_input('Passo virtuale · mm',min_value=.1,value=200.,step=10.,key='quad_wheelbase',
                                      help='Distanza dall’asse anteriore all’asse posteriore virtuale. Non modifica lo sterzo reale.')
            target=a.number_input('Sterzata media richiesta e di confronto · ±°',min_value=1.,max_value=89.9,value=25.,step=1.,key='quad_target')
            st.caption('Solo multipli di 10 mm. Si escludono le geometrie impossibili, allineate a zero '
                       'o che raggiungono un punto morto prima della corsa richiesta. Massimo 2000 combinazioni.')
            run=st.form_submit_button('Cerca quadrilateri',type='primary')
        if run:
            bar=st.progress(0,text='Confronto geometrie…')
            try:
                result=search_quadrilaterals(p,_numbers(spacings),_numbers(lengths),_numbers(ties),math.radians(target),
                                            lambda n,total:bar.progress(n/total,text=f'{n}/{total} geometrie'),wheelbase=wheelbase)
                for key in FILTER_KEYS:st.session_state.pop(key,None)
                st.session_state.pop('_quad_compare_widget',None)
                st.session_state.quadrilateral_search_result=result
                st.session_state.quad_run=uuid.uuid4().hex
                st.session_state.pop('quad_click',None)
                st.session_state.pop('quad_selected',None)
                st.session_state.pop('quad_compare',None)
            except ValueError as exc:
                st.error(str(exc))
                if 'quadrilateral_search_result' in st.session_state:
                    st.caption('I risultati sotto appartengono all’ultima ricerca riuscita.')
            finally:
                bar.empty()
    result=st.session_state.get('quadrilateral_search_result')
    if result is None:
        st.info('Avvia la ricerca, confronta le geometrie e carica quella che preferisci. Poi passa a Ottimizzazione motore.')
        return
    if not getattr(result,'motion_checked',False):
        st.info('Rilancia la ricerca per calcolare il movimento minimo di T e il Pareto a tre obiettivi.')
        return
    run_id=st.session_state.quad_run
    st.caption(f'{result.tested} combinazioni · {len(result.candidates)} geometrie utilizzabili · '
               f'corsa di confronto ±{math.degrees(result.target):g}° · passo virtuale {result.wheelbase:g} mm. '
               'Motore e interferenze fisiche esclusi da questa ricerca.')
    if result.candidates and p.left.axle_x!=result.candidates[0].parameters.left.axle_x:
        st.warning('L’offset X delle ruote è cambiato: rilancia la ricerca per aggiornare carreggiate e riferimento Ackermann.')
        return
    if p.actuation_fraction!=result.point_fraction:
        st.warning('Il punto di attacco T sul tirante è cambiato: rilancia la ricerca per aggiornare il movimento minimo.')
        return
    if not result.candidates:
        st.warning('Nessuna geometria utilizzabile: cambia gli elenchi o riduci la corsa richiesta.')
        return
    filtered=_render_filters(result)
    if not filtered:
        st.info('Nessuna geometria soddisfa i filtri. Modificali o usa Azzera filtri: la ricerca originale è conservata.')
        return
    candidates={c.id:c for c in filtered if c.pareto}
    if st.session_state.get('quad_selected') not in candidates:
        st.session_state.quad_selected=next(iter(candidates))
    selected_id=st.session_state.quad_selected
    views=['2D · proiezione','3D']
    if st.session_state.get('quad_pareto_view') not in (None,*views):
        st.session_state.quad_pareto_view='2D · proiezione'
    mode=st.radio('Vista del Pareto',views,horizontal=True,key='quad_pareto_view')
    three_d=mode=='3D'
    filter_token=hashlib.sha256(repr(filters_from_settings(st.session_state)).encode()).hexdigest()[:12]
    fig=go.Figure()
    for original,name in ((True,'Pareto originale'),(False,'Pareto filtrato')):
        points=[c for c in (result.candidates if original else filtered) if c.pareto]
        if not points:
            continue
        trace=go.Scatter3d if three_d else go.Scatter
        kwargs=dict(x=[math.degrees(c.ackermann_error if three_d else c.evaluation.steering_limit) for c in points],
                    y=[math.degrees(c.evaluation.steering_limit) if three_d else c.min_point_motion for c in points],
                    mode='markers',name=name,text=[_label(c) for c in points],
                    customdata=[[None if original else c.id,c.min_point_motion,math.degrees(c.ackermann_error)] for c in points],
                    marker=dict(size=(4 if original else 6) if three_d else (6 if original else 9),
                                symbol='circle',color='#b0bac5' if original else '#3976c4',
                                opacity=.55 if original else 1),
                    hovertemplate=('%{text}<br>Errore Ackermann max %{x:.3f}°<br>Corsa ±%{y:.2f}°'
                                   '<br>T minimo %{customdata[1]:.4f} mm/°<extra></extra>' if three_d else
                                   '%{text}<br>Sterzata massima ±%{x:.2f}°<br>T minimo %{y:.4f} mm/°'
                                   '<br>Errore Ackermann max %{customdata[2]:.3f}°<extra></extra>'))
        if three_d:
            kwargs['z']=[c.min_point_motion for c in points]
        fig.add_trace(trace(**kwargs))
    picked=candidates[selected_id]
    kwargs=dict(x=[math.degrees(picked.ackermann_error if three_d else picked.evaluation.steering_limit)],
                y=[math.degrees(picked.evaluation.steering_limit) if three_d else picked.min_point_motion],
                customdata=[[picked.id,picked.min_point_motion]],mode='markers',name='Selezionata',
                marker=dict(size=10 if three_d else 17,symbol='circle-open',
                            color='#243548',line=dict(width=2)),hoverinfo='skip')
    if three_d:
        kwargs['z']=[picked.min_point_motion]
    fig.add_trace((go.Scatter3d if three_d else go.Scatter)(**kwargs))
    fig.update_layout(template='plotly_white',height=600 if three_d else 400,
                      margin=dict(l=40,r=40,t=45,b=40),uirevision=run_id,
                      font=dict(family='Arial, sans-serif',size=12,color='#334155'),
                      paper_bgcolor='white',
                      legend=dict(orientation='h',x=0,y=1.06,font=dict(size=12)),
                      hoverlabel=dict(bgcolor='white',font=dict(color='#243548')))
    if three_d:
        axis_style=dict(showbackground=True,backgroundcolor='#fafbfc',gridcolor='#e3e8ee',
                        zeroline=False,showline=True,linecolor='#bac5d0',tickfont=dict(size=11,color='#64748b'))
        fig.update_layout(scene=dict(
            xaxis=dict(**axis_style,title=dict(text='Errore Ackermann (°)',font=dict(size=12))),
            yaxis=dict(**axis_style,title=dict(text='Escursione (±°)',font=dict(size=12))),
            zaxis=dict(**axis_style,title=dict(text='Movimento minimo T (mm/°)',font=dict(size=12))),
            aspectmode='cube',camera=dict(eye=dict(x=1.5,y=1.5,z=1.1),projection=dict(type='orthographic'))))
        st.plotly_chart(fig,use_container_width=True,key=f'quad_pareto_3d_{run_id}',config={'displaylogo':False})
        st.caption('Ruota il grafico trascinando. Cerca meno errore (X), più sterzo (Y) e più movimento minimo di T (Z). '
                   'Seleziona dal menu sotto oppure clicca i punti nella vista 2D.')
    else:
        fig.update_layout(xaxis_title='Sterzata media massima · ±° → più alta è meglio',
                          yaxis_title='Movimento minimo T · mm/° → più alto è meglio',clickmode='event+select')
        selection=st.plotly_chart(fig,use_container_width=True,key=f'quad_pareto_2d_{run_id}_{filter_token}',
                                  on_select='rerun',selection_mode='points',config={'displaylogo':False})
        if selection.selection.points:
            custom=selection.selection.points[-1].get('customdata')
            clicked=int(custom[0]) if custom and custom[0] is not None else None
            if clicked in candidates and st.session_state.get('quad_click')!=(run_id,filter_token,clicked):
                st.session_state.quad_click=(run_id,filter_token,clicked)
                st.session_state.quad_selected=clicked
                st.rerun()
        st.caption('In alto a destra è meglio. L’errore Ackermann resta consultabile passando sul punto. '
                   'Il Pareto resta calcolato sui tre obiettivi, anche quando si osserva questa proiezione 2D.')
    st.caption('Blu: Pareto dopo i filtri · grigio: Pareto originale. Il fronte usa tutti e tre gli obiettivi, anche nella proiezione 2D.')
    selected_id=st.selectbox('Quadrilatero selezionato',list(candidates),key='quad_selected',format_func=lambda i:_label(candidates[i]))
    selected=candidates[selected_id]
    q=selected.parameters
    a,b=st.columns(2)
    a.metric('Sterzata massima · ±°',f'{math.degrees(selected.evaluation.steering_limit):.2f}')
    b.metric('Movimento minimo T · mm/°',f'{selected.min_point_motion:.4f}')
    st.caption(f'Errore Ackermann massimo {math.degrees(selected.ackermann_error):.3f}° · carreggiata neutra {selected.neutral_track:g} mm. Il movimento di T è |dT/dm|: '
               'più alto significa più spostamento disponibile per ogni grado di sterzo; '
               'non determina da solo la sensibilità finale del motore.')
    # Preserve current motor, offsets and physical dimensions when applying geometry.
    preview=steering_from_lengths(p,q.pivot_spacing,q.left.arm_length,q.tie_length)
    if st.button('Carica quadrilatero nel simulatore',type='primary'):
        install(preview)
        st.rerun()
    view=st.radio('Visualizzazione del quadrilatero',['Movimento','Curve','Ackermann','Quote e CSV'],
                  horizontal=True,key='quad_results_view',label_visibility='collapsed')
    valid=[i for i in st.session_state.get('quad_compare',[]) if i in candidates and i!=selected_id]
    st.session_state.quad_compare=valid
    if '_quad_compare_widget' in st.session_state:st.session_state._quad_compare_widget=valid
    charts={'Pareto del quadrilatero':fig}
    if view=='Movimento':
        preview=replace(preview,display_range=result.target)
        signature=hashlib.sha256(('quadrilateral:'+to_json(preview)).encode()).hexdigest()
        browser_motion(preview,signature,MotorRange(False,''),key='quadrilateral_preview',steering_only=True)
        st.caption(f'Anteprima del solo quadrilatero nella corsa richiesta ±{math.degrees(result.target):g}°. '
                   'Il caricamento è l’unica azione che applica la geometria al simulatore.')
    elif view=='Curve':
        def keep_comparison():
            st.session_state.quad_compare=list(st.session_state._quad_compare_widget)
        other_ids=st.multiselect('Confronta con altri quadrilateri · massimo 2',[i for i in candidates if i!=selected_id],
                                default=valid,key='_quad_compare_widget',max_selections=2,
                                format_func=lambda i:f'Q{i}',on_change=keep_comparison)
        curves=make_subplots(rows=1,cols=2,subplot_titles=('Ruota interna: reale e Ackermann ideale','Errore Ackermann con segno'))
        movements=go.Figure()
        for i,color in zip([selected_id,*other_ids],('#3976c4','#df8628','#138777')):
            curve,motion=_curves(candidates[i].parameters,result.wheelbase,result.target,result.sample_count)
            degrees=lambda values:[math.degrees(v) for v in values]
            movements.add_trace(go.Scatter(x=degrees(motion['mean']),y=motion['movement'],
                                          name=f'Q{i}',mode='lines',line=dict(color=color)))
            curves.add_trace(go.Scatter(x=degrees(curve['outer']),y=degrees(curve['inner']),
                                        name=f'Q{i} reale',mode='lines',line=dict(color=color)),row=1,col=1)
            curves.add_trace(go.Scatter(x=degrees(curve['outer']),y=degrees(curve['ideal']),
                                        name=f'Q{i} ideale',mode='lines',line=dict(color=color,dash='dash')),row=1,col=1)
            curves.add_trace(go.Scatter(x=degrees(curve['mean']),y=degrees(curve['error']),
                                        name=f'Q{i}',mode='lines',line=dict(color=color),showlegend=False),row=1,col=2)
        curves.add_hline(y=0,line_dash='dot',line_color='#8296a7',row=1,col=2)
        curves.update_xaxes(title_text='Angolo ruota esterna · °',row=1,col=1)
        curves.update_yaxes(title_text='Angolo ruota interna · °',row=1,col=1)
        curves.update_xaxes(title_text='Sterzata media · °',row=1,col=2)
        curves.update_yaxes(title_text='Interna reale − ideale · °',row=1,col=2)
        curves.update_layout(template='plotly_white',height=360,margin=dict(l=20,r=20,t=40,b=20))
        st.plotly_chart(curves,use_container_width=True,key='quad_comparison',config={'displaylogo':False})
        st.caption('Errore positivo: interna più sterzata dell’ideale. Negativo: interna meno sterzata. '
                   'Le linee tratteggiate sono il riferimento ideale, diverso quando cambia la carreggiata.')
        movements.update_layout(template='plotly_white',height=270,margin=dict(l=20,r=20,t=15,b=20),
                                xaxis_title='Sterzata media · °',yaxis_title='Movimento T · mm/°')
        st.plotly_chart(movements,use_container_width=True,key='quad_point_movement',config={'displaylogo':False})
        charts.update({'Ackermann reale e ideale':curves,'Movimento del punto T':movements})
    elif view=='Ackermann':
        from .ackermann import render_ackermann
        charts['Scheda Ackermann']=render_ackermann(selected,result)
    else:
        pose=chassis_pose(q,select_pose(solve(q,0.),q.branch))
        rows=[('Interasse A',q.pivot_spacing),('Lunghezza bracci',q.left.arm_length),('Lunghezza tirante',q.tie_length)]
        st.dataframe([{'Quota':'A SX · origine','Valore':'(0, 0) mm'},
                      *[{'Quota':name,'Valore':f'{value:g} mm'} for name,value in rows],
                      {'Quota':'Inclinazione bracci','Valore':f'{math.degrees(q.left.arm_angle-math.pi/2):.3f}°'},
                      *[{'Quota':label+' · X / Y da A SX, ruote dritte','Valore':f'{point[0]:.3f} / {point[1]:.3f} mm'}
                        for label,point in (('A DX',pose.a_right),('B SX',pose.b_left),('B DX',pose.b_right))]],
                     hide_index=True,use_container_width=True)
        table=_table(filtered)
        st.download_button('Risultati filtrati CSV',_csv(table),'quadrilateral-filtered.csv','text/csv')
        with st.expander('Tabella e dettagli della ricerca'):
            st.dataframe(table,hide_index=True,use_container_width=True)
            st.caption(f'{result.rejected_closure} escluse a zero · {result.rejected_range} escluse per corsa insufficiente · '
                       f'{result.rejected_track} escluse per carreggiata. Errore Ackermann su {result.sample_count} pose; '
                       f'movimento minimo T su {2*result.sample_count-1} pose, attacco λ = {result.point_fraction:g}.')
    remember_figures('quadrilateral',f'Quadrilatero Q{selected_id} · {len(filtered)}/{len(result.candidates)} geometrie',charts)
