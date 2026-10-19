"""Human-readable manual CAD export and numeric sweep data."""
import csv
import io
import math
from .kinematics import Sample
from .parameters import Parameters
from .singularities import diagnose


def onshape_variables(p: Parameters) -> str:
    values = [
        ("Interasse_sterzo", p.pivot_spacing, "mm"),
        ("L_braccio_SX", p.left.arm_length, "mm"), ("L_braccio_DX", p.right.arm_length, "mm"),
        ("L_SteeringRod", p.tie_length, "mm"),
        ("L_taglio_braccio_SX", p.left.arm_length+2*p.physical.end_margin, "mm"),
        ("L_taglio_braccio_DX", p.right.arm_length+2*p.physical.end_margin, "mm"),
        ("L_taglio_tirante", p.tie_length+2*p.physical.end_margin, "mm"),
    ]
    for side, bracket in (("SX", p.left), ("DX", p.right)):
        values += [(f"Angolo_braccio_{side}", math.degrees(bracket.arm_angle), "deg"),
                   (f"Offset_ruota_X_{side}", bracket.axle_x, "mm"),
                   (f"Offset_ruota_Y_{side}", bracket.axle_y, "mm"),
                   (f"Orientamento_ruota_{side}", math.degrees(bracket.heading_offset), "deg")]
    f = p.physical
    for name, value in (
        ("Spessore_braccio", f.arm_thickness),
        ("Larghezza_braccio", f.arm_width), ("Spessore_tirante", f.rod_thickness),
        ("Larghezza_tirante", f.rod_width), ("Diametro_foro", f.hole_diameter),
        ("Diametro_perno", f.pivot_diameter), ("Margine_foro", f.end_margin),
        ("Diametro_ruota", f.wheel_diameter), ("Larghezza_ruota", f.wheel_width),
        ("Quota_braccio", f.arm_z), ("Quota_tirante", f.rod_z),
        ("Quota_staffa", f.bracket_z), ("Quota_asse_ruota", f.wheel_axle_z),
        ("Larghezza_staffa", f.bracket_width), ("Spessore_staffa", f.bracket_thickness),
        ("Diametro_rondella", f.washer_diameter), ("Spessore_rondella", f.washer_thickness),
        ("Altezza_distanziale", f.spacer_height), ("Diametro_testa_vite", f.bolt_head_diameter),
    ):
        values.append((name, value, "mm"))
    lines = ["PARAMETRI PER ONSHAPE — trasferimento manuale", "",
             "Creare variabili con questi nomi; nelle quote usare #Nome_variabile.",
             "X verso destra, Y verso il retro; angoli bracci misurati da +X.",
             "L_braccio e L_SteeringRod sono distanze fra centri dei fori.",
             "L_taglio include due margini foro-estremità; non è l'interasse.", ""]
    lines += [f"{name} = {value:.9g} {unit}    →    #{name}" for name, value, unit in values]
    lines += ["", f"Ramo di montaggio: {p.branch:+d}",
              "I perni di sterzo sono a (−#Interasse_sterzo/2, 0) e (+#Interasse_sterzo/2, 0).",
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
                    math.degrees(d.mismatch), d.ratio, *pose.point,
                    *(d.point_velocity if d.point_velocity is not None else (None, None)),
                    *pose.c_left, *pose.c_right, pose.closure_error, math.degrees(d.toggle_distance)]
        else:
            row += [None]*15
        writer.writerow(row)
    return output.getvalue()
