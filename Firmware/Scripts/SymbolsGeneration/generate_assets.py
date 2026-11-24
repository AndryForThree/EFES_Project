#!/usr/bin/env python3
"""Convert PNG/SVG assets to C arrays or self-describing binary files."""

import argparse
import io
import json
import re
import struct
import zlib
from pathlib import Path

from PIL import Image, ImageOps


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = SCRIPT_DIR.parents[1] / "EFES_FW_HumanSide/customLibs/ST7789/Assets"
DEFAULT_BINARY_OUTPUT = SCRIPT_DIR.parents[1] / "ExternalFlash/Assets"
# Little-endian metadata; pixel/palette RGB565 words are big-endian wire bytes.
BINARY_HEADER = struct.Struct('<4sBBHHHIII')
FORMAT_IDS = {'palette4_alpha4': 1, 'rgb565': 2}


def normalize_size(size):
    if size is None:
        return None
    dims = (size, size) if type(size) is int else size
    if not isinstance(dims, (list, tuple)) or len(dims) != 2 or any(type(v) is not int or not 1 <= v <= 65535 for v in dims):
        raise SystemExit(f'Dimensione non valida: {size}; usare N oppure [larghezza, altezza]')
    return tuple(dims)


def rgb565(red, green, blue):
    return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)


def load_image(path, size):
    """Normalize PNG/SVG input to an RGBA image, entirely in memory."""
    dims = normalize_size(size)
    if path.suffix.lower() == ".svg":
        try:
            import cairosvg
        except ImportError as exc:
            raise SystemExit("Per leggere SVG installare CairoSVG: python3 -m pip install CairoSVG") from exc
        try:
            # Rasterize vectors at the requested resolution, avoiding an upscale
            # of a low-resolution intermediate. SVG viewBox preserves proportions.
            png = cairosvg.svg2png(url=str(path), output_width=dims[0] if dims else None,
                                  output_height=dims[1] if dims else None)
            with Image.open(io.BytesIO(png)) as source:
                return source.convert("RGBA")
        except Exception as exc:
            raise SystemExit(f"Impossibile rasterizzare SVG {path}: {exc}") from exc
    with Image.open(path) as source:
        if source.format != "PNG" or source.mode != "RGBA":
            raise SystemExit(f"Serve un PNG RGBA oppure un SVG: {path}")
        return source.copy()


