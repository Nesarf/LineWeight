"""The value pass, taken off the reference instead of chosen: three bands of grey under a traced line drawing.

**What was wrong with the first attempt.** It ran on the figure this project draws itself -- a capsule trunk and two
sticks -- which was already judged not worth tuning. **A value pass demonstrated on a drawing nobody wants is a
demonstration of nothing.** The line layer here is a traced reference, and the values are read off that same reference.

**How the values are read.** The reference is reduced to the drawing's own canvas, the person is found as the largest
region that is not paper, and what is inside is quantised into three bands by brightness. **The bands are drawn light to
dark**, so the dark one lands on top of the others the way ink would, and the whole thing sits under the line layer.

**Three bands and not a gradient.** The procedure being followed lays a flat desaturated layer over the whole figure and
fixes the value in one move; a smooth gradient would carry shading detail that the light pass is not allowed to decide.

    python tools/value_pass.py --project maid.json --reference huaban-768347567.jpg --out maid-value.json
"""
import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from lineweight import core, project

import trace as silhouette

#: Paper is anything this bright, as a fraction. **The reference's own white is not 1.0** -- a photographed pencil
#: drawing has grey in its paper, and a threshold of 0.98 would call the whole page a person.
PAPER = 0.93

#: Light to dark, each with the fraction of brightness it covers. The greys are the same value on every channel, which
#: is what makes this pass a value pass: there is no colour here to move.
BANDS = ((0.86, (0.86, None)), (0.58, (0.58, None)), (0.28, (0.28, None)))


def person_mask(gray):
    """The figure's interior: **the region a closed outline encloses**, not the ink itself.

    **A line drawing is almost all paper by area**, so "not paper" is a few thousand pixels of line and putting a value
    under that paints the lines rather than the person. What has to be found is what the outline encloses, which is a
    hole-filling problem: close the gaps enough that the outline is a loop, fill what it holds, and take the largest
    piece. If the loop does not close, the fill leaks and covers the page -- so the closing is tried at three widths and
    the first result that is still a figure rather than a flood is the one used.
    """
    from scipy import ndimage
    ink = (gray < PAPER).astype(np.uint8)
    structure = np.ones((3, 3), dtype=bool)
    biggest = ink.astype(bool)
    for iterations in (3, 8, 16):
        closed = ndimage.binary_closing(ink, structure=structure, iterations=iterations).astype(np.uint8)
        filled = ndimage.binary_fill_holes(closed).astype(np.uint8)
        labels, count = ndimage.label(filled, structure=np.ones((3, 3), dtype=np.uint8))
        if not count:
            continue
        sizes = ndimage.sum(filled, labels, range(1, count + 1))
        piece = labels == (int(np.argmax(sizes)) + 1)
        biggest = piece
        # **A flood is not a figure.** Past three quarters of the page the outline never closed and the fill escaped; a
        # wider closing is the only thing that can help, and past the last one the ink itself is returned.
        if piece.sum() < 0.75 * gray.size:
            return piece
    return biggest


def band_masks(gray, person):
    """Three bands of brightness inside the person, from light to dark."""
    out = []
    lo_edges = [0.0, 0.45, 0.72]
    for lo in lo_edges:
        if lo == 0.0:
            mask = person.copy()
        else:
            mask = person & (gray < lo)
        out.append(mask)
    return out


def outline_of(mask):
    """Every connected piece of a mask, as a closed polygon in canvas coordinates."""
    from scipy import ndimage
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    rings = []
    for i in range(1, count + 1):
        blob = (labels == i)
        if int(blob.sum()) < 60:
            continue
        ys, xs = np.nonzero(blob)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        local = blob[y0:y1, x0:x1].astype(np.uint8)
        ring = silhouette.boundary(local, x1 - x0, y1 - y0)
        if len(ring) >= 8:
            rings.append([(x + x0, y + y0) for x, y in ring])
    return rings


def region_of(points):
    d = 'M ' + ' L '.join('%.2f %.2f' % (x, y) for x, y in points) + ' Z'
    return core.Region(points=[tuple(p) for p in points], d=d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True)
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.project).read_text(encoding='utf-8'))
    canvas = doc.get('canvas') or {}
    w, h = int(canvas.get('width', 0)), int(canvas.get('height', 0))
    if not w or not h:
        print('  the project has no canvas size')
        return 1

    from PIL import Image
    img = Image.open(args.reference).convert('L').resize((w, h), Image.LANCZOS)
    gray = np.asarray(img, dtype=np.float32) / 255.0
    person = person_mask(gray)
    print('  %s at %dx%d; person covers %.1f%% of the page'
          % (pathlib.Path(args.reference).name, w, h, 100.0 * person.sum() / (w * h)))

    fills = []
    for lo, (grey, _unused) in ((0.0, BANDS[0]), (0.45, BANDS[1]), (0.72, BANDS[2])):
        if lo == 0.0:
            mask = person.copy()
        else:
            mask = person & (gray < lo)
        rings = outline_of(mask)
        level = int(round(grey * 255))
        for ring in rings:
            fills.append({'ring': ring, 'grey': level})
        print('    band at %.2f grey: %d shapes' % (grey, len(rings)))

    # **The fills go under the lines.** A project is drawn in order, so the new marks are placed first and the existing
    # strokes after them; appending would put flat grey over the drawing that defines the shapes.
    out_doc = dict(doc)
    new_marks = []
    counter = 0
    for item in fills:
        counter += 1
        new_marks.append({
            'id': 'v%04d' % counter,
            'kind': 'fill',
            'stage': 'colour',
            'seq': counter,
            'layer': 'value',
            'geometry': {'points': [list(p) for p in item['ring']],
                         'd': 'M ' + ' L '.join('%.2f %.2f' % p for p in item['ring']) + ' Z'},
            'appearance': {'fill': '#%02x%02x%02x' % (item['grey'], item['grey'], item['grey']),
                           'opacity': 1.0, 'blend': 'normal'},
            'provenance': {'source': args.reference, 'note': 'value band', 'turn': 0},
            'state': 'live',
        })
    for i, mark in enumerate(out_doc.get('marks', [])):
        mark['seq'] = len(new_marks) + i
    out_doc['marks'] = new_marks + out_doc.get('marks', [])
    pathlib.Path(args.out).write_text(json.dumps(out_doc, ensure_ascii=False, separators=(',', ':')),
                                      encoding='utf-8')
    print('  %d value shapes under %d line marks, written to %s'
          % (len(new_marks), len(doc.get('marks', [])), args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
