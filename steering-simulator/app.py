"""Local Streamlit interface. All mechanics live in steering/, not in widgets."""
from __future__ import annotations

from dataclasses import replace
import math
import hashlib

import numpy as np
import streamlit as st

from steering.export import onshape_variables, sweep_csv
from steering.kinematics import select_pose, solve, sweep, steering_input, steering_limit
from steering.optimization import evaluate, explore
from steering.parameters import (Parameters, Motor, from_json, to_json,
                                 symmetric_steering, validate_symmetric_setup)
from steering.singularities import diagnose
from steering.motor import build_range, at_steering, response, response_csv
from visualization.plots import response_plots
from visualization.motor_plots import motor_plots
from visualization.motor_optimizer import render_motor_optimizer
from visualization.physical_config import render_physical_config
from visualization.browser_motion import browser_motion
from visualization.top_view import top_view


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
    st.session_state.configuration = Parameters()
    st.session_state.revision = 0
elif not hasattr(st.session_state.configuration.physical, "link_width"):
    # Preserve an open session across the addition of persisted 2D widths.
    st.session_state.configuration = from_json(to_json(st.session_state.configuration))
    st.session_state.revision += 1


def install_configuration(p: Parameters) -> None:
    validate_symmetric_setup(p)
    st.session_state.configuration = p
    st.session_state.revision += 1
    st.session_state.pop("candidates", None)


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
        length = number("Lunghezza Braccio", original.left.arm_length, "arm_length", .1, 500.0, .5,
                        "Distanza fra perno fisso e foro del tirante, uguale per entrambi i bracci.")
        tie = number("Lunghezza Tirante", original.tie_length, "tie", .1, 3000.0, .5,
                     "Distanza fra i centri dei due fori del tirante.")
        inclination = angle("Inclinazione Bracci · °", original.left.arm_angle-math.pi/2,
                            "inclination", -89.9, 89.9)
        st.caption("0° = bracci verso il retro. Positivo = verso l'esterno; negativo = verso l'interno. "
                   "Staffe sempre simmetriche e ruote dritte nella posa iniziale.")
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
                motor_x = number("Posizione motore X", original.motor.x, "motor_x", -2000.0, 2000.0, .5)
            with y:
                motor_y = number("Posizione motore Y", original.motor.y, "motor_y", -2000.0, 2000.0, .5)
            crank = number("Lunghezza leva motore M–Q", original.motor.crank_radius, "crank", .1, 500.0, .5)
            connecting = number("Lunghezza astina Q–T", original.motor.connecting_length, "connecting", .1, 2000.0, .5)
            fraction = number("Attacco T sul tirante · λ", original.actuation_fraction, "lambda", 0.0, 1.0, .05,
                              "0 = estremità SX, 0.5 = centro, 1 = estremità DX.")
            assembly = st.selectbox("Montaggio della leva al centro", [1, -1],
                                   index=0 if original.motor.assembly == 1 else 1,
                                   format_func=lambda value: "A" if value == 1 else "B", key=f"p{revision}_motor_assembly",
                                   help="Le due possibili posizioni del giunto Q: osserva il disegno e scegli il montaggio.")
            st.caption("0° motore corrisponde alle ruote dritte. Il montaggio scelto rimane fisso durante il movimento.")
        with st.expander("03 / Esplorazione del movimento"):
            display_range = angle("Intervallo slider · ±°", original.display_range, "range", 1.0, 90.0)
        template = replace(original, left=replace(original.left, axle_x=axle_x, axle_y=axle_y),
                           display_range=display_range,
                           actuation_fraction=fraction, motor=Motor(motor_x, motor_y, crank, connecting, assembly))
        try:
            p = symmetric_steering(template, length, tie, inclination)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        st.caption(f"Interasse perni calcolato: **{p.pivot_spacing:.3f} mm**")
        if st.button("Ripristina dimensioni iniziali", use_container_width=True):
            install_configuration(Parameters())
            st.rerun()
        st.caption("I parametri restano nella sessione. Scarica il JSON per conservarli.")
    return p


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
    st.session_state.snapshot_angle = 0.0
    st.session_state.snapshot_steering = 0.0
    st.session_state.snapshot_motor = 0.0
    for result_key in ("candidates", "technical_result", "design_evaluation", "csv_export", "motor_results"):
        st.session_state.pop(result_key, None)

