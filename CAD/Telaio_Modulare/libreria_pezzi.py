"""Geometrie generiche, in mm. Nessun nome o collegamento specifico del telaio."""
import FreeCAD as App
import Part

V = App.Vector


def attacco(x, y, spessore, diametro):
    # Le normali escono dal materiale; i due lati identificano le facce di appoggio.
    return {
        'diametro': diametro,
        'sopra': App.Placement(V(x, y, spessore), App.Rotation()),
        'sotto': App.Placement(V(x, y, 0), App.Rotation(V(1, 0, 0), 180)),
    }


def piattina_forata(p, passo):
    n = p.get('numero_fori', 11)
    larghezza = float(p.get('larghezza', 10))
    spessore = float(p.get('spessore', 1))
    diametro = float(p.get('diametro_fori', 3.5))
    passo = float(p.get('passo', passo))
    if (not isinstance(n, int) or n < 1 or min(larghezza, spessore, diametro, passo) <= 0
            or diametro >= min(larghezza, passo)):
        raise ValueError('Piattina: numero_fori intero positivo; quote positive, fori inferiori a larghezza/passo.')
    r = larghezza/2
    forma = Part.makeCylinder(r, spessore)
    if n > 1:
        lunghezza_centri = (n-1)*passo
        forma = forma.fuse(Part.makeBox(lunghezza_centri, larghezza, spessore, V(0, -r, 0)))
        forma = forma.fuse(Part.makeCylinder(r, spessore, V(lunghezza_centri, 0, 0)))
    attacchi = {}
    for i in range(n):
        x = i*passo
        forma = forma.cut(Part.makeCylinder(diametro/2, spessore+0.2, V(x, 0, -0.1)))
        attacchi['foro_%d' % (i+1)] = attacco(x, 0, spessore, diametro)
    return forma.removeSplitter(), attacchi, (0.68, 0.71, 0.75)


def distanziale(p, passo):
    h = float(p.get('altezza', 8))
    diametro = float(p.get('diametro', 6))
    foro = float(p.get('diametro_foro', 3.5))
    if min(h, diametro, foro) <= 0 or foro >= diametro:
        raise ValueError('Distanziale: quote positive e foro inferiore al diametro esterno.')
    forma = Part.makeCylinder(diametro/2, h).cut(Part.makeCylinder(foro/2, h))
    return forma, {'foro_1': attacco(0, 0, h, foro)}, (0.18, 0.20, 0.23)


# Per aggiungere un tipo: una funzione come quelle sopra, poi una riga qui.
TIPI = {
    'piattina_forata': piattina_forata,
    'distanziale': distanziale,
}

# Minuteria M3 nominale, filetti semplificati per non appesantire il CAD.
M3 = {'rondella_h': 0.5, 'dado_h': 4.0, 'passo': 0.5, 'diametro': 3.0}


def minuteria_m3(lunghezze):
    """Geometrie condivise: vite con origine sotto testa; rondella/dado dal basso."""
    import math

    def anello(re, ri, h):
        return Part.makeCylinder(re, h).cut(Part.makeCylinder(ri, h))

    argento = (0.74, 0.76, 0.80)
    forme = {'Rondella_M3': (anello(3.5, 1.6, M3['rondella_h']), argento)}
    # Dado autobloccante: metallo e inserto nylon separati, senza filetto elicoidale.
    r = 2.75/math.cos(math.pi/6)  # Chiave 5.5.
    p = [V(r*math.cos(k*math.pi/3), r*math.sin(k*math.pi/3), 0) for k in range(6)]
    dado = Part.Face(Part.makePolygon(p+[p[0]])).extrude(V(0, 0, M3['dado_h']))
    dado = dado.cut(Part.makeCylinder(1.5, 4.0)).cut(Part.makeCylinder(2.1, 1.6, V(0, 0, 2.4)))
    forme['Dado_M3_Autobloccante'] = (dado, argento)
    forme['Inserto_Nylon_M3'] = (anello(2.1, 1.5, 1.6), (0.08, 0.09, 0.11))
    for lunghezza in lunghezze:
        vite = Part.makeCylinder(1.5, lunghezza, V(0, 0, -lunghezza)).fuse(
            Part.makeCylinder(2.75, 3.0))
        r = 1.25/math.cos(math.pi/6)  # Brugola 2.5.
        p = [V(r*math.cos(k*math.pi/3), r*math.sin(k*math.pi/3), 1.7) for k in range(6)]
        cava = Part.Face(Part.makePolygon(p+[p[0]])).extrude(V(0, 0, 1.4))
        forme['Vite_M3x%d' % lunghezza] = (vite.cut(cava), argento)
    return forme


