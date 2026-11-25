"""Coordinate PCB e montaggio tramite fori. Nessuna dipendenza da FreeCAD."""
import json
import math
import re
from pathlib import Path


def leggi_pcb(file):
    # Piccolo lettore S-expression: conserva solo i dati utili al montaggio.
    tokens = iter(re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', Path(file).read_text()))

    def gruppo():
        risultato = []
        for t in tokens:
            if t == ')':
                return risultato
            risultato.append(gruppo() if t == '(' else json.loads(t) if t.startswith('"') else t)
        raise ValueError('File KiCad incompleto: '+str(file))

    if next(tokens, None) != '(':
        raise ValueError('File KiCad non valido: '+str(file))
    root = gruppo()
    if root[0] != 'kicad_pcb' or next(tokens, None) is not None:
        raise ValueError('Atteso un PCB KiCad: '+str(file))

    def campo(nodo, nome):
        return next((x[1:] for x in nodo if isinstance(x, list) and x and x[0] == nome), [])

    fori, connettori = {}, {}
    for fp in root:
        if not isinstance(fp, list) or not fp or fp[0] != 'footprint':
            continue
        props = {x[1]: x[2] for x in fp if isinstance(x, list) and x and x[0] == 'property'}
        ref = props.get('Reference', '')
        at = campo(fp, 'at')
        if len(at) < 2:
            raise ValueError('Footprint senza posizione: '+ref)
        x, y = map(float, at[:2])
        angolo = float(at[2]) if len(at) > 2 else 0.0
        if str(fp[1]).startswith('MountingHole:'):
            pads = [p for p in fp if isinstance(p, list) and p and p[0] == 'pad']
            if len(pads) != 1:
                raise ValueError('Mounting hole non supportato: '+ref)
            pad = pads[0]
            drill = campo(pad, 'drill')
            offset = campo(pad, 'at')
            if pad[2] != 'np_thru_hole' or len(drill) != 1 or not offset or any(abs(float(v)) > 1e-8 for v in offset[:2]):
                raise ValueError('Serve un foro circolare NPTH centrato nel footprint: '+ref)
            fori[ref] = dict(x=x, y=y, diametro=float(drill[0]))
        if re.fullmatch(r'J\d+', ref):
            connettori[ref] = dict(x=x, y=y, rotazione=angolo,
                                    lato=campo(fp, 'layer')[0], valore=props.get('Value', ''))
    if not fori:
        raise ValueError('Nessun mounting hole nel PCB: '+str(file))
    return dict(fori=fori, connettori=connettori)


def monta(scheda, dati_pcb, telaio, origine_step):
    """Calcola una posa rigida XY + Z; tutti i fissaggi devono coincidere esattamente."""
    h, gradi = scheda['altezza_distanziale'], scheda['rotazione']
    if len(origine_step) != 2 or not all(math.isfinite(v) for v in (h, gradi, *origine_step)) or h < 0:
        raise ValueError('Altezza, rotazione o origine STEP non valide: '+scheda['nome'])
    if not scheda['fissaggi']:
        raise ValueError('Specificare almeno un foro di riferimento per '+scheda['nome'])
    pezzi = {p['nome']: p for p in telaio['pezzi']}
    co, si = math.cos(math.radians(gradi)), math.sin(math.radians(gradi))

    def ruota(x, y):
        return co*x-si*y, si*x+co*y

    traslazione = None
    fissaggi = []
    usati_pcb, usati_telaio = set(), set()
    for f in scheda['fissaggi']:
        ref, nome, n = f['foro_pcb'], f['pezzo_telaio'], f['foro_telaio']
        if ref in usati_pcb or (nome, n) in usati_telaio:
            raise ValueError('Fissaggio duplicato: '+scheda['nome']+'/'+ref)
        usati_pcb.add(ref)
        usati_telaio.add((nome, n))
        pcb, p = dati_pcb['fori'][ref], pezzi[nome]
        if type(n) is not int or not 1 <= n <= p['numero_fori']:
            raise ValueError('Numero foro telaio non valido: '+nome)
        a = math.radians(p['angolo'])
        x = p['origine'][0]+(n-1)*telaio['passo']*math.cos(a)
        y = p['origine'][1]+(n-1)*telaio['passo']*math.sin(a)
        z = telaio['base_z']+(p['livello']+1)*telaio['spessore']
        # KiCad usa Y verso il basso; lo STEP usa Y verso l'alto e PCB inferiore Z=0.
        rx, ry = ruota(pcb['x']-origine_step[0], origine_step[1]-pcb['y'])
        t = (x-rx, y-ry, z+h)
        if traslazione is None:
            traslazione = t
        elif math.dist(traslazione, t) > 1e-5:
            raise ValueError('Fissaggio incompatibile: %s/%s su %s foro %d; scarto %.3f mm. Nessuna correzione automatica.' %
                             (scheda['nome'], ref, nome, n, math.dist(traslazione, t)))
        fissaggi.append(dict(foro_pcb=ref, centro=[x, y], z_appoggio=z, altezza=h))
    return dict(traslazione=traslazione, rotazione=gradi, fissaggi=fissaggi)