st.markdown("<div class='eyebrow'>PARAMETRIC STEERING / LABORATORIO CINEMATICO 2D</div>", unsafe_allow_html=True)
st.title("Steering Lab")
st.markdown("<div class='subtitle'>Progetta lo sterzo prima di costruirlo. Un ingresso, due ruote, un vincolo rigido.</div>", unsafe_allow_html=True)

simulation, motor_tab, dimensions_tab, optimizer_tab, graphs, design, files, guide = st.tabs(["Simulazione", "Motore e sensibilità", "Ingombri 2D", "Ottimizzazione motore", "Risposta cinematica", "Esplora progetti", "File e Onshape", "Modello e costruzione"])

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
    snapshot = browser_motion(p, signature, motor_interval)
    if snapshot and snapshot.get("signature") == signature:
        angle = snapshot.get("angle")
        steering = snapshot.get("steering_angle")
        if angle is None or (isinstance(angle, (int, float)) and math.isfinite(angle)
                             and isinstance(steering, (int, float)) and math.isfinite(steering)
                             and abs(steering) <= math.pi/2+1e-9):
            st.session_state.snapshot_angle = angle
            st.session_state.snapshot_steering = steering
            st.session_state.snapshot_motor = snapshot.get("motor_angle")

with motor_tab:
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
        st.download_button("↓ Curva motore CSV", response_csv(result["rows"]), "motor-steering-response.csv", "text/csv")
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

