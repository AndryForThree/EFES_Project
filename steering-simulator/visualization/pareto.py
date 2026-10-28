"""Interactive Pareto plot and response overlays on a common work interval."""
import math
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from steering.motor_search import MotorCandidate

COLORS = ('#3976c4', '#df8628', '#138777')


def pareto_plot(candidates: list[MotorCandidate], selected_id: int, color_metric: str,
                include_dominated: bool = True) -> go.Figure:
    color_values = {
        'motor_excursion': (lambda c: math.degrees(c.metrics.motor_excursion), 'Corsa albero richiesta · °'),
        'steering_margin': (lambda c: math.degrees(c.metrics.steering_margin), 'Margine di sterzata · °'),
    }
    value, label = color_values[color_metric]
    fig = go.Figure()
    fronts = sorted((c for c in candidates if c.pareto), key=lambda c: c.metrics.max_sensitivity)
    fig.add_trace(go.Scatter(x=[c.metrics.max_sensitivity for c in fronts],
                            y=[100*c.metrics.variation for c in fronts], mode='lines',
                            line=dict(color='#8296a7', width=1, dash='dot'), hoverinfo='skip', showlegend=False))
    for is_front, name in ((False, 'Altre soluzioni ammissibili'), (True, 'Fronte di Pareto')):
        points = [c for c in candidates if c.pareto == is_front]
        if not points or (not is_front and not include_dominated):
            continue
        fig.add_trace(go.Scatter(
            x=[c.metrics.max_sensitivity for c in points], y=[100*c.metrics.variation for c in points],
            customdata=[[c.id, c.parameters.motor.crank_radius, c.parameters.motor.connecting_length,
                         c.parameters.motor.x, c.parameters.motor.y] for c in points],
            mode='markers', name=name,
            marker=dict(size=12 if is_front else 8, symbol='diamond' if is_front else 'circle',
                        opacity=1 if is_front else .4, color=[value(c) for c in points], coloraxis='coloraxis'),
            hovertemplate='C%{customdata[0]} · leva %{customdata[1]} / astina %{customdata[2]} mm'
                          '<br>M (%{customdata[3]:.1f}, %{customdata[4]:.1f}) mm'
                          '<br>S massima: %{x:.4f} °/°<br>Variazione: %{y:.1f}%<extra></extra>'))
    selected = next((c for c in candidates if c.id == selected_id), None)
    if selected:
        fig.add_trace(go.Scatter(x=[selected.metrics.max_sensitivity], y=[100*selected.metrics.variation],
                                customdata=[[selected.id]], mode='markers', name='Selezionata',
                                marker=dict(size=20, symbol='circle-open', color='#243548', line=dict(width=2)),
                                hovertemplate=f'C{selected.id} selezionata<extra></extra>'))
    fig.update_layout(template='plotly_white', height=460, margin=dict(l=20,r=20,t=15,b=25),
                      xaxis_title='Sensibilità massima |dm/dφ| · °/° → più bassa è meglio',
                      yaxis_title='Variazione relativa della sensibilità · % → più bassa è meglio',
                      coloraxis=dict(colorscale='Viridis', colorbar=dict(title=label)),
                      legend=dict(orientation='h', y=1.08), clickmode='event+select', dragmode='select',
                      selectionrevision='pareto')
    return fig


def comparison_plot(curves: list[tuple[int, list[dict]]], absolute: bool = True) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, subplot_titles=('Motore → sterzata media', 'Sensibilità sulla stessa corsa di sterzo'))
    for (candidate_id, rows), color in zip(curves, COLORS):
        ordered = sorted(rows, key=lambda r: r['motor_deg'])
        fig.add_trace(go.Scatter(x=[r['motor_deg'] for r in ordered], y=[r['steering_mean_deg'] for r in ordered],
                                name=f'C{candidate_id}', legendgroup=str(candidate_id),
                                mode='lines', line=dict(color=color, width=2)), row=1,col=1)
        fig.add_trace(go.Scatter(x=[r['steering_mean_deg'] for r in rows],
                                y=[abs(r['sensitivity_deg_per_deg']) if absolute else r['sensitivity_deg_per_deg'] for r in rows],
                                name=f'C{candidate_id}', legendgroup=str(candidate_id), showlegend=False,
                                mode='lines', line=dict(color=color,width=2)), row=1,col=2)
    fig.update_xaxes(title_text='Angolo albero dal centro · °',row=1,col=1)
    fig.update_yaxes(title_text='Sterzata media · °',row=1,col=1)
    fig.update_xaxes(title_text='Sterzata media · °',row=1,col=2)
    fig.update_yaxes(title_text='|dm/dφ| · °/°' if absolute else 'dm/dφ · °/°',row=1,col=2)
    fig.update_layout(template='plotly_white',height=410,margin=dict(l=20,r=20,t=45,b=20),
                      legend=dict(orientation='h',y=1.15),hovermode='closest')
    return fig