def generate_asset(spec, base_dir, size):
    name = spec["name"]
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or name in ("INVALID", "COUNT"):
        raise SystemExit(f"Nome asset non valido: {name}")
    path = base_dir / spec["file"]
    if not path.is_file():
        raise SystemExit(f"Immagine non trovata: {path}")

    # CLI size overrides the individual size in the configuration.
    size = size if size is not None else spec.get("size")
    dims = normalize_size(size)
    output, fmt = spec.get('output', 'c'), spec.get('format', 'palette4_alpha4')
    if output not in ('c', 'bin') or fmt not in FORMAT_IDS:
        raise SystemExit(f'Output/formato non valido per {name}: {output}/{fmt}')
    image = load_image(path, dims)
    if dims is not None:
        resized = ImageOps.contain(image, dims, Image.Resampling.LANCZOS)
        image = Image.new("RGBA", dims, (0, 0, 0, 0))
        image.paste(resized, ((dims[0] - resized.width) // 2, (dims[1] - resized.height) // 2))

    asset = encode_image(name, image) if fmt == 'palette4_alpha4' else encode_rgb565(name, image, spec.get('background', '#000000'))
    asset.update(output=output, format=fmt)
    return asset


def encode_rgb565(name, image, background):
    width, height = image.size
    if width > 65535 or height > 65535:
        raise SystemExit(f'Asset troppo grande: {name}')
    frame = Image.new('RGB', image.size, background).convert('RGBA')
    frame = Image.alpha_composite(frame, image).convert('RGB')
    data = bytearray()
    for r, g, b in frame.getdata():
        data.extend(rgb565(r, g, b).to_bytes(2, 'big'))
    return {'name': name, 'width': width, 'height': height, 'stride': width * 2,
            'palette': [], 'data': list(data)}


def make_binary(asset):
    palette = b''.join(v.to_bytes(2, 'big') for v in asset['palette'])
    data = bytes(asset['data'])
    payload = palette + data
    header = BINARY_HEADER.pack(b'EFAS', 1, FORMAT_IDS[asset['format']],
                                asset['width'], asset['height'], len(asset['palette']),
                                len(data), len(payload), zlib.crc32(payload))
    return header + payload


def encode_image(name, image):
    """Encode an RGBA image with a per-asset palette and 4-bit alpha."""
    width, height = image.size
    if width > 65535 or height > 65535:
        raise SystemExit(f"Asset troppo grande: {name}")
    pixels = list(image.getdata())
    alpha = [(a * 15 + 127) // 255 for r, g, b, a in pixels]
    visible = [(r, g, b) for (r, g, b, a), coverage in zip(pixels, alpha) if coverage]
    if not visible:
        raise SystemExit(f"Nessun pixel visibile in {name}")

    # Transparent RGB values must not consume palette entries.
    colors = Image.new("RGB", (len(visible), 1))
    colors.putdata(visible)
    quantized = colors.quantize(colors=16, method=Image.Quantize.MEDIANCUT,
                                dither=Image.Dither.NONE)
    visible_indices = iter(quantized.getdata())
    palette_rgb = quantized.getpalette()
    palette = []
    for offset in range(0, min(len(palette_rgb), 48), 3):
        palette.append(rgb565(*palette_rgb[offset:offset + 3]))
    palette.extend([0] * (16 - len(palette)))

    # One byte per pixel: palette index in the high nibble, alpha in the low.
    data = [(next(visible_indices) << 4) | coverage if coverage else 0
            for coverage in alpha]

    return {"name": name, "width": width, "height": height,
            "stride": width, "palette": palette, "data": data}


def make_header(assets):
    rgb_assets = [a for a in assets if a.get('format') == 'rgb565']
    assets = [a for a in assets if a.get('format', 'palette4_alpha4') == 'palette4_alpha4']
    ids = "\n".join(f'    ASSET_{asset["name"]},' for asset in assets)
    header = f"""/* Generated by generate_assets.py. Do not edit. */
#ifndef ASSETS_GENERATED_H
#define ASSETS_GENERATED_H

#include <stdint.h>

typedef enum {{
    ASSET_INVALID = 0,
{ids}
    ASSET_COUNT
}} GraphicAssetId;

/* One byte per pixel, row-major: high nibble = palette index, low = alpha.
 * Alpha: 0 transparent, 15 opaque. All 16 palette indices are available.
 * Palette contains native RGB565 values; stride is measured in bytes.
 */
typedef struct {{
    const uint8_t *data;
    const uint16_t *palette;
    uint16_t width;
    uint16_t height;
    uint16_t stride;
}} GraphicAsset;

extern const GraphicAsset Assets[ASSET_COUNT];

#endif
"""
    if rgb_assets:
        ids = '\n'.join(f'    RGB565_ASSET_{a["name"]},' for a in rgb_assets)
        extra = f'''/* RGB565 bytes, MSB first. Separate registry: not a GraphicAsset. */
typedef enum {{
    RGB565_ASSET_INVALID = 0,
{ids}
    RGB565_ASSET_COUNT
}} RGB565AssetId;
typedef struct {{
    const uint8_t *data;
    uint16_t width, height;
    uint32_t stride;
}} RGB565Asset;
extern const RGB565Asset RGB565Assets[RGB565_ASSET_COUNT];

'''
        header = header.replace('#endif\n', extra + '#endif\n')
    return header


def make_source(assets):
    rgb_assets = [a for a in assets if a.get('format') == 'rgb565']
    assets = [a for a in assets if a.get('format', 'palette4_alpha4') == 'palette4_alpha4']
    lines = ['/* Generated by generate_assets.py. Do not edit. */',
             '#include "assets_generated.h"', ""]
    for asset in assets:
        name = asset["name"]
        palette = ", ".join(f"0x{color:04X}" for color in asset["palette"])
        lines.append(f"static const uint16_t palette_{name}[16] = {{{palette}}};")
        lines.append(f"static const uint8_t data_{name}[] = {{")
        for offset in range(0, len(asset["data"]), 16):
            values = ", ".join(f"0x{value:02X}" for value in asset["data"][offset:offset + 16])
            lines.append(f"    {values},")
        lines.extend(["};", ""])
    lines.extend(["const GraphicAsset Assets[ASSET_COUNT] = {",
                  "    [ASSET_INVALID] = {0},"])
    for asset in assets:
        name = asset["name"]
        lines.extend([f"    [ASSET_{name}] = {{",
                      f"        .data = data_{name},",
                      f"        .palette = palette_{name},",
                      f'        .width = {asset["width"]},',
                      f'        .height = {asset["height"]},',
                      f'        .stride = {asset["stride"]}',
                      "    },"])
    lines.extend(["};", ""])
    if rgb_assets:
        for asset in rgb_assets:
            lines.append(f'static const uint8_t rgb565_{asset["name"]}[] = {{')
            for offset in range(0, len(asset['data']), 16):
                lines.append('    ' + ', '.join(f'0x{v:02X}' for v in asset['data'][offset:offset+16]) + ',')
            lines.extend(['};', ''])
        lines.extend(['const RGB565Asset RGB565Assets[RGB565_ASSET_COUNT] = {', '    [RGB565_ASSET_INVALID] = {0},'])
        for a in rgb_assets:
            lines.append(f'    [RGB565_ASSET_{a["name"]}] = {{ .data = rgb565_{a["name"]}, .width = {a["width"]}, '
                         f'.height = {a["height"]}, .stride = {a["stride"]} }},')
        lines.extend(['};', ''])
    return "\n".join(lines)


def write_binaries(assets, output):
    index_path = output / 'assets_binary.json'
    old = json.loads(index_path.read_text()) if index_path.exists() else {'assets': []}
    previous = {a['file'] for a in old['assets']}
    if any(not re.fullmatch(r'[A-Z][A-Z0-9_]*\.bin', name) for name in previous):
        raise SystemExit(f'Indice binari non valido: {index_path}')
    entries = []
    output.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        filename = asset['name'] + '.bin'
        data = make_binary(asset)
        (output / filename).write_bytes(data)
        print(f'Generated {output / filename}')
        entries.append({'name': asset['name'], 'file': filename, 'format': asset['format'],
                        'width': asset['width'], 'height': asset['height'], 'file_bytes': len(data)})
    for filename in previous - {a['file'] for a in entries}:
        (output / filename).unlink(missing_ok=True)
    index_path.write_text(json.dumps({'assets': entries}, indent=2) + '\n')
    print(f'Generated {index_path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=SCRIPT_DIR / "assets.json")
    parser.add_argument("--output", type=Path,
                        help="Directory for assets_generated.h and .c.")
    parser.add_argument('--binary-output', type=Path, help='Directory for binary assets and assets_binary.json.')
    parser.add_argument("--size", type=int,
                        help="Resize every asset to an N x N transparent canvas.")
    args = parser.parse_args()
    if args.size is not None and not 1 <= args.size <= 65535:
        parser.error("--size must be between 1 and 65535")
    config = args.config.expanduser().resolve()
    settings = json.loads(config.read_text(encoding="utf-8"))
    specs = settings['assets']
    names = [spec["name"] for spec in specs]
    if len(names) != len(set(names)):
        parser.error("Each asset must have a unique name")
    assets = [generate_asset(spec, config.parent, args.size)
              for spec in specs]
    output = (args.output or config.parent / settings.get('output_dir', DEFAULT_OUTPUT)).expanduser().resolve()
    binary_output = (args.binary_output or config.parent / settings.get('binary_output_dir', DEFAULT_BINARY_OUTPUT)).expanduser().resolve()
    c_assets = [a for a in assets if a['output'] == 'c']
    bin_assets = [a for a in assets if a['output'] == 'bin']
    output.mkdir(parents=True, exist_ok=True)
    (output / "assets_generated.h").write_text(make_header(c_assets), encoding="utf-8")
    (output / "assets_generated.c").write_text(make_source(c_assets), encoding="utf-8")
    if bin_assets or (binary_output / 'assets_binary.json').exists():
        write_binaries(bin_assets, binary_output)
    print(f"Generated {output / 'assets_generated.h'}")
    print(f"Generated {output / 'assets_generated.c'}")
    for asset in assets:
        print(f'{asset["name"]}: {asset["width"]}x{asset["height"]}, '
              f'{asset["output"]}/{asset["format"]}, '
              f'{len(asset["data"])} bitmap bytes + {len(asset["palette"])*2} palette bytes')
    if not assets:
        print("Registro vuoto: aggiungere le immagini in assets.json.")


if __name__ == "__main__":
    main()
