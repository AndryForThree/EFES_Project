"""Convert the supplied polygon SVG to filled, hole-preserving KiCad artwork.

No logo geometry is stored here. The source SVG uses absolute M/L/Z paths;
unsupported SVG constructs are rejected rather than silently misinterpreted.
"""
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw
from shapely import constrained_delaunay_triangles, make_valid
from shapely.affinity import scale, translate
from shapely.geometry import GeometryCollection, Polygon, box
from shapely.ops import unary_union


def polygon_parts(geometry):
    if geometry.geom_type == 'Polygon':
        yield geometry
    elif hasattr(geometry, 'geoms'):
        for part in geometry.geoms:
            yield from polygon_parts(part)


def read_svg(path):
    root = ET.parse(path).getroot()
    pieces = []
    for item in root.iter():
        kind = item.tag.split('}')[-1]
        if kind not in ('svg', 'title', 'desc', 'path') or 'transform' in item.attrib:
            raise ValueError('KiCad input must contain untransformed polygon paths (M/L/Z)')
        if kind != 'path':
            continue
        if item.get('fill-rule') != 'evenodd' or item.get('stroke') not in (None, 'none'):
            raise ValueError('KiCad input requires filled evenodd paths without strokes')
        tokens = re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', item.attrib['d'])
        filled, points, command = GeometryCollection(), [], None
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in ('M', 'L'):
                if token == 'M' and points:
                    raise ValueError('Close every SVG contour with Z')
                command = token
                index += 1
            elif token == 'Z':
                if len(points) < 3:
                    raise ValueError('SVG contour needs at least three vertices')
                filled = filled.symmetric_difference(make_valid(Polygon(points)))
                points, command = [], None
                index += 1
            elif re.fullmatch(r'[A-Za-z]', token) or command is None:
                raise ValueError(f'Unsupported SVG path command: {token}; export absolute M/L/Z polygons')
            else:
                points.append((float(tokens[index]), float(tokens[index+1])))
                index += 2
        if points:
            raise ValueError('Unclosed SVG contour')
        pieces.append(filled)
    geometry = unary_union(pieces)
    if geometry.is_empty:
        raise ValueError('SVG contains no filled polygons')
    return geometry


def artwork(geometry, width_mm):
    x0, y0, x1, y1 = geometry.bounds
    factor = width_mm / (x1 - x0)
    return scale(translate(geometry, -(x0+x1)/2, -(y0+y1)/2), factor, factor, origin=(0, 0))


def footprint(name, geometry):
    lines = [f'(footprint "{name}"', '  (version 20240108)', '  (generator "sbw_assets")',
             '  (layer "F.Cu")', '  (descr "Generated from source/SBW/pcb.svg; do not edit")',
             '  (attr board_only exclude_from_pos_files exclude_from_bom)',
             '  (property "Reference" "REF**" (at 0 0) (layer "F.Fab")',
             '    (effects (font (size 1 1) (thickness 0.15)) (hide yes)))',
             f'  (property "Value" "{name}" (at 0 0) (layer "F.Fab")',
             '    (effects (font (size 1 1) (thickness 0.15)) (hide yes)))']
    for polygon in polygon_parts(geometry):
        # KiCad fp_poly has no holes: triangulate only polygons needing them.
        regions = constrained_delaunay_triangles(polygon).geoms if polygon.interiors else [polygon]
        for region in regions:
            points = ' '.join(f'(xy {x:.5f} {y:.5f})' for x, y in list(region.exterior.coords)[:-1])
            lines.append(f'  (fp_poly (pts {points}) (stroke (width 0) (type solid)) (fill yes) (layer "F.SilkS"))')
    return '\n'.join(lines + [')', ''])


def generate_kicad(config, base_dir):
    source = read_svg(base_dir / config['source'])
    output = base_dir / config['output_dir']
    output.mkdir(parents=True, exist_ok=True)
    rendered, expected = [], set()
    for variant in config['variants']:
        geometry = source.intersection(box(*variant['crop'])) if 'crop' in variant else source
        if geometry.is_empty:
            raise ValueError('Empty KiCad crop')
        for width in variant['widths_mm']:
            if not 3 <= width <= 100:
                raise ValueError('KiCad widths must be within 3..100 mm')
            name = f'{variant["name"]}_{width:g}mm'.replace('.', 'p')
            if not re.fullmatch(r'SBW_[A-Za-z0-9_]+', name) or name in expected:
                raise ValueError(f'Invalid or duplicate footprint name: {name}')
            expected.add(name)
            scaled = artwork(geometry, width)
            (output / f'{name}.kicad_mod').write_text(footprint(name, scaled))
            rendered.append((name, scaled))
    # Shared project library: only manage this generator's logo/size series.
    for path in output.glob('SBW_*.kicad_mod'):
        if re.fullmatch(r'SBW_(?:Logo|Symbol)_\d+(?:p\d+)?mm', path.stem) and path.stem not in expected:
            path.unlink()
    preview = base_dir / config['preview']
    preview.parent.mkdir(parents=True, exist_ok=True)
    columns = 3
    sheet = Image.new('RGB', (columns * 520, ((len(rendered)+columns-1)//columns) * 450), '#143f32')
    draw = ImageDraw.Draw(sheet)
    for i, (name, geometry) in enumerate(rendered):
        cx, cy = (i % columns)*520 + 260, (i // columns)*450 + 240
        draw.text((cx-230, cy-210), name, fill='white')
        for polygon in polygon_parts(geometry):
            coords = lambda ring: [(cx+x*12, cy+y*12) for x, y in ring.coords]
            draw.polygon(coords(polygon.exterior), fill='white')
            for ring in polygon.interiors:
                draw.polygon(coords(ring), fill='#143f32')
    sheet.save(preview)
    print(f'Generated {len(expected)} KiCad footprints: {output}')
