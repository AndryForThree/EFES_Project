"""Local Streamlit interface. All mechanics live in steering/, not in widgets."""
from __future__ import annotations

from dataclasses import replace
import math
import hashlib

import numpy as np
import streamlit as st

from steering.kinematics import select_pose, solve, sweep, steering_input, steering_limit
from steering.optimization import evaluate
from steering.parameters import (Parameters, Motor, from_json, to_json,
                                 steering_from_lengths, modular_defaults, on_modular_grid, validate_symmetric_setup)
from steering.singularities import diagnose
from steering.motor import build_range, at_steering, response, response_csv
from steering.motor_search import on_chassis_grid
from visualization.plots import response_plots
from visualization.motor_plots import motor_plots
from visualization.motor_optimizer import render_motor_optimizer
from visualization.physical_config import render_physical_config
from visualization.quadrilateral_optimizer import render_quadrilateral_optimizer
from visualization.browser_motion import browser_motion
from visualization.top_view import top_view
from visualization.project_controls import render_project_toolbar,restore_project,remember_figures


st.set_page_config(page_title="Steering Lab · Simulatore parametrico", page_icon="⚙️", layout="wide")
st.markdown("""<style>
.block-container{padding-top:2rem;padding-bottom:3rem;max-width:1600px}
[data-testid="stMetric"]{background:#f2f5f8;border:1px solid #e4eaf0;border-radius:10px;padding:14px 18px}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums;font-size:1.65rem}
h1{letter-spacing:-.04em} h2,h3{letter-spacing:-.025em}
.eyebrow{font-size:11px;font-weight:650;letter-spacing:.18em;color:#138777;margin-bottom:8px}
.subtitle{font-size:15px;color:#718096;line-height:1.6;margin-bottom:25px}
.legend{font-size:12px;color:#718096;margin:0 0 18px}.legend span{margin-right:20px}
</style>""", unsafe_allow_html=True)

if "configuration" not in st.session_state:
    st.session_state.configuration = modular_defaults()
    st.session_state.revision = 0
elif (not hasattr(st.session_state.configuration.physical, "link_width")
      or not hasattr(st.session_state.configuration.physical, "q_joint_diameter")):
    # Preserve an open session across the addition of persisted 2D widths.
    st.session_state.configuration = from_json(to_json(st.session_state.configuration))
    st.session_state.revision += 1


def install_configuration(p) -> None:
    validate_symmetric_setup(p)
    st.session_state.configuration = p
    st.session_state.revision += 1


@st.cache_data(show_spinner=False, max_entries=12)
def sampled(p: Parameters):
    limit, _ = steering_limit(p)
    return sweep(p, steering_input(p, -limit), steering_input(p, limit), 181)


@st.cache_data(show_spinner=False, max_entries=16)
def motor_model(p: Parameters):
    return build_range(p)


