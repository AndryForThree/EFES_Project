"""Pose dal simulatore e intersezioni volumetriche della posa corrente. Nessun solver duplicato."""
import json
import math
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

V = App.Vector
VOLUME_MINIMO = 0.001  # mm^3, soglia numerica dell'intersezione; non tolleranza di montaggio.
# Contatti intenzionali del modello: ingranamento e collare interno all'albero motore.
CONTATTI_PREVISTI = {
    frozenset(('Ruota_conica_verticale', 'Ruota_conica_orizzontale')),
    frozenset(('GA25_Collare', 'GA25_Albero_D4')),
}


def gruppo_mobile(nome):
    for lato in ('SX', 'DX'):
        if nome in ('Braccio_'+lato, 'Portaruota_'+lato, 'Asse_ruota_'+lato,
                    'Pneumatico_'+lato, 'Mozzo_ruota_'+lato) or nome.startswith('B_'+lato+'_'):
            return 'ruota_'+lato
    if nome in ('Tirante', 'Distanziale_giunto_mobile_T') or nome.startswith('T_'):
        return 'tirante'
    if nome == 'Biella_motore':
        return 'biella'
    if nome in ('Manovella_motore', 'Piattina_diametrale_mozzo', 'Asse_verticale_D4',
                'Grano_disco_M3', 'Ruota_conica_verticale', 'Grano_conica_verticale') or nome.startswith(('Q_', 'Fissaggio_disco_')):
        return 'disco'
    if nome in ('GA25_Albero_D4', 'Giunto_assi_D4', 'Asse_orizzontale_D4',
                'Ruota_conica_orizzontale', 'Grano_conica_orizzontale') or nome.startswith('Grano_giunto_'):
        return 'motore'
    return 'fisso'


def valida_esportazione(data):
    if data.get('version') != 2:
        raise ValueError('Serve il JSON v2: nel simulatore usare Salva > Meccanismo FreeCAD e riesportare.')
    motion = data['motion']
    frames = motion['frames']
    if len(frames) != 201 or motion['neutral_index'] != 100:
        raise ValueError('Cinematica: richieste le 201 pose con posa centrale all\'indice 100.')
    p = data['points']
    zero = frames[100]
    if abs(zero['steering']) > 1e-12:
        raise ValueError('La posa centrale non corrisponde a zero gradi.')
    for nome, punto in zero['points'].items():
        if math.dist(p[nome], punto) > 1e-6:
            raise ValueError('Geometria CAD e posa centrale discordanti: '+nome)
    lunghezze = [(a, b, math.dist(p[a], p[b])) for a, b in
                 (('A_SX', 'B_SX'), ('A_DX', 'B_DX'), ('B_SX', 'B_DX'), ('M', 'Q'), ('Q', 'T'))]
    precedente = -math.inf
    for f in frames:
        numeri = [f[k] for k in ('steering', 'phi', 'theta_left', 'theta_right')]
        numeri += [x for punto in f['points'].values() for x in punto]
        if not all(math.isfinite(x) for x in numeri) or f['steering'] <= precedente:
            raise ValueError('Pose non finite o non ordinate.')
        precedente = f['steering']
        punti = dict(p, **f['points'])
        for a, b, l in lunghezze:
            if abs(math.dist(punti[a], punti[b])-l) > 1e-6:
                raise ValueError('La posa altera un interasse: '+a+'-'+b)
    return frames


def rigido(orig, dest, angolo):
    rot = App.Rotation(V(0, 0, 1), math.degrees(angolo))
    a, b = V(*orig, 0), V(*dest, 0)
    return App.Placement(b-rot.multVec(a), rot)


def direzione(a, b):
    return math.atan2(b[1]-a[1], b[0]-a[0])