with graphs:
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
            st.write(f"**T** = ({pose.point[0]:.3f}, {pose.point[1]:.3f}) mm")
            if diag.point_velocity is not None:
                st.caption(f"dT/dθ SX = ({diag.point_velocity[0]:.3f}, {diag.point_velocity[1]:.3f}) mm/rad")
            st.caption(f"Distanza dal punto morto: {math.degrees(diag.toggle_distance):.2f}°")
            rows = []
            for side, center, pivot, bracket, theta, heading in (
                ("SX", pose.c_left, pose.a_left, p.left, pose.theta_left, pose.heading_left),
                ("DX", pose.c_right, pose.a_right, p.right, pose.theta_right, pose.heading_right)):
                delta = center-pivot-np.array([bracket.axle_x, bracket.axle_y])
                rows.append({"Ruota": side, "C x · mm": center[0], "C y · mm": center[1],
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
    st.subheader("Confronta la corsa delle geometrie")
    st.caption("I candidati sono ordinati per sterzata massima, fino a 90°. Nessun obiettivo su rapporto fra ruote o interferenze.")
    st.markdown("**Esplorazione automatica delle dimensioni**")
    st.caption("La ricerca varia lunghezza braccio, inclinazione e lunghezza tirante; calcola l’interasse dei perni. "
               "Ruote e offset SX rimangono quelli impostati. Gli offset DX vengono specchiati.")
    with st.form("explore"):
        a, b, c = st.columns(3)
        with a:
            lengths = st.text_input("Lunghezze braccio · mm", "20, 25, 35")
        with b:
            angles = st.text_input("Inclinazioni bracci · °", "-5, 0, 5")
        with c:
            ties = st.text_input("Lunghezze tirante · mm", f"{p.tie_length:g}")
        submitted = st.form_submit_button("Confronta candidati", type="primary")
    if submitted:
        try:
            def numbers(text: str) -> list[float]:
                values = [float(item.strip()) for item in text.split(",")]
                if not values or not all(math.isfinite(v) for v in values):
                    raise ValueError("Inserisci numeri finiti separati da virgole.")
                return values
            lens, angs, rods = numbers(lengths), numbers(angles), numbers(ties)
            if min(lens+rods) <= 0:
                raise ValueError("Le lunghezze devono essere positive.")
            with st.spinner("Calcolo della corsa di ogni candidato…"):
                st.session_state.candidates = explore(p, lens, [math.radians(v) for v in angs], rods)
        except ValueError as exc:
            st.error(str(exc))
    candidates = st.session_state.get("candidates", [])
    if candidates:
        st.dataframe([{"#": i+1, "Braccio · mm": c.parameters.left.arm_length,
                       "Inclinazione · °": math.degrees(c.parameters.left.arm_angle-math.pi/2), "Interasse · mm": c.parameters.pivot_spacing,
                       "Tirante · mm": round(c.parameters.tie_length, 3), "Sterzata massima · ±°": round(math.degrees(c.evaluation.steering_limit), 2),
                       "Limite": "Punto morto" if c.evaluation.at_deadpoint else "90° raggiunti",
                       "Motivi / limiti": " ".join(c.evaluation.reasons) or ""}
                      for i, c in enumerate(candidates)], hide_index=True, use_container_width=True)
        choice = st.selectbox("Candidato da caricare", range(len(candidates)), format_func=lambda i: f"Candidato {i+1}")
        if st.button("Applica dimensioni del candidato"):
            install_configuration(candidates[choice].parameters)
            st.rerun()

with files:
    st.subheader("Dal simulatore al banco di lavoro")
    a, b, c = st.columns(3)
    a.download_button("↓ Configurazione JSON", to_json(p), "steering-configuration.json", "application/json", use_container_width=True)
    b.download_button("↓ Variabili Onshape", onshape_variables(p), "onshape-variables.txt", "text/plain", use_container_width=True)
    if c.button("Prepara risposta CSV", use_container_width=True):
        with st.spinner("Preparazione del CSV…"):
            st.session_state.csv_export = sweep_csv(p, sampled(p))
    if "csv_export" in st.session_state:
        c.download_button("↓ Risposta CSV", st.session_state.csv_export, "steering-response.csv", "text/csv", use_container_width=True)
    st.caption("JSON completo in mm e radianti, con versione dello schema e ramo selezionato. "
               "Il CSV usa gradi per gli angoli e mm/rad per le derivate. Le variabili CAD si trasferiscono manualmente.")
    uploaded = st.file_uploader("Carica una configurazione JSON", type=["json"])
    if uploaded is not None:
        try:
            imported = from_json(uploaded.getvalue())
            validate_symmetric_setup(imported)
            st.success(f"Configurazione valida · interasse {imported.pivot_spacing:g} mm · ramo {imported.branch:+d}")
            if st.button("Carica configurazione"):
                install_configuration(imported)
                st.rerun()
        except ValueError as exc:
            st.error(f"Impossibile caricare: {exc}")
    with st.expander("Anteprima delle variabili per Onshape"):
        st.code(onshape_variables(p), language=None)

with guide:
    st.subheader("Il modello, senza scorciatoie")
    st.markdown("""
**Un quadrilatero articolato con un solo ingresso.** A SX e A DX sono i perni fissi. B è il foro del tirante,
C il centro dell'asse ruota: B e C ruotano insieme alla propria staffa, ma i rispettivi vettori locali sono indipendenti.
Il movimento di rotolamento della ruota è escluso. X è positivo verso destra, Y verso il retro; il fronte è −Y.

**Inclinazione Bracci: 0° = bracci rivolti al retro**, positiva verso l'esterno, negativa verso l'interno.
Le staffe sono sempre speculari e le ruote sono dritte nella posa zero.
L'interasse dei perni viene ricavato da lunghezza tirante t, lunghezza braccio L e inclinazione β:
**d = t − 2 L sin β**. I parametri che richiedono un interasse nullo o negativo vengono rifiutati.
Lo slider comanda la media (θ SX + θ DX)/2: richieste opposte producono pose speculari.
La velocità di animazione è riferita a questo angolo medio; i grafici tecnici conservano θ SX come ascissa.
Gli angoli di sterzata θ SX/DX si misurano dalla posa zero; l'angolo positivo orienta le ruote verso +X.
Internamente e nell'export CAD l'orientamento dei bracci rimane misurato da +X (90° + β a SX, 90° − β a DX).
""")
    st.latex(r"B_i=A_i+R(\theta_i)b_i,\quad C_i=A_i+R(\theta_i)c_i,\quad \|B_R-B_L\|=t")
    st.markdown("""
**Due cerchi, due rami.** Il punto B DX è l'intersezione del cerchio del braccio DX con quello del tirante.
Il segno ± identifica il lato orientato della retta A DX → B SX. Il ramo −1 è il parallelogramma iniziale.
Il segno rimane fisso durante il movimento; gli angoli vengono svolti rispetto alla posa precedente.
Quando la richiesta supera il primo punto morto raggiungibile dalla posa zero, il modello restituisce la posa limite calcolata. Slider, angoli e disegno rappresentano quella stessa posa. Un allarme di prossimità non blocca una posa ancora valida.
""")
    st.latex(r"\frac{d\theta_R}{d\theta_L}=\frac{(B_R-B_L)\cdot JR(\theta_L)b_L}{(B_R-B_L)\cdot JR(\theta_R)b_R}")
    st.markdown("""
**Sensibilità e punti morti.** Le tolleranze numeriche sulle lunghezze sono 10⁻¹⁰ volte la massima lunghezza
del quadrilatero. La soglia diagnostica interna si applica alla trasmissione normalizzata |d·B′|/(tL),
separatamente sui due lati. La distanza dal punto morto è espressa in gradi dell'ingresso SX e calcolata
dalle tangenti dei cerchi, compreso il caso degenere di centri coincidenti. Un ingresso inefficace può
essere segnalato anche senza una tangente in uscita. Vicino alla singolarità di uscita rapporto e velocità di T sono sospesi.

**Il tirante non è una slitta.** Nel parallelogramma, il suo centro segue T = (−L sin θ, L cos θ).
Un attuatore che impone una retta a T introduce un vincolo ulteriore e può bloccare il sistema.

**Rappresentazione grafica.** Larghezza di bracci, supporti e tirante, margini e simboli dei giunti
sono costanti illustrative: non sono quote costruttive né vincoli dell'ottimizzazione.
Spessori, quote Z, viti, rondelle e distanziali si definiscono successivamente nel CAD.
Non vengono verificate interferenze fra componenti o fra ruote.
Il supporto dei perni non è modellato.
""")
    st.markdown("""
**Costruzione con ferramenta comune**

1. Fissa i perni verticali al supporto progettato in CAD e lascia libere le staffe di ruotare.
2. Fissa rigidamente ogni braccio alla staffa: due punti di fissaggio o una geometria antirotazione.
3. Assembla il tirante con due giunti rotanti, rondelle e distanziali; evita di serrarli fino a bloccarli.
4. Controlla corsa, giochi, interferenze e arresti con il prototipo scarico prima di motorizzare.

**Limiti del primo traguardo.** Il modello è rigido e planare: non calcola carichi, attrito, forze pneumatici,
elasticità, gioco dei cuscinetti, sospensioni, resistenza o coppia del motore. La corsa massima deriva dai punti morti geometrici; le curve di risposta sono campionate.

**Motore con leva e astina.** La leva M–Q ruota attorno a M; l’astina Q–T ha lunghezza fissa
ed è snodata alle estremità. Il punto T resta solidale al tirante e segue la traiettoria imposta dallo sterzo.
Il programma calcola la posa neutra della leva dal montaggio A/B e determina il tratto continuo
collegato alle ruote dritte, fermandosi al primo limite di chiusura, punto morto o limite dello sterzo.
Non presume che il motore possa compiere giri completi. La ricerca iniziale dei limiti è numerica,
con 256 intervalli per lato e raffinamento per bisezione; non è un’ottimizzazione delle dimensioni.

Il JGA25-370 indicato nella specifica è nominalmente 12 V, circa 58 RPM, senza encoder integrato.
L’angolo simulato è quello dell’albero in uscita dal riduttore. Non sono assunti dimensioni dell’albero,
coppia disponibile o un comportamento PWM→angolo. Servono feedback o riferimenti per conoscere
la posizione reale. La velocità di riproduzione serve solo a osservare la cinematica.
""")
    st.caption("Sorgenti e istruzioni complete: README.md nella cartella del progetto.")

st.divider()
st.caption("STEERING LAB / Modello cinematico rigido · progetto educativo · elaborazione interamente locale")
