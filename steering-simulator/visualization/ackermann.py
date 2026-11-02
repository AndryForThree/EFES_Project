"""A small, self-contained Ackermann presentation sheet for the chosen geometry."""
import math
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from steering.ackermann import diagnose_ackermann


@st.cache_data(show_spinner=False,max_entries=32)
def _diagnosis(parameters,wheelbase,target,count):
    return diagnose_ackermann(parameters,wheelbase,target,count)


def render_ackermann(candidate,result):
    fit,curve,equivalent=_diagnosis(candidate.parameters,result.wheelbase,result.target,result.sample_count)
    label=f'{fit.equivalent_wheelbase:.1f} mm' if fit.status=='finite' else ('∞ · parallelo' if fit.status=='infinite' else 'Non disponibile')
    a,b,c=st.columns(3)
    a.metric('Passo usato nella ricerca',f'{fit.reference_wheelbase:g} mm')
    b.metric('Passo equivalente stimato',label)
    c.metric('Errore massimo al passo equivalente',f'{math.degrees(fit.fitted_error):.3f}°' if fit.fitted_error is not None else '—')
    st.caption('Passo = distanza tra asse anteriore e posteriore. Il passo equivalente descrive il comportamento dello sterzo: '
               'è una stima, non una lunghezza reale misurata e non la lunghezza totale del veicolo.')
    if fit.status=='finite':
        st.info(f'Questa geometria si avvicina a uno sterzo Ackermann con passo di {fit.equivalent_wheelbase:.1f} mm. '
                f'L’errore massimo passa da {math.degrees(fit.reference_error):.3f}° con il riferimento della ricerca '
                f'a {math.degrees(fit.fitted_error):.3f}° con il passo equivalente.')
    elif fit.status=='infinite':
        st.info('Le ruote sterzano dello stesso angolo: il riferimento equivalente è il limite di passo infinito.'
                if fit.behavior=='Ruote parallele' else
                'Il miglior riferimento con passo positivo è il limite di ruote parallele: non emerge un passo equivalente finito.')
    else:
        st.info('In parte della corsa le ruote non seguono una normale curva Ackermann a passo positivo: il passo equivalente non viene stimato.')
    if fit.behavior in ('Anti-Ackermann','Misto'):
        st.caption('Comportamento: '+fit.behavior+'. '+('La ruota interna sterza meno dell’esterna.' if fit.behavior=='Anti-Ackermann' else
                   'Il rapporto tra ruota interna ed esterna cambia tipo lungo la corsa.'))
    degrees=lambda values:np.degrees(values)
    figure=make_subplots(rows=1,cols=2,subplot_titles=('Come sterzano le due ruote','Scostamento dal riferimento ideale'))
    figure.add_trace(go.Scatter(x=degrees(curve['outer']),y=degrees(curve['inner']),name=f'Geometria Q{candidate.id}',
                               line=dict(color='#3976c4',width=3),mode='lines'),row=1,col=1)
    references=[(f'Passo ricerca · {result.wheelbase:g} mm',curve['ideal'],'#94a3b8','dash')]
    if equivalent is not None:
        references.append((f'Passo equivalente · {label}',equivalent,'#138777','dot'))
    for name,ideal,color,dash in references:
        figure.add_trace(go.Scatter(x=degrees(curve['outer']),y=degrees(ideal),name=name,legendgroup=name,
                                   mode='lines',line=dict(color=color,dash=dash,width=2)),row=1,col=1)
        figure.add_trace(go.Scatter(x=degrees(curve['mean']),y=degrees(curve['inner']-ideal),name=name,legendgroup=name,
                                   showlegend=False,mode='lines',line=dict(color=color,dash=dash,width=2)),row=1,col=2)
    figure.add_hline(y=0,line_color='#cbd5e1',line_dash='dot',row=1,col=2)
    figure.update_xaxes(title_text='Ruota esterna · °',row=1,col=1)
    figure.update_yaxes(title_text='Ruota interna · °',row=1,col=1)
    figure.update_xaxes(title_text='Sterzata media · °',row=1,col=2)
    figure.update_yaxes(title_text='Interna reale − ideale · °',row=1,col=2)
    error_label=f'{math.degrees(fit.fitted_error):.3f}°' if fit.fitted_error is not None else 'non stimabile'
    figure.update_layout(template='plotly_white',height=500,margin=dict(l=30,r=20,t=115,b=45),hovermode='x unified',
                         legend=dict(orientation='h',y=1.23),
                         title=dict(text=f'Q{candidate.id} · riferimento {result.wheelbase:g} mm / equivalente {label}<br>'
                                    f'<sup>Errore massimo: riferimento {math.degrees(fit.reference_error):.3f}° / equivalente {error_label}</sup>',font=dict(size=15)))
    st.plotly_chart(figure,use_container_width=True,key='quad_ackermann_diagnosis',config={'displaylogo':False})
    st.caption(f'Confronto sulla stessa corsa della ricerca: 0–{math.degrees(result.target):g}° medi, '
               f'{result.sample_count} pose. Per simmetria vale anche nell’altro verso. '
               'A destra, zero significa coincidenza con il riferimento; positivo = interna più sterzata, negativo = meno sterzata.')
    with st.expander('Come leggere la stima'):
        st.write('Il passo equivalente è unico per tutta la curva: viene scelto per ridurre il massimo errore angolare '
                 'tra ruota interna reale e ideale. Un errore residuo basso indica una buona somiglianza con quel riferimento, '
                 'non dimostra che lo sterzo sia adatto a qualsiasi veicolo. Si usa la stessa carreggiata neutra della ricerca.')
        st.caption('Questa scheda è diagnostica: non cambia geometria, riferimento della ricerca, obiettivi o Pareto.')
    return figure
