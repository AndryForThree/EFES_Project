"""Regressione: contenitori e link STEP non hanno DiffuseColor."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest

# Esegue la funzione reale senza richiedere il runtime grafico FreeCAD.
file = Path(__file__).with_name('schede_cad.py')
albero = ast.parse(file.read_text())
funzione = next(n for n in albero.body if isinstance(n, ast.FunctionDef) and n.name == 'raccogli_solidi')
ns = {'Part': SimpleNamespace(makeCompound=lambda forme: list(forme))}
exec(compile(ast.Module(body=[funzione], type_ignores=[]), str(file), 'exec'), ns)
raccogli = ns['raccogli_solidi']


class Forma:
    Faces = [1, 2]
    def isNull(self):
        return False
    def copy(self):
        return copy.copy(self)


def oggetto(label, solido=True, materiali=('verde',)):
    sorgente = SimpleNamespace(Label=label,
        isDerivedFrom=lambda tipo: solido,
        ViewObject=SimpleNamespace(ShapeAppearance=materiali))
    return SimpleNamespace(Label=label, Shape=Forma(),
        ViewObject=SimpleNamespace(),  # Nessuna proprieta dei colori sul link/contenitore.
        getLinkedObject=lambda recursive: sorgente,
        getGlobalPlacement=lambda: 'posa_globale')


class ImportazioneSchede(unittest.TestCase):
    def test_link_legge_materiali_dal_solido(self):
        compound, colori, substrato = raccogli(SimpleNamespace(Objects=[oggetto('test_PCB')]))
        self.assertEqual(colori, ['verde', 'verde'])
        self.assertEqual(compound[0].Placement, 'posa_globale')
        self.assertEqual(substrato.Placement, 'posa_globale')

    def test_contenitori_e_serigrafia_esclusi(self):
        doc = SimpleNamespace(Objects=[oggetto('assembly', False),
            oggetto('test_silkscreen'), oggetto('test_PCB'), oggetto('USB', materiali=('acciaio', 'nero'))])
        forme, colori, _ = raccogli(doc)
        self.assertEqual(len(forme), 2)
        self.assertEqual(colori, ['verde', 'verde', 'acciaio', 'nero'])

    def test_materiali_incoerenti_segnalati(self):
        with self.assertRaisesRegex(ValueError, 'Numero materiali'):
            raccogli(SimpleNamespace(Objects=[oggetto('test_PCB', materiali=())]))

    def test_substrato_mancante_segnalato(self):
        with self.assertRaisesRegex(ValueError, 'substrato'):
            raccogli(SimpleNamespace(Objects=[oggetto('USB')]))


if __name__ == '__main__':
    unittest.main()
