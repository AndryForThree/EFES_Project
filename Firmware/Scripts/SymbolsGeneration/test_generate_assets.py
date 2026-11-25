import tempfile
import unittest
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from PIL import Image
from generate_assets import generate_asset, load_image, make_binary, asset_preview, BINARY_HEADER, SCRIPT_DIR


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.svg = self.root / 'input.svg'
        self.svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10" viewBox="0 0 20 10">'
                            '<rect width="10" height="10" fill="red"/></svg>')

    def test_native_svg_matches_equivalent_png(self):
        image = Image.new('RGBA', (20, 10))
        image.paste((255, 0, 0, 255), (0, 0, 10, 10))
        image.save(self.root / 'input.png')
        svg = generate_asset({'name': 'TEST', 'file': 'input.svg'}, self.root, None)
        png = generate_asset({'name': 'TEST', 'file': 'input.png'}, self.root, None)
        self.assertEqual(svg, png)

    def test_svg_rasterized_at_target_size_with_transparent_margins(self):
        image = load_image(self.svg, 80)
        self.assertEqual(image.mode, 'RGBA')
        self.assertEqual(image.size, (80, 80))
        self.assertEqual(image.getbbox(), (0, 20, 40, 60))

    def test_cli_size_overrides_config_for_svg(self):
        asset = generate_asset({'name': 'TEST', 'file': 'input.svg', 'size': 24}, self.root, 64)
        self.assertEqual((asset['width'], asset['height'], len(asset['data'])), (64, 64, 4096))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['input.svg'])

    def test_malformed_svg_reports_input(self):
        self.svg.write_text('<svg broken')
        with self.assertRaisesRegex(SystemExit, 'Impossibile rasterizzare SVG'):
            generate_asset({'name': 'TEST', 'file': 'input.svg'}, self.root, None)

    def test_transparent_input_reports_asset(self):
        Image.new('RGBA', (8, 8)).save(self.root / 'empty.png')
        with self.assertRaisesRegex(SystemExit, 'Nessun pixel visibile in TEST'):
            generate_asset({'name': 'TEST', 'file': 'empty.png'}, self.root, None)

    def test_rgb_png_and_export_preview(self):
        image = Image.new('RGB', (2, 1))
        image.putdata([(255, 0, 0), (0, 255, 0)])
        image.save(self.root / 'rgb.png')
        asset = generate_asset({'name': 'RGB', 'file': 'rgb.png', 'output': 'bin', 'format': 'rgb565'}, self.root, None)
        self.assertEqual(bytes(asset['data']), bytes.fromhex('f80007e0'))
        self.assertEqual(list(asset_preview(asset).getdata()), [(255, 0, 0, 255), (0, 255, 0, 255)])

    def test_kicad_polygons_preserve_holes_and_painted_width(self):
        import re
        from generate_kicad import artwork, footprint, read_svg
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        self.svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10">'
                            '<path fill-rule="evenodd" d="M0 0 L20 0 L20 10 L0 10 Z '
                            'M5 2 L15 2 L15 8 L5 8 Z"/></svg>')
        geometry = artwork(read_svg(self.svg), 12)
        text = footprint('SBW_Test_12mm', geometry)
        pieces = []
        for block in re.findall(r'\(fp_poly \(pts (.*?)\) \(stroke', text):
            points = [(float(x), float(y)) for x, y in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)', block)]
            pieces.append(Polygon(points))
        exported = unary_union(pieces)
        self.assertAlmostEqual(exported.bounds[2] - exported.bounds[0], 12)
        self.assertLess(exported.symmetric_difference(geometry).area, 1e-7)
        self.assertNotIn('(pad ', text)
        self.assertIn('(layer "F.SilkS")', text)

    def test_kicad_rejects_unsupported_svg(self):
        from generate_kicad import read_svg
        self.svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>')
        with self.assertRaisesRegex(ValueError, 'polygon paths'):
            read_svg(self.svg)

    def test_rectangle_keeps_proportions(self):
        image = load_image(self.svg, [80, 60])
        self.assertEqual(image.size, (80, 60))
        self.assertEqual(image.getbbox(), (0, 10, 40, 50))
        asset = generate_asset({'name': 'TEST', 'file': 'input.svg', 'size': [80, 60]}, self.root, None)
        self.assertEqual((asset['width'], asset['height'], len(asset['data'])), (80, 60, 4800))

    def test_rgb565_wire_order_and_background(self):
        image = Image.new('RGBA', (3, 1))
        image.putdata([(255, 0, 0, 255), (0, 255, 0, 255), (255, 0, 0, 0)])
        image.save(self.root / 'colors.png')
        asset = generate_asset({'name': 'RGB', 'file': 'colors.png', 'format': 'rgb565',
                                'output': 'bin', 'background': '#0000ff'}, self.root, None)
        self.assertEqual(bytes(asset['data']), bytes.fromhex('f80007e0001f'))
        data = make_binary(asset)
        # Independent unpacking of the documented 24-byte file header.
        fields = struct.unpack('<4sBBHHHIII', data[:24])
        self.assertEqual(fields[:8], (b'EFAS', 1, 2, 3, 1, 0, 6, 6))
        self.assertEqual(fields[8], zlib.crc32(data[24:]))
        self.assertEqual(len(data), 30)

    def test_binary_has_its_own_palette(self):
        asset = generate_asset({'name': 'TEST', 'file': 'input.svg', 'output': 'bin'}, self.root, None)
        data = make_binary(asset)
        header = BINARY_HEADER.unpack(data[:24])
        self.assertEqual(header[2:8], (1, 20, 10, 16, 200, 232))
        self.assertEqual(data[24:56], b''.join(v.to_bytes(2, 'big') for v in asset['palette']))
        self.assertEqual(data[56:], bytes(asset['data']))
        self.assertEqual(header[8], zlib.crc32(data[24:]))

    def test_defaults_match_explicit_settings(self):
        spec = {'name': 'TEST', 'file': 'input.svg'}
        self.assertEqual(generate_asset(spec, self.root, None),
                         generate_asset(dict(spec, output='c', format='palette4_alpha4'), self.root, None))

    def test_invalid_options(self):
        for settings in ({'output': 'uart'}, {'format': 'jpeg'}, {'size': [12, 0]}, {'size': True}):
            with self.subTest(settings=settings), self.assertRaises(SystemExit):
                generate_asset({'name': 'TEST', 'file': 'input.svg', **settings}, self.root, None)

    def test_mixed_cli_routes_outputs_and_removes_only_obsolete_binaries(self):
        assets = []
        for output in ('c', 'bin'):
            for fmt in ('palette4_alpha4', 'rgb565'):
                assets.append({'name': f'{output}_{fmt}'.upper(), 'file': 'input.svg',
                               'size': [32, 16], 'output': output, 'format': fmt})
        config = self.root / 'assets.json'
        settings = {'output_dir': 'c_output', 'binary_output_dir': 'bin_output', 'assets': assets}
        config.write_text(json.dumps(settings))
        command = [sys.executable, str(SCRIPT_DIR / 'generate_assets.py'), '--config', str(config)]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        out = self.root / 'c_output'
        source = (out / 'assets_generated.c').read_bytes()
        self.assertNotIn(b'BIN_RGB565', source)
        self.assertIn(b'C_PALETTE4_ALPHA4', source)
        self.assertIn(b'C_RGB565', source)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-c',
                        str(out / 'assets_generated.c'), '-o', str(self.root / 'assets.o')], check=True)
        binary = self.root / 'bin_output'
        self.assertTrue((binary / 'BIN_RGB565.bin').is_file())
        self.assertTrue((binary / 'BIN_PALETTE4_ALPHA4.bin').is_file())
        before = (binary / 'BIN_RGB565.bin').read_bytes()
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        self.assertEqual(before, (binary / 'BIN_RGB565.bin').read_bytes())
        self.assertEqual(source, (out / 'assets_generated.c').read_bytes())
        (binary / 'keep.bin').write_bytes(b'keep')
        settings['assets'] = [a for a in assets if a['output'] == 'c']
        config.write_text(json.dumps(settings))
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        self.assertEqual(list(binary.glob('BIN_*.bin')), [])
        self.assertEqual((binary / 'keep.bin').read_bytes(), b'keep')
        self.assertEqual(json.loads((binary / 'assets_binary.json').read_text()), {'assets': []})


if __name__ == '__main__':
    unittest.main()
