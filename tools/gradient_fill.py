"""Give each filled shape the gradient the reference has inside it.

**What a single fill colour cannot say.** A painted garment varies inside one piece of material -- it is darker where it
turns away and lighter where the light catches it -- and a flat fill states one value for the whole piece. Splitting the
shape into more shapes was tried and fragmented it fivefold while saying the same thing. The shape is right; what it
needs is a value that varies across it.

**Fitted along the shape's own principal axis, not a fixed direction.** The pixels inside the shape are projected onto
their longest spread and the two ends of that projection give the two colours, so a highlight that runs down a thigh
becomes a gradient down the thigh rather than left to right.

**Lightness is preserved.** The two endpoint colours are scaled so that their average luminance matches the flat colour
the shape already had, which keeps the value decision from the earlier stage intact.
"""
import argparse
import json
import pathlib

import numpy as np
from PIL import Image, ImageDraw

WR, WG, WB = 0.2126, 0.7152, 0.0722


def parse_hex(text):
    text = text.lstrip('#')
    return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def to_hex(rgb):
    return '#%02x%02x%02x' % tuple(int(max(0, min(255, round(c)))) for c in rgb)


def luminance(rgb):
    return float((np.asarray(rgb, dtype=np.float64) / 255.0) @ np.array([WR, WG, WB]))


def shaped_mask(points, x0, y0, x1, y1):
    w, h = x1 - x0 + 1, y1 - y0 + 1
    canvas = Image.new('L', (w, h), 0)
    ImageDraw.Draw(canvas).polygon([(p[0] - x0, p[1] - y0) for p in points], fill=255)
    return np.asarray(canvas) > 127


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-pixels', type=int, default=400, help='smaller shapes stay flat')
    ap.add_argument('--blur', type=float, default=3.0, help='smoothing before the fit, in page pixels')
    ap.add_argument('--limit', type=float, default=0.05)
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.src).read_text(encoding='utf-8'))
    canvas = doc.get('canvas') or {}
    width = int(canvas.get('width') or 0)
    height = int(canvas.get('height') or 0)
    image = Image.open(args.reference).convert('RGB')
    if image.size != (width, height):
        image = image.resize((width, height), Image.LANCZOS)
    pixels = np.asarray(image, dtype=np.float64)

    done = 0
    drifts = []
    for mark in doc.get('marks', []):
        if mark.get('kind') != 'fill':
            continue
        geometry = mark.get('geometry') or {}
        points = geometry.get('points') or []
        if len(points) < 3:
            continue
        pts = np.asarray(points, dtype=np.float64)
        x0 = int(max(0, np.floor(pts[:, 0].min())))
        y0 = int(max(0, np.floor(pts[:, 1].min())))
        x1 = int(min(width - 1, np.ceil(pts[:, 0].max())))
        y1 = int(min(height - 1, np.ceil(pts[:, 1].max())))
        if x1 <= x0 or y1 <= y0:
            continue
        mask = shaped_mask(points, x0, y0, x1, y1)
        if int(mask.sum()) < args.min_pixels:
            continue
        patch = pixels[y0:y1 + 1, x0:x1 + 1][mask]
        ys, xs = np.nonzero(mask)
        coords = np.stack([xs, ys], axis=1).astype(np.float64)
        coords -= coords.mean(axis=0)
        cov = coords.T @ coords / len(coords)
        weights, vectors = np.linalg.eigh(cov)
        axis = vectors[:, int(np.argmax(weights))]
        projection = coords @ axis
        low = float(np.percentile(projection, 10.0))
        high = float(np.percentile(projection, 90.0))
        if high - low < 4.0:
            continue
        colour0 = patch[projection <= low].mean(axis=0)
        colour1 = patch[projection >= high].mean(axis=0)
        # **Lightness preserved**: scale both ends so their mean luminance equals the flat fill's.
        flat = parse_hex((mark.get('appearance') or {}).get('fill', '#808080'))
        want = luminance(flat)
        got = 0.5 * (luminance(colour0) + luminance(colour1))
        if got > 1e-6 and want > 1e-6:
            scale = want / got
            colour0 = np.clip(colour0 * scale, 0, 255)
            colour1 = np.clip(colour1 * scale, 0, 255)
            drifts.append(abs(0.5 * (luminance(colour0) + luminance(colour1)) - want) / want)
        centre = coords.mean(axis=0) + np.array([x0, y0])
        p0 = centre + axis * low
        p1 = centre + axis * high
        geometry['gradient'] = {
            'from': [float(p0[0]), float(p0[1])],
            'to': [float(p1[0]), float(p1[1])],
            'colour0': to_hex(colour0),
            'colour1': to_hex(colour1),
        }
        done += 1

    pathlib.Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('  %d shapes given a gradient' % done)
    if drifts:
        print('  value drift: mean %.5f  worst %.5f  limit %.4f'
              % (float(np.mean(drifts)), max(drifts), args.limit))
    print('  written to %s' % args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