def biella(interasse, larghezza=10, spessore=1, foro=3.5, passo=10, fori_extra=()):
    """Asta fra due centri. Fori intermedi solo se l'interasse e' multiplo del passo."""
    if min(interasse, larghezza, spessore, foro, passo) <= 0 or foro >= larghezza:
        raise ValueError('Biella: quote positive e foro minore della larghezza.')
    r = larghezza/2
    forma = Part.makeBox(interasse, larghezza, spessore, V(0, -r, 0))
    forma = forma.fuse(Part.makeCylinder(r, spessore)).fuse(
        Part.makeCylinder(r, spessore, V(interasse, 0, 0)))
    n = round(interasse/passo)
    centri = [i*passo for i in range(n+1)] if abs(n*passo-interasse) < 1e-6 else [0, interasse]
    for x in fori_extra:
        if not 0 <= x <= interasse:
            raise ValueError('Biella: foro extra esterno alla distanza fra i centri.')
        if all(abs(x-c) > 1e-6 for c in centri):
            centri.append(x)
    for x in centri:
        forma = forma.cut(Part.makeCylinder(foro/2, spessore+0.2, V(x, 0, -0.1)))
    return forma.removeSplitter()


def piastra_forata(p, passo):
    """Origine sul primo foro. Griglia colonne X per righe Y."""
    nx, ny = p.get('colonne', 5), p.get('righe', 9)
    h, d = p.get('spessore', 1.0), p.get('diametro_fori', 3.5)
    if min(nx, ny) < 1 or min(h, d, passo) <= 0 or d >= passo:
        raise ValueError('Piastra: griglia positiva, fori inferiori al passo.')
    forma = Part.makeBox(nx*passo, ny*passo, h, V(-passo/2, -passo/2, 0))
    attacchi = {}
    for j in range(ny):
        for i in range(nx):
            forma = forma.cut(Part.makeCylinder(d/2, h+0.2, V(i*passo, j*passo, -0.1)))
            attacchi['foro_%d_%d' % (i+1, j+1)] = attacco(i*passo, j*passo, h, d)
    return forma, attacchi, (0.68, 0.71, 0.75)


def longherone_angolare(p, passo):
    """L lungo X, fori su entrambe le ali; origine sul primo foro piano."""
    n = p.get('numero_fori', 20)
    h, ala = p.get('spessore', 1.0), p.get('ala', 10.0)
    d, lato = p.get('diametro_fori', 3.5), p.get('lato', 1)
    if n < 1 or not 0 < d < ala or not 0 < h < ala or lato not in (-1, 1):
        raise ValueError('Angolare: quote non valide.')
    lunghezza = (n-1)*passo+ala
    forma = Part.makeBox(lunghezza, ala, h, V(-ala/2, -ala/2, 0))
    parete_y = ala/2-h if lato == 1 else -ala/2
    if p.get('parete_esterna', False):
        parete_y += lato*h
    forma = forma.fuse(Part.makeBox(lunghezza, h, ala, V(-ala/2, parete_y, 0)))
    attacchi = {}
    for i in range(n):
        x = i*passo
        forma = forma.cut(Part.makeCylinder(d/2, h+0.2, V(x, 0, -0.1)))
        forma = forma.cut(Part.makeCylinder(d/2, ala+2, V(x, -ala/2-1, ala/2), V(0, 1, 0)))
        attacchi['foro_%d' % (i+1)] = attacco(x, 0, h, d)
    return forma.removeSplitter(), attacchi, (0.68, 0.71, 0.75)


