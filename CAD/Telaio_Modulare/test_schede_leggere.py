"""Vista di montaggio e invalidazione della cache, senza runtime FreeCAD."""
import ast
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

FILE = Path(__file__).with_name('schede_cad.py')
albero = ast.parse(FILE.read_text())


def funzione(nome, **ambiente):
    nodo = next(n for n in albero.body if isinstance(n, ast.FunctionDef) and n.name == nome)
    ns = dict(Path=Path, json=json, hashlib=hashlib, __file__=str(FILE), **ambiente)
    exec(compile(ast.Module(body=[nodo], type_ignores=[]), str(FILE), 'exec'), ns)
    return ns[nome]


class SchedeLeggere(unittest.TestCase):
    def test_componenti_mantengono_ingombro_completo(self):
        bb = SimpleNamespace(XLength=7, YLength=5, ZLength=12, XMin=-2, YMin=3, ZMin=-1)
        forma = SimpleNamespace(optimalBoundingBox=lambda triangoli: bb)
        part = SimpleNamespace(makeBox=lambda *arg: arg)
        semplifica = funzione('alleggerisci', Part=part, V=lambda *p: p)
        self.assertEqual(semplifica(forma, False), (7, 5, 12, (-2, 3, -1)))

    def test_cache_cambia_con_sorgenti_origine_e_dettaglio(self):
        firma = funzione('firma_cache', App=SimpleNamespace(Version=lambda: ['1', '1', '4']))
        with TemporaryDirectory() as d:
            step, pcb = Path(d)/'a.step', Path(d)/'a.kicad_pcb'
            step.write_text('STEP')
            pcb.write_text('PCB')
            iniziale = firma(step, pcb, [0, 0], 'ingombri')
            self.assertEqual(iniziale, firma(step, pcb, [0, 0], 'ingombri'))
            self.assertNotEqual(iniziale, firma(step, pcb, [70, 35], 'ingombri'))
            self.assertNotEqual(iniziale, firma(step, pcb, [0, 0], 'completo'))
            step.write_text('STEP aggiornato')
            self.assertNotEqual(iniziale, firma(step, pcb, [0, 0], 'ingombri'))
            seconda = firma(step, pcb, [0, 0], 'ingombri')
            pcb.write_text('PCB aggiornato')
            self.assertNotEqual(seconda, firma(step, pcb, [0, 0], 'ingombri'))

    def test_cache_valida_non_richiede_step(self):
        chiamate = []
        obj = SimpleNamespace(FirmaSorgenti='firma', Shape=SimpleNamespace(copy=lambda: 'geometria'),
                              ViewObject=SimpleNamespace(ShapeAppearance=['verde']))
        temp = SimpleNamespace(Name='cache', getObject=lambda nome: obj)
        app = SimpleNamespace(openDocument=lambda file: temp,
            closeDocument=lambda nome: chiamate.append(('chiudi', nome)),
            setActiveDocument=lambda nome: chiamate.append(('attiva', nome)))
        leggi = funzione('leggi_cache', App=app)
        with TemporaryDirectory() as d:
            file = Path(d)/'cache.FCStd'
            self.assertIsNone(leggi(file, 'firma', SimpleNamespace(Name='telaio')))
            file.touch()
            self.assertEqual(leggi(file, 'firma', SimpleNamespace(Name='telaio')), ('geometria', ['verde']))
            self.assertIsNone(leggi(file, 'nuova_firma', SimpleNamespace(Name='telaio')))
        self.assertEqual(chiamate, [('chiudi', 'cache'), ('attiva', 'telaio')]*2)

    def test_impostazione_predefinita_leggera(self):
        config = json.loads(FILE.with_name('schede.json').read_text())
        self.assertEqual(config['dettaglio_schede'], 'ingombri')
        self.assertTrue(all(s['attiva'] for s in config['schede']))


if __name__ == '__main__':
    unittest.main()
