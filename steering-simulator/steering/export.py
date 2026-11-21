"""Human-readable manual CAD export and numeric sweep data."""
import csv
import io
import json
import math
from .kinematics import Sample
from .parameters import Parameters
from .singularities import diagnose
from .reference import chassis_point


def onshape_variables(p: Parameters) -> str:
    values = [
        ("Interasse_sterzo", p.pivot_spacing, "mm"),
        ("L_braccio_SX", p.left.arm_length, "mm"), ("L_braccio_DX", p.right.arm_length, "mm"),
        ("L_SteeringRod", p.tie_length, "mm"),
    ]
    for side, bracket in (("SX", p.left), ("DX", p.right)):
        values += [(f"Angolo_braccio_{side}", math.degrees(bracket.arm_angle), "deg"),
                   (f"Offset_ruota_X_{side}", bracket.axle_x, "mm"),
                   (f"Offset_ruota_Y_{side}", bracket.axle_y, "mm"),
                   (f"Orientamento_ruota_{side}", math.degrees(bracket.heading_offset), "deg")]
    values += [("Diametro_ruota", p.physical.wheel_diameter, "mm"),
               ("Larghezza_ruota", p.physical.wheel_width, "mm")]
    values += [("Motore_X", p.motor.x+p.pivot_spacing/2, "mm"), ("Motore_Y", p.motor.y, "mm"),
               ("L_leva_motore", p.motor.crank_radius, "mm"),
               ("L_astina_motore", p.motor.connecting_length, "mm"),
               ("Attacco_tirante_lambda", p.actuation_fraction, "")]
    lines = ["PARAMETRI PER ONSHAPE — trasferimento manuale", "",
             "Creare variabili con questi nomi; nelle quote usare #Nome_variabile.",
             "Origine A SX = (0, 0). X verso destra, Y verso il retro; angoli bracci misurati da +X.",
             "L_braccio e L_SteeringRod sono distanze fra centri dei fori.",
             "Spessori, ferramenta e dimensioni grafiche non fanno parte dell’export.", ""]
    lines += [f"{name} = {value:.9g} {unit}    →    #{name}" for name, value, unit in values]
    lines += ["", f"Ramo di montaggio: {p.branch:+d}", f"Montaggio leva motore: {'A' if p.motor.assembly == 1 else 'B'}",
              "I perni di sterzo sono A SX = (0, 0) e A DX = (#Interasse_sterzo, 0).",
              "Quote iniziali, non validate per carichi, resistenza o tolleranze di produzione."]
    return "\n".join(lines)


def sweep_csv(p: Parameters, samples: list[Sample]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["theta_left_deg", "status", "branch", "segment", "theta_right_deg",
                     "heading_left_deg", "heading_right_deg", "mismatch_deg", "ratio",
                     "Tx_mm", "Ty_mm", "dTx_mm_per_rad", "dTy_mm_per_rad",
                     "CLx_mm", "CLy_mm", "CRx_mm", "CRy_mm", "closure_error_mm", "toggle_distance_deg"])
    for sample in samples:
        pose = sample.pose
        row = [math.degrees(sample.angle), sample.status, p.branch, sample.segment]
        if pose:
            d = diagnose(p, pose)
            row += [math.degrees(pose.theta_right), math.degrees(pose.heading_left), math.degrees(pose.heading_right),
                    math.degrees(d.mismatch), d.ratio, *chassis_point(p,pose.point),
                    *(d.point_velocity if d.point_velocity is not None else (None, None)),
                    *chassis_point(p,pose.c_left), *chassis_point(p,pose.c_right), pose.closure_error, math.degrees(d.toggle_distance)]
        else:
            row += [None]*15
        writer.writerow(row)
    return output.getvalue()


def freecad_json(p: Parameters) -> str:
    """Neutral steering geometry; CAD supplies physical thicknesses and stacking."""
    from .motor import at_steering, build_range

    p.validate()
    actuator = at_steering(p, 0.0)
    if actuator is None:
        raise ValueError('Il comando motore non chiude nella posizione centrale: verificare la configurazione attiva.')
    pose = actuator.pose
    points = dict(A_SX=pose.a_left, A_DX=pose.a_right,
                  B_SX=pose.b_left, B_DX=pose.b_right,
                  C_SX=pose.c_left, C_DX=pose.c_right, T=pose.point,
                  M=(p.motor.x, p.motor.y), Q=actuator.pin)
    interval = build_range(p)
    if not interval.valid:
        raise ValueError('Cinematica CAD: '+interval.reason)
    # Due semisettori, zero incluso esattamente; nessuna interpolazione nel CAD.
    angles = [interval.mean_lower*(1-i/100) for i in range(100)]
    angles += [interval.mean_upper*i/100 for i in range(101)]
    frames = []
    for angle in angles:
        state = at_steering(p, angle, actuator.phi)
        if state is None:
            raise ValueError('Cinematica CAD: posa non risolvibile a %.9g gradi.' % math.degrees(angle))
        pp = state.pose
        frames.append(dict(steering=angle, phi=state.phi,
            theta_left=pp.theta_left, theta_right=pp.theta_right,
            points={name: chassis_point(p, point).tolist() for name, point in
                    dict(B_SX=pp.b_left, B_DX=pp.b_right, C_SX=pp.c_left,
                         C_DX=pp.c_right, T=pp.point, Q=state.pin).items()}))
    data = dict(format='EFES_steering_CAD', version=2,
                units=dict(length='mm', angle='rad'), coordinate_origin='A_SX',
                axes=dict(x='destra', y='retro', z='alto'), steering_angle=0.0,
                points={name: chassis_point(p, point).tolist() for name, point in points.items()},
                wheel=dict(diameter=p.physical.wheel_diameter, width=p.physical.wheel_width,
                           heading_left=pose.heading_left, heading_right=pose.heading_right),
                motion=dict(neutral_index=100, frames=frames,
                            lower_reason=interval.lower_reason, upper_reason=interval.upper_reason),
                link_width=p.physical.link_width,
                note='Geometria attiva del simulatore, posa centrale. Spessori e montaggio da verificare sui pezzi reali.')
    return json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
