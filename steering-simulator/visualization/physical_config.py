"""Only the dimensions that define occupied space in the top view."""
from dataclasses import replace
import streamlit as st
from steering.parameters import Physical
from steering.kinematics import select_pose, solve
from .top_view import top_view


def render_physical_config(p, install):
    st.subheader('Ingombri 2D')
    st.write('Dimensioni comuni ai due lati dello sterzo. La larghezza vale per bracci, staffe, '
             'tirante, leva e astina del motore.')
    f = p.physical
    key = f'{f.wheel_diameter:g}_{f.wheel_width:g}_{f.link_width:g}'
    with st.form(f'physical_dimensions_{key}'):
        a, b, c = st.columns(3)
        diameter = a.number_input('Diametro ruote · mm', min_value=.1, value=float(f.wheel_diameter), step=1.)
        tire = b.number_input('Larghezza pneumatici · mm', min_value=.1, value=float(f.wheel_width), step=1.)
        link = c.number_input('Larghezza comune braccetti · mm', min_value=.1, value=float(f.link_width), step=1.,
                              help='Misura trasversale in pianta. Gli estremi sporgono dal centro dei fori di metà larghezza.')
        if st.form_submit_button('Applica ingombri 2D', type='primary'):
            updated = replace(p, physical=Physical(diameter, tire, link))
            updated.validate()
            install(updated)
            st.rerun()
    st.caption('Queste misure aggiornano il disegno e il filtro dell’ottimizzazione; non cambiano la cinematica. '
               'Per applicarle ai risultati serve una nuova ricerca. Il corpo motore, viti e perni non sono ostacoli.')
    st.plotly_chart(top_view(p, select_pose(solve(p, 0), p.branch), [], trajectories=False),
                    use_container_width=True, key='physical_dimensions_view', config={'displaylogo':False})
    st.caption('Vista dall’alto: le ruote sono rettangoli e i braccetti sono fasce rettangolari. '
               'Il filtro scarta anche il semplice contatto; la sovrapposizione al tirante è ammessa. '
               'La ricerca verifica le pose campionate lungo la corsa richiesta, senza considerare quote verticali.')
