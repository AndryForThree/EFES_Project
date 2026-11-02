"""Self-contained, printable HTML report using existing results only."""
from datetime import datetime
from html import escape
import json
import math
from zoneinfo import ZoneInfo
import numpy as np
from plotly.offline import get_plotlyjs
from steering.kinematics import solve,select_pose
from steering.motor import at_steering
from steering.geometry import strip
from steering.reference import chassis_pose,chassis_point
from steering.optimization import evaluate
from steering.motor_filters import filter_candidates,filters_from_settings
from steering.motor_axis import axis_pareto
from steering.quadrilateral_filters import filter_candidates as filter_geometries,filters_from_settings as geometry_filters
from .shapes import bodies
from .mounting import mounting_rows


def _table(rows):
    return '<table>'+''.join('<tr><th>'+escape(str(a))+'</th><td>'+escape(str(b))+'</td></tr>' for a,b in rows)+'</table>'


def geometry_svg(p,angle,motor_axis_diameter=0.):
    pose=select_pose(solve(p,angle if angle is not None else 0.),p.branch)
    if pose is None:pose=select_pose(solve(p,0.),p.branch)
    view=chassis_pose(p,pose)
    colors={'arm':('#3976c4','#d8e7f5'),'bracket':('#3976c4','#eaf1f8'),
            'rod':('#c78228','#f3d9b7'),'wheel':('#243548','#33475c'),'joint':('#71869b','#fff')}
    polygons=[(b.polygon,*colors[b.family]) for b in bodies(p,view)]
    mean=(pose.theta_left+pose.theta_right)/2
    motor=at_steering(p,mean)
    q=None
    if motor:
        m=chassis_point(p,[p.motor.x,p.motor.y]);q=chassis_point(p,motor.pin)
        polygons.extend([(strip(m,q,p.physical.link_width,p.physical.link_width/2),'#138777','#c8e6df'),
                         (strip(q,view.point,p.physical.link_width,p.physical.link_width/2),'#138777','#e5f3ef')])
    points=np.vstack([shape for shape,_,_ in polygons])
    for b in (view.b_left,view.b_right):
        points=np.vstack([points,b-p.physical.q_joint_diameter/2,b+p.physical.q_joint_diameter/2])
    if q is not None:points=np.vstack([points,q-p.physical.q_joint_diameter/2,q+p.physical.q_joint_diameter/2])
    shaft=chassis_point(p,[p.motor.x,p.motor.y]);r=motor_axis_diameter/2
    if r>0:points=np.vstack([points,shaft-r,shaft+r])
    lo=points.min(axis=0);hi=points.max(axis=0)
    pad=max(14.,(hi[0]-lo[0])*.07);lo-=pad;hi+=pad
    w,h=hi-lo;font=max(3.,w/75)
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{lo[0]} {lo[1]} {w} {h}" role="img" aria-label="Geometria dello sterzo, origine A SX">']
    for x in np.arange(math.ceil(lo[0]/10)*10,hi[0],10):
        out.append(f'<path d="M{x},{lo[1]}V{hi[1]}" stroke="#edf1f5" stroke-width=".25"/>')
    for y in np.arange(math.ceil(lo[1]/10)*10,hi[1],10):
        out.append(f'<path d="M{lo[0]},{y}H{hi[0]}" stroke="#edf1f5" stroke-width=".25"/>')
    out.append(f'<path d="M0,{lo[1]}V{hi[1]}M{lo[0]},0H{hi[0]}" stroke="#9cafc0" stroke-width=".5"/>')
    for shape,stroke,fill in polygons:
        xy=' '.join(f'{x:.6g},{y:.6g}' for x,y in shape)
        out.append(f'<polygon points="{xy}" stroke="{stroke}" fill="{fill}" stroke-width=".5"/>')
    if r>0:out.append(f'<circle cx="{shaft[0]}" cy="{shaft[1]}" r="{r}" stroke="#138777" fill="none" stroke-dasharray="2 1" stroke-width=".6"/>')
    for b in (view.b_left,view.b_right):
        out.append(f'<circle cx="{b[0]}" cy="{b[1]}" r="{p.physical.q_joint_diameter/2}" stroke="#c78228" fill="none" stroke-dasharray="2 1" stroke-width=".6"/>')
    if q is not None:out.append(f'<circle cx="{q[0]}" cy="{q[1]}" r="{p.physical.q_joint_diameter/2}" stroke="#138777" fill="none" stroke-dasharray="2 1" stroke-width=".6"/>')
    for name,point in [('A SX · O (0,0)',view.a_left),('A DX',view.a_right),('T',view.point)]:
        out.append(f'<circle cx="{point[0]}" cy="{point[1]}" r="1.5" fill="#243548"/>')
        out.append(f'<text x="{point[0]}" y="{point[1]-font*1.4}" font-size="{font}" text-anchor="middle" fill="#243548">{escape(name)}</text>')
    out.append('</svg>')
    return ''.join(out),mean