def sidebar() -> Parameters:
    original = st.session_state.configuration
    revision = st.session_state.revision

    def number(label: str, value: float, key: str, minimum: float | None = None,
               maximum: float | None = None, step: float = 1.0, help: str | None = None) -> float:
        # A validated imported design may lie outside the initial convenient UI range.
        minimum = min(minimum, float(value)) if minimum is not None else None
        maximum = max(maximum, float(value)) if maximum is not None else None
        return float(st.number_input(label, min_value=minimum, max_value=maximum, value=float(value), step=step,
                                     key=f"p{revision}_{key}", help=help))

    def angle(label: str, value: float, key: str, minimum=-180.0, maximum=180.0) -> float:
        display_value = math.remainder(value, math.tau) if minimum < 0 else value
        return math.radians(number(label, math.degrees(display_value), key, minimum, maximum))

    with st.sidebar:
        st.markdown("<div class='eyebrow'>SBW–01 / DESIGN WORKSPACE</div>", unsafe_allow_html=True)
        st.title("Parametri")
        st.caption("Lunghezze in mm · angoli in gradi")
        spacing = number("Interasse perni A", original.pivot_spacing, "pivot_spacing", .1, 3000.0, 10.,
                         "Distanza fra i perni fissi: multipli di 10 mm per la griglia del telaio.")
        length = number("Lunghezza Braccio", original.left.arm_length, "arm_length", .1, 500.0, 10.,
                        "Distanza fra perno fisso e foro del tirante, uguale per entrambi i bracci.")
        tie = number("Lunghezza Tirante", original.tie_length, "tie", .1, 3000.0, 10.,
                     "Distanza fra i centri dei due fori del tirante.")
        st.caption("L’inclinazione è ricavata dalle tre lunghezze. Staffe simmetriche e ruote dritte a zero. "
                   "Ricerca modulare nella scheda Ricerca quadrilatero.")
        with st.expander("01 / Staffe e ruote", expanded=True):
            x, y = st.columns(2)
            with x:
                axle_x = number("Offset X ruota SX", original.left.axle_x, "SXcx", -500.0, 500.0, .5)
            with y:
                axle_y = number("Offset Y ruota SX", original.left.axle_y, "SXcy", -500.0, 500.0, .5)
            st.caption("Gli offset della ruota DX vengono specchiati automaticamente.")
            st.caption("Dimensioni di ruote e braccetti nella scheda Ingombri 2D.")

        with st.expander("02 / Motore · leva e astina", expanded=True):
            st.caption("Posizione M dell’albero in uscita dal riduttore. X verso destra, Y verso il retro.")
            x, y = st.columns(2)
            with x:
                motor_x = number("Posizione motore X", original.motor.x+original.pivot_spacing/2, "motor_x_asx", -2000.0, 2000.0, 10.)
            with y:
                motor_y = number("Posizione motore Y", original.motor.y, "motor_y", -2000.0, 2000.0, 10.)
            st.caption("Origine delle coordinate: A SX = (0, 0).")
            if not on_chassis_grid(replace(original,pivot_spacing=spacing),motor_x-spacing/2,motor_y):
                st.warning("Posizione manuale fuori dalla griglia telaio 10 mm. La ricerca motore genera solo posizioni sulla griglia.")
            crank = number("Lunghezza leva motore M–Q", original.motor.crank_radius, "crank", .1, 500.0, .5)
            connecting = number("Lunghezza astina Q–T", original.motor.connecting_length, "connecting", .1, 2000.0, .5)
            attachment = number("Foro T da B SX · mm", min(original.actuation_fraction*original.tie_length,tie),
                                "attachment_mm", 0.0, tie, 10.,
                                "Distanza dal centro del perno B SX al centro del foro T, misurata lungo il tirante. Non è una coordinata del telaio.")
            fraction = attachment/tie
            if not math.isclose(attachment/10,round(attachment/10),abs_tol=1e-9):
                st.warning("Foro T fuori passo 10 mm sul tirante. La ricerca usa solo i fori modulari indicati.")
            st.caption(f"Foro T: {attachment:g} mm da B SX · {tie-attachment:g} mm da B DX. "
                       "L’asse motore mantiene le proprie coordinate sul telaio.")
            assembly = st.selectbox("Montaggio della leva a ruote dritte", [1, -1],
                                   index=0 if original.motor.assembly == 1 else 1,
                                   format_func=lambda value: "A" if value == 1 else "B", key=f"p{revision}_motor_assembly",
                                   help="Le due possibili posizioni del giunto Q: osserva il disegno e scegli il montaggio.")
            st.caption("0° motore corrisponde alle ruote dritte. Il montaggio scelto rimane fisso durante il movimento.")
        with st.expander("03 / Esplorazione del movimento"):
            display_range = angle("Intervallo slider · ±°", original.display_range, "range", 1.0, 90.0)
        template = replace(original, left=replace(original.left, axle_x=axle_x, axle_y=axle_y),
                           display_range=display_range,
                           actuation_fraction=fraction, motor=Motor(motor_x-spacing/2, motor_y, crank, connecting, assembly))
        try:
            p = steering_from_lengths(template, spacing, length, tie)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        st.caption(f"Inclinazione calcolata: **{math.degrees(p.left.arm_angle-math.pi/2):.2f}°** "
                   "(0° verso il retro; positiva verso l’esterno).")
        if not all(on_modular_grid(v) for v in (spacing,length,tie)):
            st.warning("Quote manuali fuori passo 10 mm. La geometria è visualizzata senza arrotondamenti; "
                       "la ricerca del quadrilatero usa solo misure modulari.")
        if st.button("Ripristina dimensioni iniziali", use_container_width=True):
            install_configuration(modular_defaults())
            st.rerun()
        st.caption("Usa Salva nella barra in alto per conservare il progetto completo.")
        with st.expander('Guida rapida'):
            st.markdown("Origine **A SX = (0,0)**; X verso destra, Y verso il retro. "
                        "Lo slider comanda l’angolo medio delle ruote. "
                        "Scegli prima il quadrilatero, poi il collegamento motore. "
                        "Modello cinematico 2D: niente giochi, forze o dinamica. "
                        "Metti in pausa prima di salvare la posa.")
    return p


