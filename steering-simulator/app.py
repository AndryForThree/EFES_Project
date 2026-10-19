"""Local Streamlit interface. All mechanics live in steering/, not in widgets."""
from __future__ import annotations

from dataclasses import asdict, replace
import math
import hashlib

import numpy as np
import streamlit as st

from steering.clearances import check_clearances, manufacturing_issues
from steering.export import onshape_variables, sweep_csv
from steering.kinematics import neutral_branch, neutral_tie_length, select_pose, solve, sweep
from steering.optimization import evaluate, explore
from steering.parameters import Bracket, Parameters, Physical, Targets, from_json, to_json
from steering.singularities import diagnose
from visualization.plots import response_plots
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


def install_configuration(p: Parameters) -> None:
    p.validate()
    st.session_state.configuration = p
    st.session_state.revision += 1
    st.session_state.pop("candidates", None)


@st.cache_data(show_spinner=False, max_entries=12)
def sampled(p: Parameters):
    return sweep(p, -p.display_range, p.display_range, 181)


@st.cache_data(show_spinner=False, max_entries=12)
def evaluated(p: Parameters):
    return evaluate(p)


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
        symmetric = st.checkbox("Staffe simmetriche", value=original.symmetric, key=f"p{revision}_symmetric",
                                help="Specchio rispetto a Y: X cambia segno, Y si conserva. I due bracci neutri puntano entrambi al retro.")
        d = number("Interasse perni d", original.pivot_spacing, "spacing", 1.0, 2000.0)
        tie = number("Interasse tirante t", original.tie_length, "tie", .1, 3000.0, .5,
                     "Parametro fisico indipendente: non viene ricalcolato automaticamente.")

        def bracket_fields(bracket: Bracket, side: str) -> Bracket:
            length = number(f"Lunghezza braccio {side}", bracket.arm_length, side+"arm", .1, 500.0, .5)
            alpha = angle(f"Orientamento braccio {side} · ° da +X", bracket.arm_angle, side+"alpha")
            x, y = st.columns(2)
            with x:
                axle_x = number(f"Offset X ruota {side}", bracket.axle_x, side+"cx", -500.0, 500.0, .5)
            with y:
                axle_y = number(f"Offset Y ruota {side}", bracket.axle_y, side+"cy", -500.0, 500.0, .5)
            heading = angle(f"Orientamento iniziale ruota {side} · °", bracket.heading_offset, side+"heading")
            return Bracket(length, alpha, axle_x, axle_y, heading)

        with st.expander("01 / Staffe e ruote", expanded=True):
            left = bracket_fields(original.left, "SX")
            if symmetric:
                right = Bracket(left.arm_length, math.pi-left.arm_angle, -left.axle_x, left.axle_y, -left.heading_offset)
                st.caption("DX collegata per simmetria. Con 90° entrambi i bracci sono rivolti al retro.")
            else:
                st.divider()
                right = bracket_fields(original.right, "DX")
            physical = asdict(original.physical)
            physical["wheel_diameter"] = number("Diametro ruote", physical["wheel_diameter"], "wheel_diameter", 1.0, 500.0)
            physical["wheel_width"] = number("Larghezza pneumatici", physical["wheel_width"], "wheel_width", 1.0, 200.0)

        with st.expander("02 / Piattine e supporti"):
            for key, label in (("arm_width", "Larghezza bracci"), ("arm_thickness", "Spessore bracci"),
                               ("rod_width", "Larghezza tirante"), ("rod_thickness", "Spessore tirante"),
                               ("bracket_width", "Larghezza supporto asse"), ("bracket_thickness", "Spessore supporto asse")):
                physical[key] = number(label, physical[key], key, .1, 2000.0, .5)
        with st.expander("03 / Fori e ferramenta"):
            for key, label in (("hole_diameter", "Diametro fori"), ("pivot_diameter", "Diametro perni"),
                               ("end_margin", "Margine centro foro → estremità"), ("bolt_head_diameter", "Diametro testa vite"),
                               ("washer_diameter", "Diametro rondelle"), ("washer_thickness", "Spessore rondelle"),
                               ("spacer_height", "Altezza distanziali")):
                physical[key] = number(label, physical[key], key, .1, 100.0, .1)
        with st.expander("04 / Quote Z · verifica 2.5D"):
            physical["use_heights"] = st.checkbox("Considera separazione verticale", value=physical["use_heights"], key=f"p{revision}_z")
            st.caption("Quote in mm rispetto a un riferimento Z arbitrario. Per staffe, bracci e tirante si indica la superficie inferiore.")
            for key, label in (("bracket_z", "Quota staffe"),
                               ("arm_z", "Quota bracci"), ("rod_z", "Quota tirante"), ("wheel_axle_z", "Quota asse ruote")):
                physical[key] = number(label, physical[key], key, -500.0, 500.0, .5)
        with st.expander("05 / Obiettivi e soglie"):
            t = original.targets
            left_target = angle("Escursione desiderata SX · ±°", t.left_angle, "left_target", 1.0, 179.0)
            right_target = angle("Escursione desiderata DX · ±°", t.right_angle, "right_target", 1.0, 179.0)
            mismatch = angle("Differenza angolare massima · °", t.max_mismatch, "mismatch", 0.0, 180.0)
            target_ratio = number("Rapporto obiettivo", t.target_ratio, "ratio", -20.0, 20.0, .05)
            ratio_tolerance = number("Tolleranza sul rapporto", t.ratio_tolerance, "ratio_tol", 0.0, 10.0, .01)
            min_toggle = angle("Distanza minima dal punto morto · °", t.min_toggle_angle, "min_toggle", 0.0, 180.0)
            clearance = number("Gioco minimo fra ingombri", t.clearance, "clearance", 0.0, 50.0, .1)
            warning = number("Soglia trasmissione normalizzata", t.warning_sine, "warning", .001, .99, .01,
                             "Allarme se |d · B′| / (t L) è inferiore alla soglia. Il rapporto non viene mostrato vicino al punto morto di uscita.")
            targets = Targets(left_target, right_target, mismatch, target_ratio, ratio_tolerance, min_toggle, clearance, warning)
        with st.expander("06 / Esplorazione del movimento"):
            display_range = angle("Intervallo slider · ±°", original.display_range, "range", 1.0, 180.0)
            fraction = number("Posizione T sul tirante · λ", original.actuation_fraction, "lambda", 0.0, 1.0, .05)
            branch = st.selectbox("Ramo di montaggio", [-1, 1], index=0 if original.branch == -1 else 1,
                                  format_func=lambda b: f"{b:+d} · lato {'negativo' if b < 0 else 'positivo'} dei cerchi",
                                  key=f"p{revision}_branch")
        p = Parameters(d, left, right, tie, Physical(**physical), targets, display_range, fraction, branch, symmetric)
        st.caption(f"Tirante per la posa zero nominale: **{neutral_tie_length(p):.3f} mm**")
        if st.button("Calcola tirante per posa zero", use_container_width=True):
            updated = replace(p, tie_length=neutral_tie_length(p))
            install_configuration(replace(updated, branch=neutral_branch(updated) or -1))
            st.rerun()
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
signature = hashlib.sha256((to_json(p)+str(st.session_state.revision)).encode()).hexdigest()
if st.session_state.get("motion_signature") != signature:
    st.session_state.motion_signature = signature
    st.session_state.snapshot_angle = 0.0
    for result_key in ("candidates", "technical_result", "design_evaluation", "csv_export"):
        st.session_state.pop(result_key, None)

