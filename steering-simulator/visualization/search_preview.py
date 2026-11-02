"""Draw the actual discrete search inputs without running the motor search."""
from itertools import product
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from steering.kinematics import select_pose, solve, steering_input
from steering.reference import chassis_pose
from steering.motor_search import attachment_distances


def search_preview(p, space, bounds):
    neutral = chassis_pose(p,select_pose(solve(p, 0), p.branch))
    y0 = float(neutral.b_left[1])
    fig = make_subplots(rows=2, cols=2, specs=[[{'colspan': 2}, None], [{}, {}]],
                        row_heights=[.72, .28], vertical_spacing=.15,
                        subplot_titles=('Posizioni dell’asse motore · vista dall’alto',
                                        'Leve disponibili · interasse fori', 'Astine disponibili · interasse fori'))
    # Both the rectangle and its grid use exactly the bounds/positions used by search.
    xmin, xmax, ymin, ymax = bounds
    xmin+=p.pivot_spacing/2
    xmax+=p.pivot_spacing/2
    fig.add_shape(type='rect', x0=xmin, x1=xmax, y0=ymin, y1=ymax,
                  fillcolor='rgba(57,118,196,.10)', line=dict(color='#3976c4'), row=1, col=1)
    for mean, name, color, dash in ((0., 'Sterzo a ruote dritte', '#243548', 'solid'),
                                   (-space.target, 'Sterzata negativa richiesta', '#df8628', 'dot'),
                                   (space.target, 'Sterzata positiva richiesta', '#138777', 'dot')):
        pose = chassis_pose(p,select_pose(solve(p, steering_input(p, mean)), p.branch))
        if pose is None or abs((pose.theta_left+pose.theta_right)/2-mean) > 1e-6:
            continue
        fig.add_trace(go.Scatter(x=[pose.a_left[0], pose.b_left[0], pose.b_right[0], pose.a_right[0]],
                                y=[pose.a_left[1], pose.b_left[1], pose.b_right[1], pose.a_right[1]],
                                mode='lines+markers', name=name,
                                line=dict(color=color, width=3 if mean == 0 else 1.5, dash=dash),
                                hovertemplate='X %{x:.1f} · Y %{y:.1f} mm<extra>%{fullData.name}</extra>'), row=1, col=1)
    holes=attachment_distances(p,space)
    locations=[neutral.b_left+(distance/p.tie_length)*(neutral.b_right-neutral.b_left) for distance in holes]
    fig.add_trace(go.Scatter(x=[v[0] for v in locations],y=[v[1] for v in locations],
                            mode='markers+text',name='Fori T da provare sul tirante',
                            text=[f'{distance:g} mm' for distance in holes],
                            textposition=['top center' if i%2==0 else 'bottom center' for i in range(len(holes))],
                            customdata=list(holes),marker=dict(color='#138777',size=11),
                            hovertemplate='Foro T · %{customdata:g} mm da B SX<br>X %{x:.3f} / Y %{y:.3f} mm a ruote dritte<extra></extra>'),row=1,col=1)
    fig.add_trace(go.Scatter(x=[0,p.pivot_spacing],y=[0,0],mode='markers+text',
                            text=['A SX · O (0,0)','A DX'],textposition='top center',
                            marker=dict(size=8,color='#243548'),showlegend=False),row=1,col=1)
    positions = list(product((x+p.pivot_spacing/2 for x in space.x_positions), space.y_positions))
    fig.add_trace(go.Scattergl(x=[xy[0] for xy in positions], y=[xy[1] for xy in positions],
                              mode='markers', name=f'Assi motore da provare · {len(positions)}',
                              marker=dict(size=6 if len(positions)>500 else 9, color='#3976c4'),
                              hovertemplate='Asse M · X %{x:.1f} / Y %{y:.1f} mm da A SX<extra></extra>'), row=1, col=1)
    left = min(xmin, float(neutral.a_left[0]), float(neutral.b_left[0]))
    right = max(xmax, float(neutral.a_right[0]), float(neutral.b_right[0]))
    fig.add_shape(type='line', x0=left, x1=right, y0=y0+space.min_behind, y1=y0+space.min_behind,
                  line=dict(color='#c07125', dash='dash'), row=1, col=1)
    fig.add_annotation(x=right, y=y0+space.min_behind, text=f'Margine minimo: {space.min_behind:g} mm',
                       showarrow=False, yshift=12, xanchor='right', font=dict(color='#a45c18'), row=1, col=1)
    fig.add_annotation(x=xmin, y=(y0+ymin)/2, ax=xmin, ay=y0, axref='x', ayref='y',
                       text='Dietro · +Y', showarrow=True, arrowhead=2, row=1, col=1)
    for column, lengths, color in ((1, space.crank_lengths, '#df8628'), (2, space.rod_lengths, '#138777')):
        for index, length in enumerate(lengths):
            fig.add_trace(go.Scatter(x=[0, length], y=[index, index], mode='lines+markers',
                                    line=dict(color=color, width=4), marker=dict(size=8), showlegend=False,
                                    hovertemplate=f'Interasse {length:g} mm<extra></extra>'), row=2, col=column)
        fig.update_yaxes(tickvals=list(range(len(lengths))), ticktext=[f'{v:g} mm' for v in lengths],
                         zeroline=False, row=2, col=column)
        fig.update_xaxes(title_text='mm', range=[0, 1.1*max(*space.crank_lengths, *space.rod_lengths)], row=2, col=column)
    fig.update_xaxes(title_text='X da A SX · mm', row=1, col=1)
    fig.update_yaxes(title_text='Y · mm · retro ↓', autorange='reversed', scaleanchor='x', scaleratio=1, row=1, col=1)
    fig.update_layout(template='plotly_white', height=760,
                      margin=dict(l=30, r=25, t=45, b=30),
                      legend=dict(orientation='h', y=1.17, x=0), hovermode='closest')
    return fig
