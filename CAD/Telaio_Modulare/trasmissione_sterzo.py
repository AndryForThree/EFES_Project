"""Montaggio indicativo della trasmissione, centrato sull'asse M esportato dal simulatore."""
import math
import FreeCAD as App
import Part

V = App.Vector
METALLO = (0.68, 0.71, 0.75)
NERO = (0.07, 0.08, 0.09)
STIMA = 'Quote EiTech indicative dalle foto; ingombro di riferimento, non disegno costruttivo.'


def genera(punti, quota_disco, quota_piano, impostazioni, libreria, aggiungi, minuteria=True):
    passo, s = impostazioni['passo'], impostazioni['spessore']
    foro, diam_asse = impostazioni['foro'], impostazioni['diametro_asse']
    r = impostazioni['raggio_disco']
    m, q = punti['M'], punti['Q']
    rotazione = impostazioni['angolo_motore']  # 0: motore verso +Y, ingresso alberino verso -Y.
    orientamento = App.Rotation(V(0, 0, 1), rotazione)
    base = V(*m, quota_piano)
    supporto_telaio = impostazioni['supporto_telaio']

    def posa(nome, forma, colore, posizione, asse=V(0, 0, 1), nota=STIMA):
        forma = forma.copy()
        forma.rotate(V(), App.Rotation(V(0, 0, 1), asse).Axis,
                     App.Rotation(V(0, 0, 1), asse).Angle*180/math.pi)
        # Ogni pezzo e' prima orientato nel riferimento del modulo, poi sul telaio.
        forma.Placement = App.Placement(base, orientamento).multiply(
            App.Placement(V(*posizione), App.Rotation())).multiply(forma.Placement)
        aggiungi(nome, forma, colore, nota)

    def posa_telaio(nome, forma, colore, posizione, nota=STIMA):
        forma = forma.copy()
        forma.translate(V(*posizione))
        aggiungi(nome, forma, colore, nota)

    # Piastra e angolari seguono M: nessun arretramento per evitare lo sterzo.
    p = dict(colonne=5, righe=9, spessore=s, diametro_fori=foro)
    forma, _, colore = libreria.piastra_forata(p, passo)
    forma.rotate(V(), V(0, 0, 1), rotazione)
    posa_telaio('Trasmissione_Piastra_9x5', forma, colore,
                (*supporto_telaio['origine_piastra'], quota_piano))
    for angolare in supporto_telaio['angolari']:
        forma, _, colore = libreria.longherone_angolare(dict(numero_fori=20,
            spessore=s, diametro_fori=foro, lato=angolare['lato'], parete_esterna=True), passo)
        posa_telaio(angolare['nome'], forma, colore, (*angolare['origine'], quota_piano-s),
                    nota=STIMA+' Posato sotto il motore, a cavallo dei longheroni; compatibilita dei fori da verificare.')

    if not supporto_telaio['griglia_valida']:
        App.Console.PrintWarning('Base motore segue M fuori griglia: attacchi ai longheroni da verificare. Posizione mantenuta.\n')

    # Il GA25 posa sul piano; modello dal PDF locale JGA25-370, pagina 2.
    z_albero = s+12.5
    fronte = 41.0
    for nome, (forma, colore) in libreria.componenti_ga25({}).items():
        posa('GA25_'+nome, forma, colore, (0, fronte, z_albero), V(0, -1, 0),
             'Riferimento: Datasheets/Motor/JGA25-370.PDF, pagina 2. Variante reale da verificare.')
    # Le due staffette attuali sono semplici L, non una nuova base stampata.
    for segno in (-1, 1):
        staffa = Part.makeBox(8, 10, s, V(-4, 0, 0)).fuse(
            Part.makeBox(8, s, 15, V(-4, 0, 0)))
        staffa = staffa.cut(Part.makeCylinder(foro/2, s+0.2, V(0, 5, -0.1)))
        staffa = staffa.cut(Part.makeCylinder(1.6, s+0.2, V(0, -0.1, 12.5), V(0, 1, 0)))
        posa('Staffa_motore_'+('SX' if segno < 0 else 'DX'), staffa, METALLO,
             (segno*8.5, fronte-s, s), nota='Staffetta L attuale, ingombro stimato; fori a terra da verificare.')
        if minuteria:
            vite = Part.makeCylinder(1.5, 4).fuse(Part.makeCylinder(2.75, 3, V(0, 0, -3)))
            posa('Vite_frontale_GA25_'+str(segno), vite, METALLO,
                 (segno*8.5, fronte-s, z_albero), V(0, 1, 0),
                 'M3x4 indicativa: tratto nel riduttore max 3.5 mm nel PDF. Lunghezza di acquisto da verificare sulle staffe.')

    forma, _, colore = libreria.giunto_assi(dict(lunghezza=20, foro_asse=diam_asse), passo)
    posa('Giunto_assi_D4', forma, colore, (0, 18, z_albero), V(0, 1, 0))
    posa('Asse_orizzontale_D4', Part.makeCylinder(diam_asse/2, 29.5), METALLO,
         (0, 0, z_albero), V(0, 1, 0))
    altezza_asse = quota_disco-quota_piano+15-s
    if altezza_asse <= 0:
        raise ValueError('Quota disco inferiore al piano della trasmissione.')
    posa('Asse_verticale_D4', Part.makeCylinder(diam_asse/2, altezza_asse), METALLO, (0, 0, s))
    # Coppia conica 1:1 riconoscibile; dentatura solamente illustrativa.
    rg = 12.0
    denti_coniche = 22  # EiTech 01481: numero di denti ufficiale; ingombri ancora da misurare.
    forma, _, colore = libreria.ruota_conica(dict(foro_asse=diam_asse, denti=denti_coniche), passo)
    nota_coniche = 'EiTech 01481: 22 denti confermati dal produttore. Diametro, altezza e profilo denti indicativi.'
    posa('Ruota_conica_verticale', forma, colore, (0, 0, z_albero+rg), V(0, 0, -1), nota_coniche)
    posa('Ruota_conica_orizzontale', forma, colore, (0, rg, z_albero), V(0, -1, 0), nota_coniche)
    supporto = Part.makeCylinder(5, 7).cut(Part.makeCylinder(diam_asse/2+0.1, 7))
    posa('Supporto_inferiore_asse', supporto, NERO, (0, 0, s),
         nota='Supporto asse indicativo, fissaggio verticale da completare.')

    # Disco in coordinate globali: M e Q sono esattamente quelli del simulatore.
    forma, _, colore = libreria.disco_forato_mozzo(dict(raggio=r, spessore=s,
        foro_asse=diam_asse, altezza_mozzo=5, diametro_fori=foro, foratura_circolare=True), passo)
    dx, dy = q[0]-m[0], q[1]-m[1]
    fase = math.degrees(math.atan2(dy, dx))
    forma.rotate(V(), V(0, 0, 1), fase)
    # Foro Q teorico esplicito: non presume che esista nella foratura reale EiTech.
    forma = forma.cut(Part.makeCylinder(foro/2, s+0.2, V(dx, dy, -0.1)))
    forma.translate(V(*m, quota_disco))
    aggiungi('Manovella_motore', forma, colore,
             'EiTech 01161: diametro nominale 50 mm; raggio configurato %.2f mm. ' % r
             +STIMA+' Foratura su corona; due fissaggi diametrali. Foro Q teorico dal simulatore.')
    distanza_q = math.hypot(dx, dy)
    dopo = max(2, math.ceil(distanza_q/passo))
    piattina, _, colore_piattina = libreria.piattina_diametrale(dict(fori_prima=2,
        fori_dopo=dopo, larghezza=impostazioni['larghezza_asta'], spessore=s,
        diametro_fori=foro, foro_asse=diam_asse+0.2), passo)
    piattina = piattina.cut(Part.makeCylinder(foro/2, s+0.2, V(distanza_q, 0, -0.1)))
    piattina.rotate(V(), V(0, 0, 1), fase)
    piattina.translate(V(*m, quota_disco+s))
    aggiungi('Piattina_diametrale_mozzo', piattina, colore_piattina,
             'Passa per M con foro asse; fissata al disco nei fori -20 e +20 mm. Q resta quello del simulatore.')
    if distanza_q < 2*passo+6:
        App.Console.PrintWarning('Leva motore corta: verificare interferenza del giunto Q con la vite di fissaggio a +20 mm. CAD mantenuto.\n')
    raggio_q = math.hypot(dx, dy)
    if raggio_q > r-foro/2:
        App.Console.PrintWarning('Attacco Q a %.2f mm: esterno al disco da raggio %.2f mm. CAD mantenuto.\n' % (raggio_q, r))
    elif abs(dx/passo-round(dx/passo)) > 1e-6 or abs(dy/passo-round(dy/passo)) > 1e-6:
        App.Console.PrintWarning('Foro Q teorico sul disco: non coincide con la griglia disegnata. Verificare il pezzo EiTech.\n')
    if minuteria:
        # Grani senza filetto, con taglio visibile. Separati dai componenti.
        grano = Part.makeCylinder(1.5, 3).cut(Part.makeBox(0.6, 4, 0.8, V(-0.3, -2, -0.1)))
        for y in (23, 33):
            posa('Grano_giunto_'+str(y), grano, METALLO, (5, y, z_albero), V(-1, 0, 0))
        posa('Grano_conica_verticale', grano, METALLO, (4, 0, z_albero+rg+3), V(-1, 0, 0))
        posa('Grano_conica_orizzontale', grano, METALLO, (4, rg+3, z_albero), V(-1, 0, 0))
        grano_disco = grano.copy()
        grano_disco.rotate(V(), V(0, 1, 0), -90)
        grano_disco.translate(V(6, 0, -2.5))
        grano_disco.rotate(V(), V(0, 0, 1), fase)
        grano_disco.translate(V(*m, quota_disco))
        aggiungi('Grano_disco_M3', grano_disco, METALLO, 'Grano radiale M3 indicativo.')
        # Due viti passanti ai lati opposti del centro: disco + piattina.
        hw_disco = libreria.minuteria_m3((12,))
        for lato, x in (('prima', -2*passo), ('dopo', 2*passo)):
            direzione = V(math.cos(math.radians(fase)), math.sin(math.radians(fase)), 0)
            centro = V(*m, 0)+direzione*x
            for j, (nome, z) in enumerate((('Vite_M3x12', quota_disco+2*s+0.5),
                ('Rondella_M3', quota_disco+2*s), ('Rondella_M3', quota_disco-0.5),
                ('Dado_M3_Autobloccante', quota_disco-4.5), ('Inserto_Nylon_M3', quota_disco-2.1))):
                forma, colore = hw_disco[nome]
                posa_telaio('Fissaggio_disco_%s_%s_%d' % (lato, nome, j), forma, colore, (centro.x, centro.y, z),
                             nota='Vite-rondella-piattina-disco-rondella-dado M3, ai lati opposti di M.')
        App.Console.PrintMessage('Disco-piattina: 2 viti M3x12, 4 rondelle e 2 dadi autobloccanti.\n')
        # Un solo bullone quando attacco piastra e attacco telaio usano lo stesso foro.
        attacchi = {}
        def giunto(centro, basso, alto):
            chiave = tuple(round(v, 6) for v in centro)
            precedente = attacchi.get(chiave, (basso, alto))
            attacchi[chiave] = (min(basso, precedente[0]), max(alto, precedente[1]))
        for x in supporto_telaio['estremi_piastra_x']:
            for y in supporto_telaio['file']:
                giunto((x, y), quota_piano-s, quota_piano+s)
        for g in supporto_telaio['giunti']:
            giunto(g['centro'], quota_piano-2*s, quota_piano)
        hw = libreria.minuteria_m3((12,))
        for i, ((x, y), (basso, alto)) in enumerate(attacchi.items()):
            for j, (nome, z) in enumerate((('Vite_M3x12', alto+0.5), ('Rondella_M3', alto),
                ('Rondella_M3', basso-0.5), ('Dado_M3_Autobloccante', basso-4.5), ('Inserto_Nylon_M3', basso-2.1))):
                forma, colore = hw[nome]
                posa_telaio('Fissaggio_piastra_%d_%s_%d' % (i+1, nome, j), forma, colore, (x, y, z),
                            nota='Attacco a fori telaio/piastra, bullone unico per i fori condivisi.')
        n = len(attacchi)
        App.Console.PrintMessage('Fissaggi modulo: %d M3x12, %d rondelle, %d dadi autobloccanti; 2 M3x4 frontali e 5 grani M3 indicativi.\n' % (n, 2*n, n))
    # Nessun test di collisione: l'utente deve poter vedere anche configurazioni incompatibili.
    App.Console.PrintMessage('Trasmissione: piastra 9x5, angolari 20 fori, GA25 orizzontale, coppia conica e disco con grano.\n')
    App.Console.PrintMessage('Quote EiTech e montaggio Z indicativi; collisioni non bloccanti.\n')

    asse_orizzontale = orientamento.multVec(V(0, 1, 0))
    return dict(origine_asse=[m[0], m[1], quota_piano+z_albero],
                direzione_asse=[asse_orizzontale.x, asse_orizzontale.y, asse_orizzontale.z],
                denti_verticale=denti_coniche, denti_orizzontale=denti_coniche, quote_verificate=False)