class Movimento:
    def __init__(self, doc):
        self.doc = doc
        dati = doc.getObject('Dati_Sterzo')
        if dati is None:
            raise ValueError('Eseguire prima Sterzo.FCMacro con il JSON v2.')
        self.revisione = dati.Revisione
        self.meta = json.loads(dati.DatiJSON)
        self.frames = valida_esportazione(self.meta['export'])
        self.p = self.meta['export']['points']
        self.zero = self.frames[100]
        self.drive = self.meta['trasmissione']
        self.originali = {}
        for o in doc.Objects:
            if hasattr(o, 'GruppoCinematico') and o.GruppoCinematico != 'fisso':
                self.originali[o.Name] = (o.GruppoCinematico, App.Placement(o.Placement))
        if not self.originali:
            raise ValueError('Il documento non contiene componenti cinematici.')
        if any(g == 'motore' for g, _ in self.originali.values()) and self.drive is None:
            raise ValueError('Asse orizzontale e numero denti mancanti nei dati CAD.')
        self.indice = 100

    def valida_documento(self):
        dati = self.doc.getObject('Dati_Sterzo')
        if dati is None or dati.Revisione != self.revisione:
            raise ValueError('CAD rigenerato: chiudere e riaprire la macro movimento.')
        if any(self.doc.getObject(n) is None for n in self.originali):
            raise ValueError('Un componente mobile e stato eliminato: rigenerare il CAD.')

    def applica(self, indice):
        self.valida_documento()
        if not isinstance(indice, int) or not 0 <= indice < len(self.frames):
            raise ValueError('Indice posa fuori dall\'intervallo esportato.')
        f, z, p = self.frames[indice], self.zero, self.p
        punti = f['points']
        trasf = {
            'ruota_SX': rigido(p['A_SX'], p['A_SX'], f['theta_left']-z['theta_left']),
            'ruota_DX': rigido(p['A_DX'], p['A_DX'], f['theta_right']-z['theta_right']),
            'tirante': rigido(p['B_SX'], punti['B_SX'], direzione(punti['B_SX'], punti['B_DX'])-direzione(p['B_SX'], p['B_DX'])),
            'biella': rigido(p['Q'], punti['Q'], direzione(punti['Q'], punti['T'])-direzione(p['Q'], p['T'])),
            'disco': rigido(p['M'], p['M'], f['phi']-z['phi']),
        }
        if self.drive is not None:
            d = self.drive
            rapporto = d['denti_verticale']/d['denti_orizzontale']
            if rapporto <= 0:
                raise ValueError('Numero denti non valido.')
            origine, asse = V(*d['origine_asse']), V(*d['direzione_asse'])
            r = App.Rotation(asse, -math.degrees(f['phi']-z['phi'])*rapporto)
            trasf['motore'] = App.Placement(origine-r.multVec(origine), r)
        pose = {n: trasf[g].multiply(base) for n, (g, base) in self.originali.items()}
        for n, posa in pose.items():
            self.doc.getObject(n).Placement = posa
        self.doc.recompute()
        self.indice = indice

    def ripristina(self):
        self.valida_documento()
        for n, (_, posa) in self.originali.items():
            self.doc.getObject(n).Placement = posa
        self.doc.recompute()


def interferenze(doc):
    schede, sterzo = doc.getObject('Dati_Schede'), doc.getObject('Dati_Sterzo')
    if schede is not None and (sterzo is None or schede.RevisioneSterzo != sterzo.Revisione):
        raise ValueError('Schede riferite a un telaio precedente: eseguire Schede.FCMacro.')
    if any(getattr(o, 'DettaglioScheda', '') == 'ingombri' for o in doc.Objects):
        App.Console.PrintWarning('Schede in vista ingombri: le collisioni con i componenti sono conservative; per la verifica dettagliata usare dettaglio_schede=completo.\n')
    oggetti = [o for o in doc.Objects if hasattr(o, 'Shape') and not o.Shape.isNull()]
    forme = [(o, o.Shape, o.Shape.BoundBox) for o in oggetti]
    risultati = []
    for i, (a, sa, ba) in enumerate(forme):
        if not sa.isValid():
            raise ValueError('Geometria non valida: '+a.Name)
        for b, sb, bb in forme[i+1:]:
            if frozenset((a.Name, b.Name)) in CONTATTI_PREVISTI:
                continue
            if (min(ba.XMax, bb.XMax)-max(ba.XMin, bb.XMin) <= 0 or
                min(ba.YMax, bb.YMax)-max(ba.YMin, bb.YMin) <= 0 or
                min(ba.ZMax, bb.ZMax)-max(ba.ZMin, bb.ZMin) <= 0):
                continue
            comune = sa.common(sb)
            if not comune.isValid():
                raise ValueError('Intersezione non calcolabile: %s / %s' % (a.Name, b.Name))
            if comune.Volume > VOLUME_MINIMO:
                risultati.append((a.Name, b.Name, comune.Volume))
    return risultati


