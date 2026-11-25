"""Import STEP a colori e posizionamento delle schede definite in schede.json."""
import importlib.util
import hashlib
import json
import re
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
import ImportGui
import Part
from PySide import QtWidgets

V = App.Vector


def alleggerisci(forma, substrato):
    """PCB: contorno e aperture >=1.5 mm. Componenti: ingombro rettangolare."""
    bb = forma.optimalBoundingBox(False)
    if not substrato:
        if min(bb.XLength, bb.YLength, bb.ZLength) <= 1e-7:
            raise ValueError('Componente STEP senza volume: impossibile generarne l\'ingombro.')
        return Part.makeBox(bb.XLength, bb.YLength, bb.ZLength, V(bb.XMin, bb.YMin, bb.ZMin))
    superfici = [f for f in forma.Faces if f.BoundBox.ZLength < 1e-6
                 and abs(f.CenterOfMass.z-bb.ZMax) < 1e-6]
    if not superfici:
        raise ValueError('Substrato PCB senza superficie superiore piana.')
    sopra = max(superfici, key=lambda f: f.Area)
    corpo = Part.Face(sopra.OuterWire).extrude(V(0, 0, -bb.ZLength))
    aperture = []
    for wire in sopra.Wires:
        if wire.isSame(sopra.OuterWire):
            continue
        b = wire.BoundBox
        if max(b.XLength, b.YLength) >= 1.5:
            aperture.append(Part.Face(wire).extrude(V(0, 0, -bb.ZLength)))
    if aperture:
        corpo = corpo.cut(Part.makeCompound(aperture))
    if not corpo.isValid():
        raise ValueError('Substrato semplificato non valido.')
    return corpo


def raccogli_solidi(documento, dettaglio='completo'):
    """Solo geometria Part, colori dal solido originale anche per gli App::Link."""
    forme, materiali, substrati = [], [], []
    for o in documento.Objects:
        if not hasattr(o, 'Shape') or o.Shape.isNull():
            continue
        sorgente = o.getLinkedObject(True)
        if not sorgente.isDerivedFrom('Part::Feature'):
            continue
        if 'silkscreen' in sorgente.Label.lower() or 'silkscreen' in o.Label.lower():
            continue
        if not o.Shape.Faces:
            continue
        if dettaglio == 'ingombri' and not o.Shape.Solids:
            continue  # La vista di montaggio contiene solo volumi fisici.
        forma = o.Shape.copy()
        forma.Placement = o.getGlobalPlacement()
        substrato = sorgente.Label.endswith('_PCB')
        if substrato:
            substrati.append(forma.copy())
        # FreeCAD 1.x: ShapeAppearance appartiene al solido, non al contenitore.
        colori = list(sorgente.ViewObject.ShapeAppearance)
        if len(colori) == 1:
            colori *= len(forma.Faces)
        if len(colori) != len(forma.Faces):
            raise ValueError('Numero materiali non coerente con le facce STEP: '+o.Label)
        if dettaglio == 'ingombri':
            forma = alleggerisci(forma, substrato)
            colori = [colori[0]]*len(forma.Faces)
        forme.append(forma)
        materiali.extend(colori)
    if len(substrati) != 1 or not forme:
        raise ValueError('Atteso un solo substrato KiCad con etichetta terminante in _PCB.')
    return Part.makeCompound(forme), materiali, substrati[0]


