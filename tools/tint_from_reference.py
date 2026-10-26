"""Colour each region from the reference's own colour, keeping the value it already has.

**Why one hue is not a colouring.** The first pass put a single hue and saturation over everything and the picture came
out sepia: a white-haired character with a red eye and black stockings has three different materials, and one hue cannot
say three. What a painted reference does provide is *where* each hue goes, so each filled shape takes its hue and
saturation from the pixels under it and keeps only its own luminance.

**The value is what was already decided.** This pass never touches lightness: it converts the shape's existing grey to
HSL, replaces hue and saturation with the reference's, and converts back. So the guard from the colour stage still
holds, and the report says by how much it would not have.
"""
import argparse
import colorsys
import json
import pathlib

import numpy as np
from PIL import Image, ImageDraw

WR, WG, WB = 0.2126, 0.7152, 0.0722


def parse_hex(text):
    text = text.lstrip('#')
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    r, g, b = (c / 255.0 for c in rgb)
    return WR * r + WG * g + WB * b


def tinted(target, hue, sat):
    r, g, b = colorsys.hsv_to_rgb(hue, sat, 1.0)
    cur = WR * r + WG * g + WB * b
    if cur <= 1e-9:
        return (target * 255.0,) * 3
    if target <= cur:
        k = target / cur
        return (r * k * 255.0, g * k * 255.0, b * k * 255.0)
    t = (target - cur) / (1.0 - cur)
    return ((r + (1.0 - r) * t) * 255.0, (g + (1.0 - g) * t) * 255.0, (b + (1.0 - b) * t) * 255.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--radius', type=int, default=12, help='patch radius sampled under each shape, in page pixels')
    ap.add_argument('--sat-scale', type=float, default=1.0)
    ap.add_argument('--limit', type=float, default=0.05)
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.src).read_text(encoding='utf-8'))
    canvas = doc.get('canvas') or {}
    width = int(canvas.get('width') or 0)
    height = int(canvas.get('height') or 0)
    image = Image.open(args.reference).convert('RGB')
    if image.size != (width, height):
        image = image.resize((width, height), Image.LANCZOS)
    pixels = np.asarray(image, dtype=np.float32) / 255.0

    drifts = []
    hues = []
    for mark in doc.get('marks', []):
        if mark.get('kind') != 'fill':
            continue
        points = (mark.get('geometry') or {}).get('points') or []
        if len(points) < 3:
            continue
        # **The pixels inside the shape, not a patch around its centroid.** A convoluted shape -- a ribbon, a lock of
        # hair, a leg seen between two others -- has its centroid outside itself, and sampling there takes the colour of
        # whatever is behind it. Measured on a second reference, that turned a warm face violet because the skin's
        # centroid sat on the violet background.
        pts = np.asarray(points, dtype=np.float64)
        x0 = int(max(0, np.floor(pts[:, 0].min())))
        y0 = int(max(0, np.floor(pts[:, 1].min())))
        x1 = int(min(width - 1, np.ceil(pts[:, 0].max())))
        y1 = int(min(height - 1, np.ceil(pts[:, 1].max())))
        if x1 <= x0 or y1 <= y0:
            continue
        canvas = Image.new('L', (x1 - x0 + 1, y1 - y0 + 1), 0)
        ImageDraw.Draw(canvas).polygon([(p[0] - x0, p[1] - y0) for p in pts], fill=255)
        inside = np.asarray(canvas) > 127
        if int(inside.sum()) < 16:
            continue
        patch = pixels[y0:y1 + 1, x0:x1 + 1][inside]
        mean = patch.reshape(-1, 3).mean(axis=0)
        hue, sat, _v = colorsys.rgb_to_hsv(float(mean[0]), float(mean[1]), float(mean[2]))
        sat = max(0.0, min(1.0, sat * args.sat_scale))
        appearance = mark.setdefault('appearance', {})
        current = parse_hex(appearance.get('fill', '#808080'))
        target_l = luminance(current)
        new = tinted(target_l, hue, sat)
        appearance['fill'] = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(c)))) for c in new)
        got = luminance(parse_hex(appearance['fill']))
        if target_l > 1e-6:
            drifts.append(abs(got - target_l) / target_l)
        hues.append(hue)

    pathlib.Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    if not drifts:
        print('  nothing filled')
        return 1
    print('  %d shapes tinted from the reference' % len(drifts))
    print('  hue spread: min %.3f  median %.3f  max %.3f' % (min(hues), float(np.median(hues)), max(hues)))
    print('  value drift: mean %.5f  worst %.5f  limit %.4f'
          % (float(np.mean(drifts)), max(drifts), args.limit))
    if max(drifts) <= args.limit:
        print('  within the limit: hue and saturation came from the picture, lightness did not move')
        return 0
    print('  over the limit')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
