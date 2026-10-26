"""Measure whether a value shape belongs to one material, and which way of cutting gives that.

**The fault this measures.** A value shape is a connected set of pixels at one brightness. On a second reference that
made the skin come out violet-grey: one shape held part of a face, part of a dress and part of the background, because
those three happen to share a luminance. Tinting such a shape from its own pixels averages three materials into one hue.

**So the question is not how many shapes there are but whether a shape holds one colour.** Two cuttings are compared
here -- connected sets at one brightness, and connected sets at one quantised colour -- and both are scored the same way:
paint each shape with its own mean colour and measure, per pixel, how far that flat colour is from the reference. A
shape that holds one material scores near zero; a shape that spans three scores its own average distance from all three.

Writes nothing but numbers, so the decision to change the value layer is made on a measurement and not on one picture
looking wrong.
"""
import argparse
import colorsys
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import value_pass


def person_of(rgb):
    gray = (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)
    return value_pass.person_mask(gray), gray


def hue_spread(patch):
    """How far apart the hues inside a patch are, weighted by saturation. One material is near zero.

    Hue is circular, so a mean of the angles is wrong: red at 0.98 and red at 0.02 average to 0.5, which is cyan. The
    spread is therefore one minus the length of the mean unit vector in the hue plane.
    """
    if patch.shape[0] < 16:
        return 0.0
    mx = patch.max(axis=1)
    mn = patch.min(axis=1)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    if float(sat.sum()) < 1e-6:
        return 0.0
    r, g, b = patch[:, 0], patch[:, 1], patch[:, 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.empty_like(r)
    top = (mx == r)
    mid = (mx == g) & ~top
    low = ~(top | mid)
    hue[top] = ((g[top] - b[top]) / d[top]) % 6.0
    hue[mid] = (b[mid] - r[mid]) / d[mid] + 2.0
    hue[low] = (r[low] - g[low]) / d[low] + 4.0
    ang = hue / 6.0 * 2.0 * np.pi
    w = sat / sat.sum()
    length = float(np.hypot((w * np.cos(ang)).sum(), (w * np.sin(ang)).sum()))
    return max(0.0, 1.0 - length)


def absorb(labels, min_area, rounds=6):
    """Fold every speck into the neighbouring shape it shares the most border with.

    **Dropping a small shape leaves a hole in the painting.** The first version set specks to zero, so a tenth of the
    figure had no shape over it and would come out as paper. A speck is small, so the shape beside it is a better guess
    at what is underneath than nothing is -- the same argument the closing uses on a line drawing, applied to area
    instead of to outline.
    """
    for _ in range(rounds):
        areas = np.bincount(labels.ravel())
        small = [int(s) for s in np.flatnonzero(areas < max(1, min_area)) if s > 0]
        if not small:
            break
        wanted = set(small)
        pairs = []
        for a, b in ((labels[:, 1:], labels[:, :-1]), (labels[1:, :], labels[:-1, :])):
            keep = a != b
            if keep.any():
                pairs.append(np.stack([a[keep], b[keep]], axis=1))
        if not pairs:
            break
        both = np.sort(np.concatenate(pairs).astype(np.int32), axis=1)
        uniq, counts = np.unique(both, axis=0, return_counts=True)
        size = int(labels.max()) + 1
        best = np.zeros(size, dtype=np.int64)
        want = np.zeros(size, dtype=np.int64)
        for (a, b), n in zip(uniq, counts):
            a, b = int(a), int(b)
            if a in wanted and n > best[a]:
                best[a], want[a] = n, b
            if b in wanted and n > best[b]:
                best[b], want[b] = n, a
        changed = False
        for s in small:
            if want[s]:
                labels[labels == s] = want[s]
                changed = True
        if not changed:
            break
    return labels


def score(labels, count, rgb, person, name):
    """Flat-colour error per shape: the distance from a shape's own mean colour to each of its pixels.

    **One pass over the picture, not one per shape.** Touching `labels == i` for every shape in turn walks the whole
    canvas once per shape, which is what made the first version take a minute for five hundred shapes.
    """
    from scipy import ndimage
    areas = np.bincount(labels.ravel(), minlength=count + 1)
    boxes = ndimage.find_objects(labels)
    errors = []
    weights = []
    spreads = []
    for i in range(1, count + 1):
        if areas[i] < 120 or boxes[i - 1] is None:
            continue
        ys, xs = boxes[i - 1]
        local = labels[ys, xs] == i
        patch = rgb[ys, xs][local]
        mean = patch.mean(axis=0)
        dist = np.abs(patch - mean).sum(axis=1) / 3.0
        errors.append(float(np.median(dist)))
        weights.append(int(areas[i]))
        spreads.append(hue_spread(patch))
    if not errors:
        print('  %-10s no shapes' % name)
        return
    errors = np.asarray(errors)
    weights = np.asarray(weights, dtype=np.float64)
    spreads = np.asarray(spreads)
    order = np.argsort(errors)
    cum = np.cumsum(weights[order]) / weights.sum()
    median = float(errors[order][np.searchsorted(cum, 0.5)])
    p90 = float(errors[order][np.searchsorted(cum, 0.9)])
    covered = float(sum(weights)) / float(person.sum())
    print('  %-10s %5d shapes  cover %5.1f%% of the figure  flat-colour error: median %.4f  p90 %.4f  '
          'hue spread: median %.3f  p90 %.3f'
          % (name, len(errors), 100.0 * covered, median, p90, float(np.median(spreads)),
             float(np.percentile(spreads, 90))))


def grey_shapes(gray, person, bands, min_area=0):
    from scipy import ndimage
    inside = gray[person]
    centres = value_pass.kmeans_1d(inside, bands)
    flat = np.abs(gray.reshape(-1, 1) - centres.reshape(1, -1)).argmin(axis=1).reshape(gray.shape)
    labels = np.zeros(gray.shape, dtype=np.int32)
    count = 0
    structure = np.ones((3, 3), dtype=np.uint8)
    for i in range(len(centres)):
        mask = (person & (flat == i)).astype(np.uint8)
        part, n = ndimage.label(mask, structure=structure)
        part[part > 0] += count
        labels = np.maximum(labels, part.astype(np.int32))
        count += n
    if min_area > 0:
        labels = absorb(labels, min_area)
    return labels, count, centres


def equal_components(key, eight=True):
    """Connected sets of *equal* value, in one pass.

    **`ndimage.label` joins every non-zero pixel regardless of value**, so cutting the picture by colour with it needed
    one whole-canvas pass per colour -- five hundred passes over a megapixel canvas. Turning the "equal and adjacent"
    relation into edges and asking for connected components answers the same question in one pass.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    h, w = key.shape
    idx = np.arange(h * w, dtype=np.int32).reshape(h, w)
    rows = []
    cols = []
    same = key[:, 1:] == key[:, :-1]
    rows.append(idx[:, :-1][same])
    cols.append(idx[:, 1:][same])
    same = key[1:, :] == key[:-1, :]
    rows.append(idx[:-1, :][same])
    cols.append(idx[1:, :][same])
    if eight:
        same = key[1:, 1:] == key[:-1, :-1]
        rows.append(idx[:-1, :-1][same])
        cols.append(idx[1:, 1:][same])
        same = key[1:, :-1] == key[:-1, 1:]
        rows.append(idx[:-1, 1:][same])
        cols.append(idx[1:, :-1][same])
    r = np.concatenate(rows)
    c = np.concatenate(cols)
    graph = coo_matrix((np.ones(r.size, dtype=np.int8), (r, c)), shape=(h * w, h * w))
    count, labels = connected_components(graph, directed=False)
    return labels.reshape(h, w).astype(np.int32), int(count)


def colour_shapes(rgb, person, levels, blur, min_area):
    """Connected sets of one quantised colour, cut inside the figure.

    **The quantisation is the whole point.** Levels are coarse on purpose: 8 per channel is thirty-two levels of
    brightness, which separates a white dress from skin and a stocking from shadow while keeping the folds of one
    material inside a single area. Finer than that and every brush stroke becomes a shape of its own.
    """
    from scipy import ndimage
    soft = ndimage.gaussian_filter(rgb.astype(np.float32), blur)
    # **The step is in the units the array is in.** `region_edges` works on 0..255; this array was divided by 255 by the
    # caller, so a step of 256/levels floors every channel to zero and the whole figure becomes one shape of colour zero.
    step = 1.0 / float(max(2, levels))
    q = np.clip((soft / step).astype(np.int32), 0, levels - 1)
    key = (q[:, :, 0] * levels + q[:, :, 1]) * levels + q[:, :, 2]
    key = np.where(person, key, -1)
    labels, _count = equal_components(key)
    labels = np.where(person, labels + 1, 0)
    if min_area > 0:
        labels = absorb(labels, min_area)
    return labels, int(labels.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True)
    ap.add_argument('--canvas-side', type=float, default=1440)
    ap.add_argument('--bands', type=int, default=4)
    ap.add_argument('--levels', type=int, default=8)
    ap.add_argument('--blur', type=float, default=2.0)
    ap.add_argument('--min-area', type=int, default=120)
    args = ap.parse_args()

    image = Image.open(args.reference).convert('RGB')
    scale = args.canvas_side / float(max(image.size))
    if scale < 1.0:
        image = image.resize((max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale))), Image.LANCZOS)
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    h, w = rgb.shape[:2]
    person, gray = person_of(rgb)
    print('  %s at %dx%d; the figure covers %.1f%% of the page'
          % (pathlib.Path(args.reference).name, w, h, 100.0 * person.sum() / (w * h)))

    labels, count, centres = grey_shapes(gray, person, args.bands, args.min_area)
    print('  bands light to dark: %s' % ', '.join('%.2f' % c for c in centres[::-1]))
    score(labels, count, rgb, person, 'grey')

    labels, count = colour_shapes(rgb, person, args.levels, args.blur, args.min_area)
    score(labels, count, rgb, person, 'colour')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
