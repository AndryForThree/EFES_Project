"""Verifica delle coordinate e dei vincoli, eseguibile senza FreeCAD."""
import copy
import json
import math
from pathlib import Path
import unittest
import schede_config
import telaio_sterzo

ROOT = Path(__file__).resolve().parent


class MontaggioSchede(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT/'schede.json').read_text())
        punti = json.loads((ROOT/'sterzo_cad.json').read_text())['points']
        cls.telaio = telaio_sterzo.piano_telaio(punti)
        cls.telaio.update(passo=10, base_z=24, spessore=1)
        cls.catalogo = {nome: schede_config.leggi_pcb(ROOT/v['pcb'])
                        for nome, v in cls.config['libreria'].items()}

    def monta(self, s):
        return schede_config.monta(s, self.catalogo[s['tipo']], self.telaio,
                                   self.config['libreria'][s['tipo']]['origine_step_kicad'])

    def test_coordinate_reali_e_connettori(self):
        self.assertEqual(self.catalogo['HumanSide']['fori']['H4']['x'], 95)
        self.assertEqual(self.catalogo['RoadSide']['fori']['H1']['diametro'], 3.2)
        self.assertIn('J14', self.catalogo['RoadSide']['connettori'])
        self.assertNotIn('JP1', self.catalogo['HumanSide']['connettori'])

    def test_due_fissaggi_humanside_coincidono(self):
        s = self.config['schede'][1]
        m = self.monta(s)
        self.assertEqual(len(m['fissaggi']), 2)
        self.assertAlmostEqual(math.dist(*[f['centro'] for f in m['fissaggi']]), 90)
        self.assertAlmostEqual(m['traslazione'][2], 37)

    def test_cambio_origine_step_non_sposta_i_fori(self):
        s = self.config['schede'][1]
        b = self.catalogo['HumanSide']
        for origine in ([0, 0], [70, 35]):
            m = schede_config.monta(s, b, self.telaio, origine)
            a = math.radians(m['rotazione'])
            for f in m['fissaggi']:
                p = b['fori'][f['foro_pcb']]
                x, y = p['x']-origine[0], origine[1]-p['y']
                self.assertAlmostEqual(math.cos(a)*x-math.sin(a)*y+m['traslazione'][0], f['centro'][0])
                self.assertAlmostEqual(math.sin(a)*x+math.cos(a)*y+m['traslazione'][1], f['centro'][1])

    def test_fissaggio_incompatibile_non_arrotondato(self):
        s = copy.deepcopy(self.config['schede'][1])
        s['fissaggi'][1]['foro_pcb'] = 'H4'
        with self.assertRaisesRegex(ValueError, 'Fissaggio incompatibile'):
            self.monta(s)

    def test_errori_di_configurazione(self):
        for chiave, valore in [('altezza_distanziale', -1), ('rotazione', float('nan')),
                              ('fissaggi', [])]:
            s = copy.deepcopy(self.config['schede'][0])
            s[chiave] = valore
            with self.assertRaises(ValueError):
                self.monta(s)
        s = copy.deepcopy(self.config['schede'][0])
        s['fissaggi'][0]['foro_telaio'] = 999
        with self.assertRaisesRegex(ValueError, 'Numero foro'):
            self.monta(s)

    def test_nomi_fori_non_inventati(self):
        s = copy.deepcopy(self.config['schede'][0])
        s['fissaggi'][0]['foro_pcb'] = 'H999'
        with self.assertRaises(KeyError):
            self.monta(s)


if __name__ == '__main__':
    unittest.main()