st.markdown("<div class='eyebrow'>PARAMETRIC STEERING / LABORATORIO CINEMATICO 2D</div>", unsafe_allow_html=True)
st.title("Steering Lab")
st.markdown("<div class='subtitle'>Progetta lo sterzo prima di costruirlo. Un ingresso, due ruote, un vincolo rigido.</div>", unsafe_allow_html=True)

neutral_error = p.tie_length-neutral_tie_length(p)
if abs(neutral_error) > p.length_tolerance:
    st.warning(f"Posa zero incompatibile: il tirante differisce di {neutral_error:+.3f} mm dalla misura richiesta. "
               "A θ SX = 0 la ruota destra può essere già sterzata, oppure il montaggio impossibile. "
               "Usa il comando esplicito nella barra laterale per ricalcolare il tirante.")

simulation, graphs, design, files, guide = st.tabs(["Simulazione", "Risposta cinematica", "Esplora progetti", "File e Onshape", "Modello e costruzione"])

with simulation:
    snapshot = browser_motion(p, signature)
    if snapshot and snapshot.get("signature") == signature:
        angle = snapshot.get("angle")
        if angle is None or (isinstance(angle, (int, float)) and math.isfinite(angle) and abs(angle) <= p.display_range+1e-9):
            st.session_state.snapshot_angle = angle