def firma_cache(step, pcb, origine, dettaglio):
    dati = dict(formato=1, dettaglio=dettaglio, origine=origine,
                freecad=App.Version()[:3], codice=Path(__file__).stat().st_mtime_ns,
                sorgenti=[(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in (step, pcb)])
    return hashlib.sha256(json.dumps(dati, sort_keys=True).encode()).hexdigest()


def leggi_cache(file, firma, doc):
    if not file.is_file():
        return None
    temp = App.openDocument(str(file))
    try:
        o = temp.getObject('GeometriaScheda')
        if o is None:
            raise ValueError('Cache scheda non valida: '+str(file))
        if o.FirmaSorgenti != firma:
            return None  # Sorgenti o impostazioni cambiate: rigenerare la conversione.
        return o.Shape.copy(), list(o.ViewObject.ShapeAppearance)
    finally:
        App.closeDocument(temp.Name)
        App.setActiveDocument(doc.Name)


def salva_cache(file, firma, geometria, materiali, doc):
    temp = App.newDocument('Cache_Scheda_EFES')
    try:
        o = temp.addObject('Part::Feature', 'GeometriaScheda')
        o.Shape = geometria
        o.ViewObject.ShapeAppearance = materiali
        o.ViewObject.DisplayMode = 'Shaded'
        o.addProperty('App::PropertyString', 'FirmaSorgenti').FirmaSorgenti = firma
        temp.recompute()
        file.parent.mkdir(parents=True, exist_ok=True)
        # Scrittura temporanea, poi sostituzione: niente cache parziali.
        temporaneo = file.with_name(file.stem+'_nuovo.FCStd')
        temp.saveAs(str(temporaneo))
        temporaneo.replace(file)
    finally:
        App.closeDocument(temp.Name)
        App.setActiveDocument(doc.Name)


def genera(doc, file_config):
    file_config = Path(file_config)
    spec = importlib.util.spec_from_file_location('schede_config', file_config.parent/'schede_config.py')
    regole = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regole)
    config = json.loads(file_config.read_text())
    dettaglio = config['dettaglio_schede']
    if dettaglio not in ('ingombri', 'completo'):
        raise ValueError('dettaglio_schede deve essere ingombri oppure completo.')
    # Libera anche la vecchia cache pesante, creata dalle versioni precedenti.
    if hasattr(App, '_EFES_CACHE_SCHEDE'):
        del App._EFES_CACHE_SCHEDE
    meta = doc.getObject('Dati_Sterzo')
    if meta is None:
        raise ValueError('Eseguire prima Sterzo.FCMacro.')
    dati = json.loads(meta.DatiJSON)
    if not dati.get('telaio'):
        raise ValueError('Rigenerare con Sterzo.FCMacro aggiornato e MOSTRA_TELAIO=True.')
    catalogo = {}
    for tipo, voce in config['libreria'].items():
        pcb = (file_config.parent/voce['pcb']).resolve()
        step = (file_config.parent/voce['step']).resolve()
        if not step.is_file():
            raise ValueError('STEP mancante: '+str(step))
        catalogo[tipo] = regole.leggi_pcb(pcb)
        App.Console.PrintMessage('%s: fori %s; %d connettori letti dal PCB.\n' %
            (tipo, ', '.join(catalogo[tipo]['fori']), len(catalogo[tipo]['connettori'])))

    pronti, montaggi, nomi = [], {}, set()
    for scheda in config['schede']:
        nome = scheda['nome']
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', nome) or nome in nomi:
            raise ValueError('Nome istanza non valido o duplicato: '+nome)
        nomi.add(nome)
        if type(scheda['attiva']) is not bool:
            raise ValueError('attiva deve essere true oppure false: '+nome)
        voce = config['libreria'][scheda['tipo']]
        if not scheda['attiva']:
            continue
        pcb = catalogo[scheda['tipo']]
        montaggio = regole.monta(scheda, pcb, dati['telaio'], voce['origine_step_kicad'])
        posa = App.Placement(V(*montaggio['traslazione']),
                             App.Rotation(V(0, 0, 1), montaggio['rotazione']))
        step_path = (file_config.parent/voce['step']).resolve()
        pcb_path = (file_config.parent/voce['pcb']).resolve()
        firma = firma_cache(step_path, pcb_path, voce['origine_step_kicad'], dettaglio)
        id_file = hashlib.sha256(str(step_path).encode()).hexdigest()[:12]
        file_cache = file_config.parent/'cache_schede'/('%s_%s.FCStd' % (id_file, dettaglio))
        caricata = leggi_cache(file_cache, firma, doc)
        if caricata is not None:
            geometria, materiali = caricata
            App.Console.PrintMessage(nome+': caricata cache su disco ('+dettaglio+').\n')
        else:
            temp = App.newDocument('Import_Scheda_EFES')
            try:
                ImportGui.insert(str(step_path), temp.Name)
                temp.recompute()
                facce_originali = sum(len(o.Shape.Faces) for o in temp.Objects
                                       if hasattr(o, 'Shape') and not o.Shape.isNull())
                geometria, materiali, substrato = raccogli_solidi(temp, dettaglio)
                # Verifica origine STEP confrontando i fori con il substrato importato.
                bb = substrato.optimalBoundingBox(False)
                if abs(bb.ZMin) > .01 or bb.ZLength <= .1:
                    raise ValueError('STEP: faccia inferiore del substrato richiesta a Z=0: '+nome)
                ox, oy = voce['origine_step_kicad']
                for ref, f in pcb['fori'].items():
                    centro = V(f['x']-ox, oy-f['y'], .01)
                    vuoto = Part.makeCylinder(f['diametro']/2-.05, bb.ZLength-.02, centro)
                    bordo = Part.makeCylinder(f['diametro']/2+.25, bb.ZLength-.02, centro).cut(vuoto)
                    if substrato.common(vuoto).Volume > .001 or substrato.common(bordo).Volume < .01:
                        raise ValueError('Foro %s/%s discordante fra STEP e KiCad: controllare origine export o riesportare il PCB.' % (nome, ref))
                App.Console.PrintMessage('%s: %d facce negli oggetti importati -> %d nella vista %s.\n' %
                                         (nome, facce_originali, len(geometria.Faces), dettaglio))
            finally:
                App.closeDocument(temp.Name)
                App.setActiveDocument(doc.Name)
            salva_cache(file_cache, firma, geometria, materiali, doc)
        forma = geometria.copy()
        forma.Placement = posa.multiply(forma.Placement)
        pronti.append((nome, forma, materiali, montaggio, pcb))
        montaggi[nome] = dict(tipo=scheda['tipo'], posa=montaggio,
                              fori=pcb['fori'], connettori=pcb['connettori'])

    pannello = Gui.getMainWindow().findChild(QtWidgets.QDockWidget, 'EFES_Sterzo_Movimento')
    if pannello is not None:
        pannello.close()
    doc.openTransaction('Aggiorna schede')
    try:
        for o in list(doc.Objects):
            if getattr(o, 'GeneratoSchede', False):
                doc.removeObject(o.Name)

        def marca(o):
            o.addProperty('App::PropertyBool', 'GeneratoSchede').GeneratoSchede = True
            return o

        for nome, forma, materiali, montaggio, pcb in pronti:
            gruppo = marca(doc.addObject('App::DocumentObjectGroup', 'Scheda_'+nome))
            gruppo.Label = nome
            o = marca(doc.addObject('Part::Feature', 'PCB_'+nome))
            o.Label, o.Shape = nome+' - '+dettaglio, forma
            o.ViewObject.ShapeAppearance = materiali
            o.ViewObject.DisplayMode = 'Shaded'
            o.ViewObject.Deviation = .2
            o.addProperty('App::PropertyString', 'GruppoCinematico').GruppoCinematico = 'fisso'
            o.addProperty('App::PropertyString', 'DettaglioScheda').DettaglioScheda = dettaglio
            gruppo.addObject(o)
            for f in montaggio['fissaggi']:
                if f['altezza'] == 0:
                    continue
                diametro = pcb['fori'][f['foro_pcb']]['diametro']
                if diametro >= 6:
                    raise ValueError('Foro troppo grande per il distanziale D6: '+nome)
                base = V(*f['centro'], f['z_appoggio'])
                forma = Part.makeCylinder(3, f['altezza'], base).cut(
                    Part.makeCylinder(diametro/2, f['altezza'], base))
                o = marca(doc.addObject('Part::Feature', 'Distanziale_%s_%s' % (nome, f['foro_pcb'])))
                o.Shape = forma
                o.ViewObject.ShapeColor = (.72, .73, .75)
                o.addProperty('App::PropertyString', 'GruppoCinematico').GruppoCinematico = 'fisso'
                gruppo.addObject(o)
            if len(montaggio['fissaggi']) < 2:
                App.Console.PrintWarning(nome+': un solo foro di riferimento; completare i fissaggi prima del montaggio reale.\n')
        info = marca(doc.addObject('App::FeaturePython', 'Dati_Schede'))
        info.addProperty('App::PropertyString', 'DatiJSON').DatiJSON = json.dumps(montaggi)
        info.addProperty('App::PropertyString', 'RevisioneSterzo').RevisioneSterzo = meta.Revisione
        doc.recompute()
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    App.Console.PrintMessage('Schede montate: %d. Configurazione: %s\n' % (len(pronti), file_config))
    if pronti and dettaglio == 'ingombri':
        App.Console.PrintMessage('Vista ingombri: componenti rettangolari, piccoli fori PCB omessi. Interferenze sulle schede indicative e conservative.\n')
