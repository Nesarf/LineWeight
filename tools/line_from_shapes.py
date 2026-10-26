"""The line, taken from the boundaries between colour areas instead of from the gradient.

**The two layers were deciding the same thing twice and disagreeing.** The fills say where the materials are: colour
areas covering the figure, and the error of painting each with its own colour is 0.0176. The strokes say where the joins
are -- but they are found from the gradient, so a cheek's shading boundary is as strong an edge as a jaw, and on the
reference measured here the result was twenty-odd strokes across a face and none on an eye.

**A boundary between two colour areas is a place where the material changes**, which is what a line in a cel drawing is.
So the candidate set becomes the set of label edges.

**How strong a line is comes from the two areas, not from the edge.** The difference between the two colours a boundary
separates is stable -- it is measured over hundreds of pixels of two smoothed areas, not over one pixel of gradient -- so
a join between skin and hair can be drawn heavy while a join between a cheek and its own shadow is drawn faint. That
replaces a single threshold on edge strength with a ratio between the two sides of the line, and it is the same statement
the light rule makes: the side away from the light gets the weight.

    python tools/line_from_shapes.py --reference "...jpg" --out edges.png
"""
import argparse
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import shape_pass
import value_pass

NEIGHBOURS = ((0, 1), (1, 0), (1, 1), (1, -1))


def label_edges(labels):
    """Every neighbouring pair of pixels that carries two different labels, with the pair recorded.

    **Eight neighbours, not four.** A diagonal join has no side neighbour on either cell, so a four-connected test leaves
    the whole staircase of a diagonal boundary out -- and a diagonal boundary is what most contours are.
    """
    pairs = []
    for dy, dx in NEIGHBOURS:
        a = labels[max(0, dy):labels.shape[0] + min(0, dy), max(0, dx):labels.shape[1] + min(0, dx)]
        b = labels[max(0, -dy):labels.shape[0] + min(0, -dy), max(0, -dx):labels.shape[1] + min(0, -dx)]
        same = a == b
        if (~same).any():
            ya, xa = np.nonzero(~same)
            low = np.minimum(a[~same], b[~same]).astype(np.int32)
            high = np.maximum(a[~same], b[~same]).astype(np.int32)
            pairs.append((ya + max(0, dy), xa + max(0, dx), low, high))
    return pairs


def colour_table(labels, rgb):
    """The median colour of every area, taken over the pixels inside it."""
    from scipy import ndimage
    count = int(labels.max())
    boxes = ndimage.find_objects(labels)
    table = np.zeros((count + 1, 3), dtype=np.float32)
    for i in range(1, count + 1):
        box = boxes[i - 1] if i - 1 < len(boxes) else None
        if box is None:
            continue
        ys, xs = box
        patch = rgb[ys, xs][labels[ys, xs] == i]
        if patch.size:
            table[i] = np.median(patch, axis=0)
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--levels', type=int, default=20)
    ap.add_argument('--blur', type=float, default=1.0)
    ap.add_argument('--min-area', type=int, default=150)
    ap.add_argument('--work-side', type=float, default=1600.0)
    ap.add_argument('--faint', type=float, default=0.06, help='colour difference below which a join draws nothing')
    ap.add_argument('--heavy', type=float, default=0.30, help='colour difference at which a join draws full weight')
    ap.add_argument('--ink', type=float, default=1.0, help='the darkest a line gets, as a fraction of full ink')
    args = ap.parse_args()

    image = Image.open(args.reference).convert('RGB')
    scale = min(1.0, args.work_side / float(max(image.size)))
    work = image
    if scale < 1.0:
        work = image.resize((max(1, int(round(image.size[0] * scale))), max(1, int(round(image.size[1] * scale)))),
                            Image.LANCZOS)
    rgb = np.asarray(work, dtype=np.float32) / 255.0
    w, h = rgb.shape[1], rgb.shape[0]
    gray = (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)
    person = value_pass.person_mask(gray)

    key = np.where(person, shape_pass.quantise(rgb, args.levels, args.blur), -1)
    labels = shape_pass.equal_components(key)
    labels = np.where(person, labels, 0)
    labels = shape_pass.absorb(labels, args.min_area)
    table = colour_table(labels, rgb)

    weight = np.zeros((h, w), dtype=np.float32)
    differences = []
    for ya, xa, low, high in label_edges(labels):
        diff = np.abs(table[low] - table[high]).sum(axis=1) / 3.0
        # **The darkest of the eight neighbour passes wins.** A join reached from two directions would otherwise be drawn
        # once faint and once heavy depending on which pass got there last.
        np.maximum.at(weight, (ya, xa), diff)
        differences.append(diff)
    flat = np.concatenate(differences) if differences else np.zeros(1)
    span = args.heavy - args.faint
    strength = np.clip((weight - args.faint) / max(1e-6, span), 0.0, 1.0)
    ink = 1.0 - args.ink * strength
    out = np.repeat(ink[:, :, None], 3, axis=2)
    print('  %d colour areas; %d boundary pixels; colour difference median %.3f  p90 %.3f'
          % (int(labels.max()), int((weight > 0).sum()), float(np.median(flat)), float(np.percentile(flat, 90))))
    print('  joins above the faint floor: %.1f%% of the boundary' % (100.0 * float((weight > args.faint).mean()
                                                                                    / max(1e-9, float((weight > 0).mean())))))
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8)).save(target)
    print('  wrote %s' % target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