with graphs:
    st.subheader("Grafici e diagnostica su richiesta")
    analysis_angle = st.session_state.snapshot_angle
    if analysis_angle is None:
        st.warning("La posa acquisita non è valida. Scegli una posa risolvibile nella simulazione.")
    else:
        st.caption(f"Posa acquisita: θ SX = {math.degrees(analysis_angle):+.2f}°. "
                   "Metti in pausa l'animazione o rilascia lo slider per acquisire una nuova posa.")
    if st.button("Calcola grafici e diagnostica", type="primary", disabled=analysis_angle is None):
        progress = st.progress(0, text="Campionamento della risposta cinematica…")
        with st.spinner("Calcolo su richiesta…"):
            samples = sampled(p)
            progress.progress(35, text="Preparazione dei sei grafici…")
            figure = response_plots(p, samples, analysis_angle)
            progress.progress(75, text="Verifica della posa e degli ingombri…")
            pose = select_pose(solve(p, analysis_angle), p.branch)
            st.session_state.technical_result = {
                "angle": analysis_angle, "figure": figure, "pose": pose,
                "diagnostics": diagnose(p, pose) if pose else None,
                "clearances": check_clearances(p, pose) if pose else [],
                "top_view": top_view(p, pose, samples),
            }
            progress.progress(100, text="Analisi pronta")
        progress.empty()
    result = st.session_state.get("technical_result")
    if result:
        st.caption(f"Risultati calcolati alla posa θ SX = {math.degrees(result['angle']):+.2f}°. "
                   "Restano fermi durante l'animazione; premi Calcola per aggiornarli.")
        st.plotly_chart(result["figure"], use_container_width=True, config={"displaylogo": False}, key="responses")
        with st.expander("Vista della posa acquisita · esportazione SVG"):
            st.plotly_chart(result["top_view"], use_container_width=True,
                            config={"displaylogo": False, "toImageButtonOptions": {"format": "svg", "filename": "steering-top-view"}},
                            key="snapshot_top_view")
        pose, diag, hits = result["pose"], result["diagnostics"], result["clearances"]
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
            states = {"risk": "Possibile interferenza / gioco insufficiente", "projected": "Vicinanza in pianta", "separated": "Separati in Z"}
            if hits:
                st.dataframe([{"Componente A": c.first, "Componente B": c.second, "Distanza XY · mm": c.xy_gap,
                               "Distanza Z · mm": c.z_gap, "Esito": states[c.status]} for c in hits], use_container_width=True, hide_index=True)
            for issue in manufacturing_issues(p):
                st.warning(issue)
        else:
            st.error("La posa non ammette una soluzione cinematica.")
        st.caption("Rosso nei grafici: intervalli impossibili. Linee rosse puntinate: punti morti analitici. "
                   "Il controllo degli ingombri riguarda la sola posa acquisita; usa Valuta progetto per l'intervallo obiettivo.")
    else:
        st.info("I grafici e la verifica degli ingombri vengono calcolati solo quando premi il pulsante. L'animazione resta indipendente.")