def report_html(project):
    p=project.parameters
    axis_diameter=project.settings.get('motor_filter_axis_diameter',0.)
    svg,mean=geometry_svg(p,project.simulation.get('angle',0.),axis_diameter)
    try:date=datetime.fromisoformat(project.saved_at).astimezone(ZoneInfo('Europe/Rome')).strftime('%d/%m/%Y %H:%M')
    except (ValueError,TypeError):date=str(project.saved_at)
    capacity=evaluate(p)
    rows=[('Origine e assi','A SX = (0,0); X destra, Y retro; tutte le lunghezze in mm'),
          ('Interasse perni A',f'{p.pivot_spacing:g} mm'),('Bracci',f'{p.left.arm_length:g} mm'),
          ('Tirante',f'{p.tie_length:g} mm'),('Inclinazione',f'{math.degrees(p.left.arm_angle-math.pi/2):.3f}°'),
          ('Offset ruota SX',f'({p.left.axle_x:g}, {p.left.axle_y:g}) mm; DX speculare'),
          ('Ruote',f'Ø{p.physical.wheel_diameter:g} × {p.physical.wheel_width:g} mm'),
          ('Larghezza braccetti',f'{p.physical.link_width:g} mm'),('Ingombro giunti B/Q',f'Ø{p.physical.q_joint_diameter:g} mm'),
          ('Asse motore M',f'({p.motor.x+p.pivot_spacing/2:g}, {p.motor.y:g}) mm'),
          ('Leva / astina',f'{p.motor.crank_radius:g} / {p.motor.connecting_length:g} mm'),
          ('Attacco sul tirante / montaggio',f'{p.actuation_fraction*p.tie_length:g} mm da B SX · '+('A' if p.motor.assembly==1 else 'B')),
          ('Sterzata massima del quadrilatero',f'±{math.degrees(capacity.steering_limit):.2f}° medi'),
          ('Posa rappresentata',f'{math.degrees(mean):+.2f}° medi')]
    sections=[f'<section><h2>Configurazione attuale</h2>{svg}{_table(rows)}'
              '<h3>Quote di montaggio a ruote dritte</h3>'+_table(mounting_rows(p))+'</section>']
    quad=project.results.get('quadrilateral_search_result')
    if quad:
        selected=project.settings.get('quad_selected')
        comparison=set([selected,*project.settings.get('quad_compare',[])])
        qfilters=geometry_filters(project.settings)
        filtered=filter_geometries(quad,qfilters)
        chosen=[c for c in filtered if c.id in comparison]
        sections.append('<section><h2>Ricerca del quadrilatero</h2>'+_table([
            ('Corsa di confronto',f'±{math.degrees(quad.target):g}°'),('Passo virtuale',f'{quad.wheelbase:g} mm'),
            ('Candidati',f'{quad.tested} combinazioni; {len(quad.candidates)} ammissibili; {sum(c.pareto for c in quad.candidates)} Pareto originali'),
            ('Dopo i filtri',f'{len(filtered)} geometrie; {sum(c.pareto for c in filtered)} Pareto'),
            ('Interassi A inclusi',str(qfilters.spacings) if qfilters.spacings is not None else 'Tutti'),
            ('Bracci inclusi',str(qfilters.lengths) if qfilters.lengths is not None else 'Tutti'),
            ('Tiranti inclusi',str(qfilters.ties) if qfilters.ties is not None else 'Tutti')])+
            ''.join('<h3>Q'+str(c.id)+'</h3>'+_table([
                ('Interasse / braccio / tirante',f'{c.parameters.pivot_spacing:g} / {c.parameters.left.arm_length:g} / {c.parameters.tie_length:g} mm'),
                ('Errore Ackermann massimo',f'{math.degrees(c.ackermann_error):.4f}°'),
                ('Sterzata massima',f'±{math.degrees(c.evaluation.steering_limit):.2f}°'),
                ('Movimento minimo T',f'{c.min_point_motion:.5f} mm/°')]) for c in chosen)+
            '<p class="note">Gli obiettivi sono errore Ackermann minimo, escursione massima e movimento minimo di T massimo. '
            'Gli errori riguardano la stessa corsa richiesta, non tutta l’escursione aggiuntiva. '
            'Le ricerche salvate sono istantanee separate dalla configurazione attuale.</p></section>')
    motor=project.results.get('motor_search_result')
    if motor:
        selected=project.settings.get('motor_search_selected_id')
        comparison=set([selected,*project.settings.get('motor_compare',[])])
        filters=filters_from_settings(project.settings)
        fixed=filter_candidates(motor,filters)
        filtered=axis_pareto(fixed,axis_diameter,dict(project.results.get('motor_axis_cache',{})))
        chosen=[c for c in filtered if c.id in comparison]
        sections.append('<section><h2>Ricerca del collegamento motore</h2>'+_table([
            ('Geometria base: interasse / braccio / tirante',f'{motor.base.pivot_spacing:g} / {motor.base.left.arm_length:g} / {motor.base.tie_length:g} mm'),
            ('Corsa verificata',f'±{math.degrees(motor.space.target):g}°'),
            ('Candidati',f'{motor.tested} teorici; {motor.detailed_tested} analizzati; {len(motor.feasible)} ammissibili; {sum(c.pareto for c in motor.feasible)} Pareto originali'),
            ('Pareto dopo i filtri',f'{sum(c.pareto for c in filtered)} soluzioni'),
            ('Ingombro asse M',f'Ø{axis_diameter:g} mm; leva M–Q esclusa'),
            ('Leve / astine incluse',f'{filters.crank_lengths if filters.crank_lengths is not None else "Tutte"} / {filters.rod_lengths if filters.rod_lengths is not None else "Tutte"} mm'),
            ('Montaggi inclusi',', '.join('A' if v==1 else 'B' for v in filters.assemblies) or 'Nessuno'),
            ('Zona filtro motore da A SX',f'X: {filters.x_bounds or "intera ricerca"}; Y: {filters.y_bounds or "intera ricerca"} mm'),
            ('Leva sempre dietro al tirante mobile','Attivo' if filters.rear_only else 'Disattivo')])+
            ''.join('<h3>C'+str(c.id)+'</h3>'+_table([
                ('Asse M',f'({c.parameters.motor.x+c.parameters.pivot_spacing/2:g}, {c.parameters.motor.y:g}) mm'),
                *mounting_rows(c.parameters),
                ('Leva / astina',f'{c.parameters.motor.crank_radius:g} / {c.parameters.motor.connecting_length:g} mm'),
                ('Distanza minima leva dietro al tirante mobile',f'{c.rear_clearance:.3f} mm' if c.rear_clearance is not None else 'Non calcolata'),
                ('Sensibilità massima',f'{c.metrics.max_sensitivity:.5f} °/°'),
                ('Variazione relativa',f'{100*c.metrics.variation:.2f}%'),
                ('Corsa albero',f'{math.degrees(c.metrics.motor_excursion):.2f}°')]) for c in chosen)+
            '<p class="note">Sensibilità = variazione dell’angolo medio delle ruote / variazione dell’angolo motore. '
            'Il filtro delle interferenze è 2D e campionato: leva/astina contro ruote, bracci e staffe; '
            'il disco di Q anche contro il tirante; B SX e B DX contro leva, astina e Q. '
            'Il collegamento T=B è ammesso solo nella zona del giunto e dei terminali. Il vincolo posteriore usa il bordo e la normale del tirante in ciascuna posa campionata, '
            'includendo tutto l’ingombro della leva. Una distanza positiva soddisfa il vincolo. '
            'Il disco dell’asse M viene verificato, quando attivo, contro parti dello sterzo, B/Q e astina; '
            'i candidati dominati non verificati restano nell’insieme originale, senza essere dichiarati validi. '
            'Leva M–Q collegata all’asse e quote verticali sono escluse.</p></section>')
    charts=[]
    for record in project.figures.values():
        html='<section><h2>'+escape(str(record['caption']))+'</h2>'
        for name,fig in record['charts'].items():
            index=len(charts);charts.append(json.loads(fig.to_json()))
            html+=f'<h3>{escape(str(name))}</h3><div class="chart" id="chart-{index}"></div><img class="print-chart" id="print-{index}" alt="{escape(str(name),quote=True)}"/>'
        sections.append(html+'</section>')
    specs=json.dumps(charts,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    notes='<p class="notes">'+escape(project.notes)+'</p>' if project.notes else ''
    return '''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+escape(project.name)+''' · Steering Lab</title><style>
*{box-sizing:border-box}body{font:15px/1.55 Arial,sans-serif;color:#243548;margin:0;background:#f3f5f8}main{max-width:1100px;margin:30px auto;background:white;padding:40px;border:1px solid #dfe6ed;border-radius:10px}
h1{font-size:30px;margin:0 0 6px}h2{font-size:21px;border-bottom:1px solid #dfe6ed;padding-bottom:8px;margin-top:30px}h3{font-size:16px}section{margin:24px 0}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid #e5eaf0}th{width:45%;font-weight:500;color:#516478}.note,.meta{color:#64748b;font-size:13px}.notes{white-space:pre-wrap}svg{width:100%;max-height:420px;background:#fafcfd;border:1px solid #e5eaf0;border-radius:8px}.chart{height:440px}.print-chart{display:none;width:100%}button{background:#138777;color:white;border:0;border-radius:6px;padding:11px 18px;font:inherit;cursor:pointer}.actions{margin:20px 0}
@page{size:A4;margin:14mm}@media print{body{background:white}main{border:0;margin:0;padding:0;max-width:none}.actions{display:none}h2,h3{break-after:avoid}tr,svg,.print-chart{break-inside:avoid}.chart{display:none}.print-chart{display:block}.meta{font-size:10px}section{margin:18px 0}}
</style><main><h1>'''+escape(project.name)+'''</h1><p class="meta">Steering Lab · '''+escape(date)+''' · modello '''+escape(project.model_version)+''' · origine A SX</p>'''+notes+'''
<div class="actions"><button id="print-button">Stampa / Salva PDF</button><p class="note" id="print-status">Report autonomo: grafici interattivi disponibili anche senza internet.</p></div>'''+''.join(sections)+'''
<section><h2>Ipotesi del modello</h2><p>Modello cinematico planare, componenti rigidi, staffe simmetriche e ruote dritte a zero. Non comprende giochi, deformazioni, attrito, forze, coppie o dinamica del veicolo. Il passo posteriore è virtuale. I massimi/minimi campionati non sono certificazioni continue della corsa. Il report include soltanto i risultati disponibili, senza eseguire nuove ottimizzazioni.</p></section></main>
<script>'''+get_plotlyjs()+'''</script><script>
const specs='''+specs+''';const ready=Promise.all(specs.map((s,i)=>Plotly.newPlot('chart-'+i,s.data,{...s.layout,height:440,autosize:true},{responsive:true,displaylogo:false}).catch(()=>null))); 
async function prepareImages(){await ready;for(let i=0;i<specs.length;i++){try{document.getElementById('print-'+i).src=await Plotly.toImage('chart-'+i,{format:'png',width:1200,height:650});}catch(e){document.getElementById('print-'+i).alt='Grafico disponibile nella versione interattiva HTML';}}}
const prepared=prepareImages();document.getElementById('print-button').onclick=async()=>{const b=document.getElementById('print-button');b.disabled=true;document.getElementById('print-status').textContent='Preparazione della stampa…';await prepared;await Promise.all([...document.querySelectorAll('.print-chart')].map(i=>i.decode().catch(()=>{})));window.print();b.disabled=false;document.getElementById('print-status').textContent='Report pronto.';};
</script></html>'''
