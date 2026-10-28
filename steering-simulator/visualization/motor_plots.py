"""Motor-to-mean-steering response, computed only on request."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def motor_plots(rows: list[dict], current: float = 0.0) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Angolo medio delle ruote", "Sensibilità sterzo / motore"))
    x = [row['motor_deg'] for row in rows]
    for col, key, label, color in ((1,'steering_mean_deg','Sterzata media','#3976c4'),
                                    (2,'sensitivity_deg_per_deg','dm/dφ','#138777')):
        fig.add_trace(go.Scatter(x=x,y=[row[key] for row in rows],name=label,mode='lines',
                                 connectgaps=False,line=dict(color=color,width=2)),row=1,col=col)
        fig.add_vline(x=current,line_color='#8ea0b0',line_dash='dot',row=1,col=col)
        fig.update_xaxes(title_text='Albero motore rispetto al centro · °',row=1,col=col)
    fig.update_yaxes(title_text='Sterzata media · °',row=1,col=1)
    fig.update_yaxes(title_text='° sterzata / ° motore',row=1,col=2)
    fig.update_layout(height=400,template='plotly_white',margin=dict(l=20,r=20,t=45,b=20),showlegend=False)
    return fig