with design:
    st.subheader("Valuta prima di forare")
    st.write("Verifica il progetto nell'intervallo obiettivo e confronta una griglia limitata di geometrie simmetriche.")
    if st.button("Valuta progetto", type="primary"):
        with st.spinner("Verifica dell'intervallo obiettivo e degli ingombri…"):
            st.session_state.design_evaluation = evaluated(p)
    evaluation = st.session_state.get("design_evaluation")
    if evaluation is not None:
        cols = st.columns(4)
        cols[0].metric("Geometria", "Valida" if evaluation.geometrically_valid else "Non valida")
        cols[1].metric("Trasmissione", "Regolare" if evaluation.well_conditioned else "Critica")
        cols[2].metric("Regole costruttive", "Superate" if evaluation.manufacturing_ok else "Da correggere")
        cols[3].metric("Ingombri campionati", "Liberi" if evaluation.clearance_ok else "Da verificare")
        if evaluation.suitable:
            st.success("Candidato conforme ai controlli implementati. Resistenza, gioco reale e carichi restano da verificare.")
        for reason in evaluation.reasons:
            st.write("• " + reason)
        st.caption(f"{evaluation.sampled_poses} pose controllate; soglie e obiettivi nella barra laterale. "
                   "I punti morti sono cercati analiticamente; gli ingombri sono campionati e non costituiscono prova di assenza di collisioni.")
    else:
        st.info("Valutazione completa su richiesta: premi Valuta progetto.")
    st.divider()
    st.markdown("**Esplorazione automatica delle dimensioni**")
    st.caption("La ricerca imposta esplicitamente il tirante neutro di ogni candidato. "
               "Ruote, offset SX, materiali e quote Z rimangono quelli impostati. Gli offset DX vengono specchiati.")
    with st.form("explore"):
        a, b, c = st.columns(3)
        with a:
            lengths = st.text_input("Lunghezze braccio · mm", "20, 25, 35")
        with b:
            angles = st.text_input("Orientamenti braccio SX · °", "85, 90, 95")
        with c:
            spacings = st.text_input("Interassi perni · mm", f"{p.pivot_spacing:g}")
        submitted = st.form_submit_button("Confronta candidati", type="primary")
    if submitted:
        try:
            def numbers(text: str) -> list[float]:
                values = [float(item.strip()) for item in text.split(",")]
                if not values or not all(math.isfinite(v) for v in values):
                    raise ValueError("Inserisci numeri finiti separati da virgole.")
                return values
            lens, angs, spans = numbers(lengths), numbers(angles), numbers(spacings)
            if min(lens+spans) <= 0:
                raise ValueError("Le lunghezze devono essere positive.")
            with st.spinner("Chiusura, sensibilità e ingombri di ogni candidato…"):
                st.session_state.candidates = explore(p, lens, [math.radians(v) for v in angs], spans)
        except ValueError as exc:
            st.error(str(exc))
    candidates = st.session_state.get("candidates", [])
    if candidates:
        st.dataframe([{"#": i+1, "Braccio · mm": c.parameters.left.arm_length,
                       "α SX · °": math.degrees(c.parameters.left.arm_angle), "Interasse · mm": c.parameters.pivot_spacing,
                       "Tirante · mm": round(c.parameters.tie_length, 3), "Conforme": c.evaluation.suitable,
                       "Δ ruote max · °": round(math.degrees(c.evaluation.max_mismatch), 3),
                       "Motivi / limiti": " ".join(c.evaluation.reasons) or "Verifica meccanica ancora necessaria"}
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

L'orientamento del braccio è misurato da +X: **90° = braccio rivolto al retro**. Gli angoli delle staffe θ SX/DX
si misurano dalla loro posa zero. L'heading della ruota include anche il suo offset di montaggio.
L'angolo positivo orienta le ruote verso +X. La posa zero tratteggiata è quella nominale di ciascuna staffa,
anche quando il tirante impostato non permette alle due staffe di stare entrambe a zero.
""")
    st.latex(r"B_i=A_i+R(\theta_i)b_i,\quad C_i=A_i+R(\theta_i)c_i,\quad \|B_R-B_L\|=t")
    st.markdown("""
**Due cerchi, due rami.** Il punto B DX è l'intersezione del cerchio del braccio DX con quello del tirante.
Il segno ± identifica il lato orientato della retta A DX → B SX. Il ramo −1 è il parallelogramma iniziale.
Il segno rimane fisso durante il movimento; gli angoli vengono svolti rispetto alla posa precedente.
Il pulsante che adotta un nuovo montaggio è una scelta esplicita di posa, non una simulazione del passaggio attraverso il punto morto.
""")
    st.latex(r"\frac{d\theta_R}{d\theta_L}=\frac{(B_R-B_L)\cdot JR(\theta_L)b_L}{(B_R-B_L)\cdot JR(\theta_R)b_R}")
    st.markdown("""
**Sensibilità e punti morti.** Le tolleranze numeriche sulle lunghezze sono 10⁻¹⁰ volte la massima lunghezza
del quadrilatero. La soglia ingegneristica si applica alla trasmissione normalizzata |d·B′|/(tL),
separatamente sui due lati. La distanza dal punto morto è espressa in gradi dell'ingresso SX e calcolata
dalle tangenti dei cerchi, compreso il caso degenere di centri coincidenti. Un ingresso inefficace può
essere segnalato anche senza una tangente in uscita. Vicino alla singolarità di uscita rapporto e velocità di T sono sospesi.

**Il tirante non è una slitta.** Nel parallelogramma, il suo centro segue T = (−L sin θ, L cos θ).
Un attuatore che impone una retta a T introduce un vincolo ulteriore e può bloccare il sistema.

**Ingombri e quote Z.** Le piattine sono rettangoli con margine oltre i fori; le ruote sono rettangoli
orientati e, in Z, intervalli asse ± raggio. Questo è un inviluppo conservativo del pneumatico, non la sua forma 3D.
Rondelle e teste vite hanno un'impronta poligonale circoscritta. L'altezza della testa vite e la geometria
dei bulloni passanti non sono modellate: la loro fattibilità va verificata separatamente.
Le coppie di accoppiamento previste (braccio–tirante al giunto, staffa–braccio, supporto–ruota e relativa
ferramenta) sono escluse dal controllo di interferenza; lo spazio braccio–tirante è controllato come regola di montaggio.
L'eventuale sfregamento di queste coppie lungo il movimento richiede verifica CAD. Una sovrapposizione XY
con quote Z separate è indicata come separata, non come collisione.

**Quote aggiunte alla specifica.** Pneumatici 60 × 18 mm,
larghezza tirante 10 mm, spessore 2 mm e quote Z nella barra laterale sono ipotesi modificabili.
Il supporto dei perni non è modellato: la sua forma si progetta successivamente in CAD, attorno agli ingombri del meccanismo.
""")
    st.markdown("""
**Costruzione con ferramenta comune**

1. Fissa i perni verticali al supporto progettato in CAD e lascia libere le staffe di ruotare.
2. Fissa rigidamente ogni braccio alla staffa: due punti di fissaggio o una geometria antirotazione.
3. Assembla il tirante con due giunti rotanti, rondelle e distanziali; evita di serrarli fino a bloccarli.
4. Controlla corsa, giochi, interferenze e arresti con il prototipo scarico prima di motorizzare.

**Limiti del primo traguardo.** Il modello è rigido e planare: non calcola carichi, attrito, forze pneumatici,
elasticità, gioco dei cuscinetti, sospensioni, resistenza o coppia del motore. I criteri costruttivi sono
controlli geometrici elementari. Le verifiche d'ingombro e parte delle metriche sull'intervallo sono campionate.

**Fase successiva: attuatore.** Il JGA25-370 indicato nella specifica è nominalmente 12 V, circa 58 RPM,
senza encoder integrato. Questa versione non simula il motore. Il nucleo accetta un ingresso angolare indipendente
dalla UI: una futura biella-manovella dovrà aggiungere il vincolo ‖T−Q(φ)‖ = s e la propria continuità di ramo.
Non sono assunti dimensioni d'albero, coppia disponibile né giri completi consentiti. Per conoscere la posizione
serviranno feedback o riferimenti e limiti adeguati.
""")
    st.caption("Sorgenti e istruzioni complete: README.md nella cartella del progetto.")

st.divider()
st.caption("STEERING LAB / Modello cinematico rigido · progetto educativo · elaborazione interamente locale")