class Pannello(QtWidgets.QDockWidget):
    def __init__(self, doc, parent):
        super().__init__('Sterzo: movimento e interferenze', parent)
        self.setObjectName('EFES_Sterzo_Movimento')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.moto = Movimento(doc)
        self.colori = {}
        self.direzione = 1
        self.chiuso = False
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(50)  # 20 pose/s; nessuna interpolazione.
        self.timer.timeout.connect(self.avanza)
        contenuto = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(contenuto)
        a, b = self.moto.frames[0], self.moto.frames[-1]
        lay.addWidget(QtWidgets.QLabel('201 pose dal simulatore: %.3f° … %.3f°\nRiproduzione a 20 pose/s.' %
                                      (math.degrees(a['steering']), math.degrees(b['steering']))))
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 200)
        self.slider.setValue(100)
        lay.addWidget(self.slider)
        lay.addWidget(QtWidgets.QLabel('Movimento e interferenze riferiti al CAD attuale.\nQuote EiTech ancora da verificare.'))
        self.angolo = QtWidgets.QLabel('Sterzo medio: 0.000°')
        lay.addWidget(self.angolo)
        self.play = QtWidgets.QPushButton('Avvia / pausa')
        lay.addWidget(self.play)
        zero = QtWidgets.QPushButton('Posizione centrale')
        lay.addWidget(zero)
        self.check = QtWidgets.QPushButton('Controlla interferenze nella posa')
        lay.addWidget(self.check)
        self.stato = QtWidgets.QLabel('Controllo volumetrico: soglia 0.001 mm³.\nEsclusi ingranamento e contatto interno collare/albero GA25.')
        self.stato.setWordWrap(True)
        lay.addWidget(self.stato)
        self.lista = QtWidgets.QListWidget()
        lay.addWidget(self.lista)
        self.setWidget(contenuto)
        self.slider.valueChanged.connect(self.sposta)
        self.play.clicked.connect(self.avvio)
        zero.clicked.connect(lambda: self.slider.setValue(100))
        self.check.clicked.connect(self.controlla)
        self.lista.itemDoubleClicked.connect(self.seleziona)
        App.addDocumentObserver(self)

    def errore(self, exc):
        self.timer.stop()
        self.stato.setText('ERRORE: '+str(exc))
        self.play.setEnabled(False)
        self.slider.setEnabled(False)
        self.check.setEnabled(False)
        App.Console.PrintError('Sterzo: '+str(exc)+'\n')

    def pulisci_colori(self):
        for n, (colore, facce) in self.colori.items():
            o = self.moto.doc.getObject(n)
            if o is not None:
                o.ViewObject.ShapeColor = colore
                o.ViewObject.DiffuseColor = facce
        self.colori.clear()

    def sposta(self, indice):
        try:
            self.pulisci_colori()
            self.lista.clear()
            self.moto.applica(indice)
            self.angolo.setText('Sterzo medio: %.3f°' % math.degrees(self.moto.frames[indice]['steering']))
            self.stato.setText('Posa aggiornata. Premi Controlla interferenze per questa posa.')
        except Exception as exc:
            self.errore(exc)

    def avvio(self):
        if self.timer.isActive():
            self.timer.stop()
        else:
            self.timer.start()

    def avanza(self):
        attuale = self.slider.value()
        if (attuale == 200 and self.direzione == 1) or (attuale == 0 and self.direzione == -1):
            self.direzione *= -1
        self.slider.setValue(attuale+self.direzione)

    def controlla(self):
        self.timer.stop()
        self.pulisci_colori()
        self.lista.clear()
        self.stato.setText('Calcolo delle intersezioni…')
        QtWidgets.QApplication.processEvents()
        try:
            self.moto.valida_documento()
            risultati = interferenze(self.moto.doc)
            for a, b, volume in risultati:
                item = QtWidgets.QListWidgetItem('%s / %s — %.4f mm³' % (a, b, volume))
                item.setData(QtCore.Qt.UserRole, (a, b))
                self.lista.addItem(item)
                for n in (a, b):
                    o = self.moto.doc.getObject(n)
                    if n not in self.colori:
                        self.colori[n] = (o.ViewObject.ShapeColor, list(o.ViewObject.DiffuseColor))
                    o.ViewObject.ShapeColor = (1.0, 0.12, 0.08)
                    o.ViewObject.DiffuseColor = [(1.0, 0.12, 0.08)]*len(o.Shape.Faces)
            self.stato.setText('%d coppie in interferenza nella posa %.3f°. Doppio clic per selezionare.' %
                               (len(risultati), math.degrees(self.moto.frames[self.moto.indice]['steering'])))
        except Exception as exc:
            self.errore(exc)

    def seleziona(self, item):
        Gui.Selection.clearSelection()
        for n in item.data(QtCore.Qt.UserRole):
            Gui.Selection.addSelection(self.moto.doc.Name, n)

    def slotDeletedDocument(self, doc):
        if doc.Name == self.moto.doc.Name:
            self.chiuso = True
            self.timer.stop()
            self.close()

    def closeEvent(self, event):
        self.timer.stop()
        App.removeDocumentObserver(self)
        if not self.chiuso:
            self.pulisci_colori()
            self.moto.ripristina()
        self.chiuso = True
        event.accept()