def disco_forato_mozzo(p, passo):
    """Disco XY a Z=0 con mozzo sotto e grano radiale. Foratura EiTech indicativa."""
    import math
    r, h = p.get('raggio', 30.0), p.get('spessore', 1.0)
    ri, rm, hm = p.get('foro_asse', 4.0)/2, p.get('diametro_mozzo', 12.0)/2, p.get('altezza_mozzo', 10.0)
    d = p.get('diametro_fori', 3.5)
    if not 0 < ri < rm < r or min(h, hm, d) <= 0:
        raise ValueError('Disco: quote non valide.')
    forma = Part.makeCylinder(r, h).fuse(Part.makeCylinder(rm, hm, V(0, 0, -hm)))
    forma = forma.cut(Part.makeCylinder(ri, hm+h+0.2, V(0, 0, -hm-0.1)))
    forma = forma.cut(Part.makeCylinder(1.5, rm+1, V(0, 0, -hm/2), V(1, 0, 0)))
    attacchi = {}
    if p.get('foratura_circolare', False):
        # Schema visivo dalla foto: corona esterna e fori interni; quote da verificare.
        centri = [(('esterno_%d' % (k+1)), (r-passo/2)*math.cos(k*math.tau/12),
                   (r-passo/2)*math.sin(k*math.tau/12)) for k in range(12)]
        centri += [('interno_%d_%d' % (i, j), i*passo, j*passo)
                   for i in (-1, 0, 1) for j in (-1, 0, 1) if (i, j) != (0, 0)]
        centri += [('fissaggio_prima', -2*passo, 0), ('fissaggio_dopo', 2*passo, 0)]
    else:
        n = int(r//passo)
        centri = [('foro_%d_%d' % (i, j), i*passo, j*passo)
                  for i in range(-n, n+1) for j in range(-n, n+1)]
    for nome, x, y in centri:
        if rm+d/2 < math.hypot(x, y) < r-d/2-1:
            forma = forma.cut(Part.makeCylinder(d/2, h+0.2, V(x, y, -0.1)))
            attacchi[nome] = attacco(x, y, h, d)
    return forma.removeSplitter(), attacchi, (0.68, 0.71, 0.75)


def giunto_assi(p, passo):
    """Manicotto assiale Z con due sedi per grani, senza filetti elicoidali."""
    h, re = p.get('lunghezza', 20.0), p.get('diametro', 10.0)/2
    ri = p.get('foro_asse', 4.0)/2
    if not 0 < ri < re or h <= 0:
        raise ValueError('Giunto: quote non valide.')
    forma = Part.makeCylinder(re, h).cut(Part.makeCylinder(ri, h))
    for z in (h/4, 3*h/4):
        forma = forma.cut(Part.makeCylinder(1.5, re+1, V(0, 0, z), V(1, 0, 0)))
    return forma, {}, (0.08, 0.09, 0.10)


def ruota_conica(p, passo):
    """Cono dentato illustrativo, NON dentatura evolvente utilizzabile per fabbricare."""
    r, h, foro = p.get('raggio', 12.0), p.get('altezza', 7.0), p.get('foro_asse', 4.0)
    denti = p.get('denti', 20)
    if not 0 < foro/2 < r*0.45 or h <= 0 or denti < 6:
        raise ValueError('Ruota conica: quote non valide.')
    forma = Part.makeCone(r, r*0.45, h)
    # Scanalature radiali coniche: pochi solidi, silhouette riconoscibile.
    for i in range(denti):
        cava = Part.makeBox(r, 0.8, h+0.2, V(r*0.62, -0.4, -0.1))
        cava.rotate(V(), V(0, 0, 1), i*360/denti)
        forma = forma.cut(cava)
    forma = forma.fuse(Part.makeCylinder(4, 6, V(0, 0, -6)))
    forma = forma.cut(Part.makeCylinder(foro/2, h+6.2, V(0, 0, -6.1)))
    forma = forma.cut(Part.makeCylinder(1.5, 5, V(0, 0, -3), V(1, 0, 0)))
    return forma.removeSplitter(), {}, (0.065, 0.07, 0.08)


def componenti_ga25(p):
    """Asse Z uscente, faccia riduttore Z=0. Quote dal PDF locale JGA25-370, pagina 2.

    L riduttore 21, motore 30.8, diametri 25/24.4, uscita 11.5 e albero D4.
    Estetica fondello/terminali stimata; identificare la variante reale prima di fissaggi precisi.
    """
    l = p.get('lunghezza_riduttore', 21.0)
    if l <= 0:
        raise ValueError('Riduttore: lunghezza positiva.')
    riduttore = Part.makeCylinder(12.5, l, V(0, 0, -l))
    for x in (-8.5, 8.5):
        riduttore = riduttore.cut(Part.makeCylinder(1.5, 3.5, V(x, 0, -3.5)))
    collare = Part.makeCylinder(3.5, 2.5)
    albero = Part.makeCylinder(2, 11.5).cut(Part.makeBox(4, 2, 8.1, V(-2, 1.5, 3.5)))
    return {
        'Riduttore': (riduttore, (0.52, 0.54, 0.56)),
        'Corpo': (Part.makeCylinder(12.2, 30.8, V(0, 0, -l-30.8)), (0.72, 0.72, 0.69)),
        'Collare': (collare, (0.58, 0.50, 0.34)),
        'Albero_D4': (albero, (0.78, 0.79, 0.80)),
        'Fondello': (Part.makeCylinder(11, 1, V(0, 0, -l-31.8)), (0.17, 0.18, 0.18)),
        'Terminale_1': (Part.makeBox(1, 3, 0.5, V(-8, -1.5, -l-32.3)), (0.69, 0.52, 0.28)),
        'Terminale_2': (Part.makeBox(1, 3, 0.5, V(7, -1.5, -l-32.3)), (0.69, 0.52, 0.28)),
    }


def motore_ga25(p, passo):
    return Part.makeCompound([f for f, _ in componenti_ga25(p).values()]), {}, (0.65, 0.66, 0.65)


TIPI.update(piastra_forata=piastra_forata, longherone_angolare=longherone_angolare,
            disco_forato_mozzo=disco_forato_mozzo, giunto_assi=giunto_assi,
            ruota_conica=ruota_conica, motore_ga25=motore_ga25)


def piattina_diametrale(p, passo):
    """Piattina con foro asse nel centro di riferimento e fori M3 sui due lati."""
    prima, dopo = p.get('fori_prima', 2), p.get('fori_dopo', 2)
    if not isinstance(prima, int) or not isinstance(dopo, int) or min(prima, dopo) < 1:
        raise ValueError('Piattina diametrale: almeno un intervallo su ciascun lato del centro.')
    forma, _, colore = piattina_forata(dict(numero_fori=prima+dopo+1,
        larghezza=p.get('larghezza', 10), spessore=p.get('spessore', 1),
        diametro_fori=p.get('diametro_fori', 3.5)), passo)
    forma.translate(V(-prima*passo, 0, 0))
    h, asse = p.get('spessore', 1), p.get('foro_asse', 4.2)
    if not 0 < asse < p.get('larghezza', 10):
        raise ValueError('Piattina: foro asse minore della larghezza.')
    forma = forma.cut(Part.makeCylinder(asse/2, h+0.2, V(0, 0, -0.1)))
    attacchi = {'centro': attacco(0, 0, h, asse)}
    for i in range(-prima, dopo+1):
        if i:
            attacchi['foro_%+d' % i] = attacco(i*passo, 0, h, p.get('diametro_fori', 3.5))
    return forma.removeSplitter(), attacchi, colore


TIPI['piattina_diametrale'] = piattina_diametrale