if 'pending_project' in st.session_state:
    restore_project(st.session_state,st.session_state.pop('pending_project'))
render_project_toolbar()
p = sidebar()
try:
    p.validate()
except ValueError as exc:
    st.error(f"Parametri non validi: {exc}")
    st.stop()
st.session_state.configuration = p
signature = hashlib.sha256(("crank-motor-v1:"+to_json(p)+str(st.session_state.revision)).encode()).hexdigest()
if st.session_state.get("motion_signature") != signature:
    st.session_state.motion_signature = signature
    if not st.session_state.pop('project_restoring',False):
        st.session_state.snapshot_angle = 0.0
        st.session_state.snapshot_steering = 0.0
        st.session_state.snapshot_motor = 0.0
        st.session_state.simulation_state={}
        for result_key in ("technical_result", "motor_results"):
            st.session_state.pop(result_key, None)
        for section in ('technical','motor_analysis'):
            st.session_state.get('project_figures',{}).pop(section,None)

simulation, design, optimizer_tab, dimensions_tab, analysis_tab = st.tabs([
    "Simulazione", "Ricerca quadrilatero", "Ottimizzazione motore", "Ingombri 2D", "Analisi"])

with dimensions_tab:
    render_physical_config(p, install_configuration)

motor_interval = motor_model(p)

with simulation:
    capacity = evaluate(p)
    st.subheader("Corsa della geometria")
    columns = st.columns(3)
    maximum = math.degrees(capacity.steering_limit)
    columns[0].metric("Sterzata massima a sinistra", f"−{maximum:.2f}°")
    columns[1].metric("Sterzata massima a destra", f"+{maximum:.2f}°")
    columns[2].metric("Limite", "Primo punto morto" if capacity.at_deadpoint else "90° raggiunti")
    st.caption("Angoli riferiti alla media delle due ruote. Calcolo geometrico indipendente dall’intervallo dello slider. "
               "Il punto morto è la fine della corsa, non una posizione da attraversare.")
    if capacity.geometrically_valid:
        st.caption(f"Al limite verso destra: ruota SX {math.degrees(capacity.left_positive):.2f}°, "
                   f"ruota DX {math.degrees(capacity.right_positive):.2f}°. Verso sinistra gli angoli si scambiano e cambiano segno.")
    if motor_interval.valid:
        st.markdown("**Con il collegamento motore impostato**")
        motor_cols = st.columns(3)
        motor_cols[0].metric("Sterzata media disponibile", f"{math.degrees(motor_interval.mean_lower):.1f}° / +{math.degrees(motor_interval.mean_upper):.1f}°")
        motor_cols[1].metric("Corsa albero dal centro", f"{math.degrees(motor_interval.phi_lower):.1f}° / +{math.degrees(motor_interval.phi_upper):.1f}°")
        neutral_motor = at_steering(p, 0.0)
        motor_cols[2].metric("Sensibilità al centro · °/°", f"{neutral_motor.sensitivity:.3f}" if neutral_motor.sensitivity is not None else "—")
        st.caption("M = asse motore · Q = estremità della leva · T = attacco sul tirante. "
                   "Il comando Motore muove l’albero; Sterzata libera permette di esplorare il solo sterzo. "
                   "La corsa motore può essere diversa nei due versi.")
    else:
        st.error(motor_interval.reason)
        st.caption("Comando motore disabilitato. Correggi posizione o lunghezze; il solo sterzo rimane ispezionabile con Sterzata libera.")
    with st.expander('Quote di montaggio · ruote dritte'):
        from visualization.mounting import mounting_rows
        st.dataframe([{'Quota':name,'Valore':value} for name,value in mounting_rows(p)],
                     hide_index=True,use_container_width=True)
        st.caption('Foro T misurato lungo il tirante da B SX. Coordinate X/Y riferite ad A SX. '
                   'Le coordinate di T e Q e l’orientamento della leva valgono a ruote dritte.')
    snapshot = browser_motion(p, signature, motor_interval,initial_state=st.session_state.get('simulation_state',{}),
                              motor_axis_diameter=st.session_state.get('motor_filter_axis_diameter',0.))
    if snapshot and snapshot.get("signature") == signature:
        angle = snapshot.get("angle")
        steering = snapshot.get("steering_angle")
        if angle is None or (isinstance(angle, (int, float)) and math.isfinite(angle)
                             and isinstance(steering, (int, float)) and math.isfinite(steering)
                             and abs(steering) <= math.pi/2+1e-9):
            st.session_state.snapshot_angle = angle
            st.session_state.snapshot_steering = steering
            st.session_state.snapshot_motor = snapshot.get("motor_angle")
            st.session_state.simulation_state={k:snapshot.get(k) for k in ("mode","speed","angle","steering_angle","motor_angle")}

