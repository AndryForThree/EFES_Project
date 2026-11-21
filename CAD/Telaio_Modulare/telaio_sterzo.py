"""Regole del telaio piano. Solo quote e fori: nessuna dipendenza da FreeCAD."""
import math


def piano_telaio(punti, passo=10.0, fori_longheroni=20, rientro_fori=1):
    """Pezzi generici e giunti individuati con (nome istanza, numero foro)."""
    if (not isinstance(fori_longheroni, int) or fori_longheroni < 9
            or rientro_fori not in (1, 2) or not math.isfinite(passo) or passo <= 0):
        raise ValueError('Telaio: almeno 9 fori per longherone e rientro di 1 o 2 fori.')
    sx, dx = punti['A_SX'], punti['A_DX']
    interasse = dx[0]-sx[0]
    n = round(interasse/passo)
    if abs(dx[1]-sx[1]) > 1e-6 or n < 1 or abs(n*passo-interasse) > 1e-6:
        raise ValueError('Telaio EiTech: perni allineati su X e interasse multiplo del passo; geometria non arrotondata.')
    sinistra = sx[0]+rientro_fori*passo
    destra = dx[0]-rientro_fori*passo
    if destra-sinistra <= 8*passo:
        raise ValueError('Telaio troppo stretto per quattro diagonali con attacchi 3/4 fori dagli angoli.')
    y0, y1 = sx[1], sx[1]+(fori_longheroni-1)*passo
    pezzi, giunti = [], []

    def pezzo(nome, fori, origine, angolo, livello):
        pezzi.append(dict(nome=nome, tipo='piattina_forata', numero_fori=fori,
                          origine=origine, angolo=angolo, livello=livello))

    pezzo('Traversa_anteriore', n+1, (sx[0], y0), 0, 2)
    pezzo('Traversa_posteriore', n+1, (sx[0], y1), 0, 2)
    for lato, x in (('SX', sinistra), ('DX', destra)):
        nome = 'Longherone_'+lato
        pezzo(nome, fori_longheroni, (x, y0), 90, 1)
        foro_traversa = rientro_fori+1 if lato == 'SX' else n-rientro_fori+1
        for estremita, indice in (('anteriore', 1), ('posteriore', fori_longheroni)):
            giunti.append(dict(nome='Angolo_'+estremita+'_'+lato,
                               fori=[(nome, indice), ('Traversa_'+estremita, foro_traversa)]))
            # Triangolo 3-4-5: foro 2 sul longherone e foro 7 sulla traversa.
            segno_x = 1 if lato == 'SX' else -1
            segno_y = 1 if estremita == 'anteriore' else -1
            y = y0 if estremita == 'anteriore' else y1
            a = (x, y+segno_y*3*passo)
            b = (x+segno_x*4*passo, y)
            ux, uy = (b[0]-a[0])/(5*passo), (b[1]-a[1])/(5*passo)
            diagonale = 'Diagonale_'+estremita+'_'+lato
            pezzo(diagonale, 7, (a[0]-ux*passo, a[1]-uy*passo),
                  math.degrees(math.atan2(uy, ux)), 0)
            giunti += [dict(nome=diagonale+'_longherone',
                            fori=[(diagonale, 2), (nome, 4 if segno_y == 1 else fori_longheroni-3)]),
                       dict(nome=diagonale+'_traversa',
                            fori=[(diagonale, 7), ('Traversa_'+estremita, foro_traversa+segno_x*4)])]
    return dict(pezzi=pezzi, giunti=giunti, interasse=interasse,
                larghezza=destra-sinistra, profondita=y1-y0)


def centro_foro(pezzo, numero, passo):
    if not 1 <= numero <= pezzo['numero_fori']:
        raise ValueError('Foro esterno al pezzo '+pezzo['nome'])
    angolo = math.radians(pezzo['angolo'])
    return (pezzo['origine'][0]+(numero-1)*passo*math.cos(angolo),
            pezzo['origine'][1]+(numero-1)*passo*math.sin(angolo))


def supporto_motore(piano, m, passo=10.0, shift_fori=0):
    """Base sotto M; angolari a cavallo dei longheroni, senza correggere la configurazione."""
    if not isinstance(shift_fori, int):
        raise ValueError('Shift angolari: numero intero di fori.')
    pezzi = {p['nome']: p for p in piano['pezzi']}
    sx, dx = pezzi['Longherone_SX'], pezzi['Longherone_DX']
    xl, xr = sx['origine'][0], dx['origine'][0]
    intervalli = round((xr-xl)/passo)
    avanzo = 19-intervalli
    if avanzo < 0:
        raise ValueError('Gli angolari da 20 fori non raggiungono entrambi i longheroni: larghezza massima 190 mm.')
    # Lo scorrimento cambia gli sbalzi, senza perdere nessuno dei due fissaggi.
    sbalzo_sx = avanzo//2-shift_fori
    if not 0 <= sbalzo_sx <= avanzo:
        raise ValueError('SHIFT_ANGOLARI_FORI deve essere fra %d e %d per mantenere entrambi i fissaggi.' %
                         (avanzo//2-avanzo, avanzo//2))
    x0 = xl-sbalzo_sx*passo
    y0 = sx['origine'][1]
    # La base segue esattamente M, anche fuori griglia o in interferenza con lo sterzo.
    ys = (m[1]-2*passo, m[1]+2*passo)
    angolari, giunti = [], []
    griglia_valida = True
    for nome, y, lato in (('SX', ys[0], -1), ('DX', ys[1], 1)):
        fila = (y-y0)/passo
        foro_esatto = abs(fila-round(fila)) < 1e-6 and 0 <= round(fila) < sx['numero_fori']
        griglia_valida = griglia_valida and foro_esatto
        angolari.append(dict(nome='Trasmissione_Angolare_20_'+nome, origine=(x0, y), lato=lato))
        for longherone, x in ((sx, xl), (dx, xr)):
            giunti.append(dict(centro=(x, y), angolare=angolari[-1]['nome'],
                               foro_angolare=round((x-x0)/passo)+1,
                               longherone=longherone['nome'],
                               foro_longherone=round(fila)+1 if foro_esatto else None))
    # Il corpo motore deve puntare verso l'interno; M resta quello del simulatore.
    verso = 1 if m[0] <= (xl+xr)/2 else -1
    angolo = -90 if verso == 1 else 90
    bordo_x = m[0]-verso*2*passo
    origine_piastra = (bordo_x, ys[1] if verso == 1 else ys[0])
    return dict(angolari=angolari, giunti=giunti, angolo_motore=angolo,
                origine_piastra=origine_piastra, file=ys, griglia_valida=griglia_valida,
                estremi_piastra_x=(bordo_x, bordo_x+verso*8*passo))
