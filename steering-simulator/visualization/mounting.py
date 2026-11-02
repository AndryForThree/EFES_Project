"""Neutral mounting drawing and precise dimensions for the two independent grids."""
import math
import plotly.graph_objects as go
from steering.reference import mounting_coordinates


def mounting_rows(p):
    points=mounting_coordinates(p)
    distance=p.actuation_fraction*p.tie_length
    rows=[('Foro T da B SX, lungo il tirante',f'{distance:.3f} mm'),
          ('Foro T da B DX, lungo il tirante',f'{p.tie_length-distance:.3f} mm')]
    rows.extend((f'{name.replace("_"," ")} a ruote dritte · X / Y da A SX',
                 f'{point[0]:.3f} / {point[1]:.3f} mm')
                for name,point in points.items() if point is not None and name!='A_SX')
    q=points['Q'];m=points['M']
    if q is not None:
        rows.append(('Orientamento leva M–Q a ruote dritte, da +X verso +Y',
                     f'{math.degrees(math.atan2(q[1]-m[1],q[0]-m[0])):.3f}°'))
    return rows


def mounting_plot(p,motor_axis_diameter=0.):
    points=mounting_coordinates(p)
    fig=go.Figure()
    def segment(names,color,width):
        xy=[points[name] for name in names]
        if any(point is None for point in xy):return
        fig.add_trace(go.Scatter(x=[v[0] for v in xy],y=[v[1] for v in xy],mode='lines',
                                line=dict(color=color,width=width),showlegend=False,hoverinfo='skip'))
    segment(['A_SX','B_SX','B_DX','A_DX'],'#3976c4',5)
    segment(['B_SX','B_DX'],'#df8628',6)
    segment(['M','Q','T'],'#138777',4)
    radius=p.physical.q_joint_diameter/2
    if motor_axis_diameter>0:
        m=points['M'];r=motor_axis_diameter/2
        fig.add_shape(type='circle',x0=m[0]-r,x1=m[0]+r,y0=m[1]-r,y1=m[1]+r,line=dict(color='#138777',dash='dash'))
    for name in ('B_SX','B_DX','Q'):
        point=points[name]
        if point is not None:
            fig.add_shape(type='circle',x0=point[0]-radius,x1=point[0]+radius,y0=point[1]-radius,y1=point[1]+radius,
                          line=dict(color='#138777' if name=='Q' else '#df8628',dash='dash'))
    for name,point in points.items():
        if point is None:continue
        fig.add_trace(go.Scatter(x=[point[0]],y=[point[1]],mode='markers+text',
            text=[name.replace('_',' ')],textposition='top center',showlegend=False,
            marker=dict(size=10,color='#138777' if name in ('M','Q','T') else '#243548'),
            hovertemplate=f'{name.replace("_"," ")} · X %{{x:.3f}} / Y %{{y:.3f}} mm da A SX<extra></extra>'))
    mx,my=points['M'];tx,ty=points['T'];bx,by=points['B_SX']
    for x,y in ((mx,my),(tx,ty)):
        fig.add_shape(type='line',x0=x,x1=x,y0=0,y1=y,line=dict(color='#94a3b8',dash='dot'))
        fig.add_shape(type='line',x0=0,x1=x,y0=y,y1=y,line=dict(color='#94a3b8',dash='dot'))
    fig.add_annotation(x=(bx+tx)/2,y=by,text=f'B SX → T = {p.actuation_fraction*p.tie_length:g} mm',
                       showarrow=False,yshift=25,font=dict(color='#a45c18'))
    fig.add_annotation(x=mx,y=my,text=f'M ({mx:g}, {my:g}) mm',showarrow=True,ax=60,ay=40,
                       font=dict(color='#138777'))
    fig.update_xaxes(title_text='X da A SX · mm',dtick=10,zeroline=True,zerolinecolor='#94a3b8')
    fig.update_yaxes(title_text='Y da A SX · mm · retro ↓',dtick=10,autorange='reversed',
                     scaleanchor='x',scaleratio=1,zeroline=True,zerolinecolor='#94a3b8')
    fig.update_layout(template='plotly_white',height=430,margin=dict(l=30,r=30,t=40,b=30),
                      title='Quote di montaggio · ruote dritte',hovermode='closest')
    return fig