with analysis_tab:
    with st.expander('Curve motore',expanded=True):
        st.subheader("Dal motore alle ruote")
        st.write("La curva mostra la sterzata media delle ruote in funzione dell’angolo dell’albero in uscita dal riduttore. "
                 "La sensibilità dm/dφ indica quanti gradi di sterzata ottieni localmente per 1° di albero. Un segno negativo indica inversione del verso.")
        st.caption("0° albero = ruote dritte. Curve della configurazione attuale. La ricerca automatica è nella scheda Ottimizzazione motore.")
        if st.button("Calcola curve motore", type="primary", disabled=not motor_interval.valid):
            progress = st.progress(0, text="Soluzione dei vincoli motore–sterzo…")
            with st.spinner("Calcolo della risposta del collegamento…"):
                rows = response(p, motor_interval)
                progress.progress(80, text="Preparazione delle curve di posizione e sensibilità…")
                current_phi = st.session_state.snapshot_motor
                figure = motor_plots(rows, math.degrees(current_phi) if current_phi is not None else 0.0)
                st.session_state.motor_results = {"figure":figure, "rows":rows}
                progress.progress(100, text="Curve pronte")
            progress.empty()
        if "motor_results" in st.session_state:
            result = st.session_state.motor_results
            st.plotly_chart(result["figure"], use_container_width=True, config={"displaylogo":False}, key="motor_response")
            st.download_button("Curva motore CSV", response_csv(result["rows"]), "motor-steering-response.csv", "text/csv")
            st.caption("CSV: angolo motore, sterzata media, angoli delle due ruote e sensibilità in °/°. "
                       "I valori non definiti vicino a una singolarità restano vuoti. Curve ferme fino al prossimo calcolo.")
        else:
            st.info("Premi Calcola curve motore per ottenere i grafici. L’animazione non esegue questo calcolo.")
        if motor_interval.valid:
            st.write(f"**Fine corsa verso sterzata negativa:** {motor_interval.lower_reason}.")
            st.write(f"**Fine corsa verso sterzata positiva:** {motor_interval.upper_reason}.")
        st.caption("Modello cinematico ideale: non calcola coppia, attrito, giochi o dinamica. "
                   "La mappa non sostituisce un sensore di posizione né la calibrazione del prototipo.")

with optimizer_tab:
    render_motor_optimizer(p, install_configuration)

with analysis_tab:
    with st.expander('Cinematica e diagnostica',expanded=False):
        st.subheader("Grafici e diagnostica su richiesta")
        analysis_angle = st.session_state.snapshot_angle
        if analysis_angle is None:
            st.warning("La posa acquisita non è valida. Scegli una posa risolvibile nella simulazione.")
        else:
            st.caption(f"Sterzata acquisita: {math.degrees(st.session_state.snapshot_steering):+.2f}° "
                       f"(ruota SX: {math.degrees(analysis_angle):+.2f}°). "
                       "Metti in pausa l'animazione o rilascia lo slider per acquisire una nuova posa.")
        if st.button("Calcola grafici e diagnostica", type="primary", disabled=analysis_angle is None):
            progress = st.progress(0, text="Campionamento della risposta cinematica…")
            with st.spinner("Calcolo su richiesta…"):
                samples = sampled(p)
                progress.progress(35, text="Preparazione dei sei grafici…")
                figure = response_plots(p, samples, analysis_angle)
                progress.progress(75, text="Diagnostica della posa…")
                pose = select_pose(solve(p, analysis_angle), p.branch)
                st.session_state.technical_result = {
                    "angle": analysis_angle, "steering": st.session_state.snapshot_steering, "figure": figure, "pose": pose,
                    "diagnostics": diagnose(p, pose) if pose else None,
                    "top_view": top_view(p, pose, samples),
                }
                progress.progress(100, text="Analisi pronta")
            progress.empty()
        result = st.session_state.get("technical_result")
        if result:
            remember_figures("technical","Analisi cinematica della configurazione attuale",{"Risposta cinematica":result["figure"],"Posa acquisita":result["top_view"]})
            st.caption(f"Risultati alla sterzata media {math.degrees(result['steering']):+.2f}° "
                       f"(θ SX = {math.degrees(result['angle']):+.2f}°). "
                       "Restano fermi durante l'animazione; premi Calcola per aggiornarli.")
            st.plotly_chart(result["figure"], use_container_width=True, config={"displaylogo": False}, key="responses")
            with st.expander("Vista della posa acquisita · esportazione SVG"):
                st.plotly_chart(result["top_view"], use_container_width=True,
                                config={"displaylogo": False, "toImageButtonOptions": {"format": "svg", "filename": "steering-top-view"}},
                                key="snapshot_top_view")
            pose, diag = result["pose"], result["diagnostics"]
            if pose:
                st.write(f"**Errore chiusura:** {pose.closure_error:.2e} mm · **Margine radiale:** {pose.radial_margin:.4f} mm")
                st.write(f"**T** = ({pose.point[0]+p.pivot_spacing/2:.3f}, {pose.point[1]:.3f}) mm")
                if diag.point_velocity is not None:
                    st.caption(f"dT/dθ SX = ({diag.point_velocity[0]:.3f}, {diag.point_velocity[1]:.3f}) mm/rad")
                st.caption(f"Distanza dal punto morto: {math.degrees(diag.toggle_distance):.2f}°")
                rows = []
                for side, center, pivot, bracket, theta, heading in (
                    ("SX", pose.c_left, pose.a_left, p.left, pose.theta_left, pose.heading_left),
                    ("DX", pose.c_right, pose.a_right, p.right, pose.theta_right, pose.heading_right)):
                    delta = center-pivot-np.array([bracket.axle_x, bracket.axle_y])
                    rows.append({"Ruota": side, "C x · mm": center[0]+p.pivot_spacing/2, "C y · mm": center[1],
                                 "ΔC x · mm": delta[0], "ΔC y · mm": delta[1], "|ΔC| · mm": float(np.linalg.norm(delta)),
                                 "Angolo staffa · °": math.degrees(theta), "Heading ruota · °": math.degrees(heading)})
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.error("La posa non ammette una soluzione cinematica.")
            st.caption("Rosso nei grafici: intervalli impossibili. Linee rosse puntinate: punti morti analitici. "
                       "La sterzata massima della geometria è riportata nella scheda Simulazione.")
        else:
            st.info("I grafici vengono calcolati solo quando premi il pulsante. L'animazione resta indipendente.")

with design:
    render_quadrilateral_optimizer(p, install_configuration)

