"""The shapes come from the reference's own colours, not from its brightness.

**Why the value layer was rebuilt.** It used to cut the figure into connected sets at one *brightness*. On a second
reference that put a face, a dress and the background into a single shape, because all three happened to share a
luminance; tinting that shape from its own pixels averaged three materials and the skin came out violet-grey.

**What is kept and what is replaced.** The value guard stays -- lightness must not move -- but its argument changes: a
shape taken from one colour area already holds one material, so the colour under it *is* its colour, and the lightness
that comes out is the reference's own. What replaces the cut is a quantisation: ten levels per channel, one connected set
per quantised colour, and every speck folded into the neighbour it shares the most border with, so the figure is covered
completely and no shape is smaller than the eye reads it.

**The consequence the gradient pass needs.** A shape is no longer one grey plus a hue found elsewhere; it is one colour.
A gradient fitted along such a shape's own axis between two of its colours is a highlight on one material, while the same
fit across a value band was a line drawn between two materials.
"""
import argparse
import json
import pathlib
import sys
import time

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import trace as silhouette
import value_pass


def quantise(rgb, levels, blur):
    soft = ndimage.gaussian_filter(rgb.astype(np.float32), blur)
    step = 1.0 / float(max(2, levels))
    q = np.clip((soft / step).astype(np.int32), 0, levels - 1)
    return q[:, :, 0] * levels * levels + q[:, :, 1] * levels + q[:, :, 2]


def equal_components(key):
    """Connected sets of equal value, in one pass over the canvas.

    **`ndimage.label` joins every non-zero pixel regardless of value.** Cutting by colour with it needs one whole-canvas
    pass per colour, which is five hundred passes over a megapixel canvas. Turning "equal and adjacent" into edges and
    asking for connected components answers the same question in one pass: five hundred times faster on the reference
    this was measured on.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    h, w = key.shape
    idx = np.arange(h * w, dtype=np.int32).reshape(h, w)
    rows = []
    cols = []
    pairs = ((idx[:, :-1], idx[:, 1:], key[:, :-1] == key[:, 1:]),
             (idx[:-1, :], idx[1:, :], key[:-1, :] == key[1:, :]),
             (idx[:-1, :-1], idx[1:, 1:], key[:-1, :-1] == key[1:, 1:]),
             (idx[:-1, 1:], idx[1:, :-1], key[:-1, 1:] == key[1:, :-1]))
    for left, right, same in pairs:
        rows.append(left[same])
        cols.append(right[same])
    r = np.concatenate(rows)
    c = np.concatenate(cols)
    graph = coo_matrix((np.ones(r.size, dtype=np.int8), (r, c)), shape=(h * w, h * w))
    _count, labels = connected_components(graph, directed=False)
    return labels.reshape(h, w).astype(np.int32) + 1


def absorb(labels, min_area):
    """Fold every speck into the neighbour it shares the most border with, in one pass.

    **Dropping a speck leaves a hole in the painting.** Measured: keeping the small shapes out took the covered share of
    the figure from a hundred per cent down to eighty-one, so a fifth of the picture would have been paper. A shape this
    small is noise; the shape beside it is a better guess at what is under it than nothing is.

    **One pass, not a loop of passes.** The earlier version recomputed the whole adjacency of the canvas on every round to
    find that round's specks, and on a picture that cuts into a hundred and thirty-seven thousand pieces at the first
    quantisation it took seventy-six seconds -- with every other stage of the cut under two. Counting the adjacency once,
    then walking the areas from smallest to largest through a union-find, does the same merging in one traversal.
    """
    count = int(labels.max())
    if count < 3:
        return labels
    areas = np.bincount(labels.ravel(), minlength=count + 1).astype(np.int64)
    pairs = []
    for a, b in ((labels[:, 1:], labels[:, :-1]), (labels[1:, :], labels[:-1, :])):
        keep = a != b
        if keep.any():
            pairs.append(np.stack([a[keep], b[keep]], axis=1))
    if not pairs:
        return labels
    both = np.sort(np.concatenate(pairs).astype(np.int64), axis=1)
    uniq, counts = np.unique(both, axis=0, return_counts=True)
    del both, pairs

    neighbours = {}
    for index in range(uniq.shape[0]):
        a = int(uniq[index, 0])
        b = int(uniq[index, 1])
        n = int(counts[index])
        neighbours.setdefault(a, []).append((b, n))
        neighbours.setdefault(b, []).append((a, n))

    parent = np.arange(count + 1, dtype=np.int64)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return int(x)

    # **A few traversals, not one.** A speck that swallows its neighbours can still be under the threshold when it is
    # done, and with a single pass it survives -- measured, that left nine thousand areas where the looping version left
    # two. Re-walking the same adjacency costs a fraction of a second, because the expensive part was counting it.
    for _round in range(12):
        changed = False
        for i in np.argsort(areas[1:], kind='stable'):
            i = int(i) + 1
            if areas[i] >= min_area:
                break
            if find(i) != i:
                continue
            totals = {}
            for j, n in neighbours.get(i, ()):
                root = find(j)
                totals[root] = totals.get(root, 0) + n
            if not totals:
                continue
            target = max(totals.items(), key=lambda item: item[1])[0]
            if target == find(i):
                continue
            parent[find(i)] = target
            areas[target] += areas[i]
            changed = True
        if not changed:
            break

    root = np.array([find(i) for i in range(count + 1)], dtype=np.int32)
    return root[labels]


def colour_table(labels, rgb):
    """The mean colour of every area, and its pixel count, in one pass over the canvas.

    **A mean rather than a median, and the shape is why.** An area here is a connected set at one quantised colour, so the
    pixels inside it are one material by construction: a strand of hair crossing a face lands in a *different* area, not
    in the same one, which is exactly the case a median was guarding against on the old value bands that spanned three
    materials. The cost is the deciding argument anyway -- a median walks each area's own bounding box in turn, and on a
    two-and-a-half thousand wide reference with two thousand areas that is several hundred million comparisons; one
    `bincount` over the canvas gives the whole table. Measured: the per-area median did not finish a run in twelve
    minutes.
    """
    count = int(labels.max())
    flat = labels.ravel().astype(np.int64)
    sums = np.empty((count + 1, 3), dtype=np.float64)
    for channel in range(3):
        sums[:, channel] = np.bincount(flat, weights=rgb[:, :, channel].ravel(), minlength=count + 1)
    counts = np.bincount(flat, minlength=count + 1).astype(np.float64)
    table = (sums / np.maximum(counts, 1.0)[:, None]).astype(np.float32)
    return table, counts


def colour_of(labels, rgb):
    """One colour per shape, plus how far a flat fill of it would be from the reference.

    The error is the measure the cut is judged by, now taken over every pixel at once: paint each pixel with its own
    area's colour and ask how far that is from the picture. **The number is not directly comparable with the earlier
    per-area median** -- that one weighted each area equally and reported its median, this one weights each pixel -- so a
    change of scale here is a change of definition, not a regression.
    """
    table, counts = colour_table(labels, rgb)
    inside = labels > 0
    if inside.any():
        painted = table[labels][inside]
        error = np.abs(rgb[inside] - painted).sum(axis=1) / 3.0
        print('  flat-colour error over the figure: mean %.4f  median %.4f'
              % (float(error.mean()), float(np.median(error))))
    out = {}
    for i in range(1, len(counts)):
        if counts[i] < 4:
            continue
        rgb_i = np.clip(table[i], 0.0, 1.0)
        out[i] = '#%02x%02x%02x' % tuple(int(round(float(c) * 255)) for c in rgb_i)
    return out


def outlines(labels, grow=1, min_area=1):
    """One closed polygon per shape, grown by `grow` pixels so neighbours overlap instead of leaving a seam.

    **Moore tracing walks the pixel edge, so the polygon sits inside the shape.** Two neighbours therefore both give up
    the same half pixel and a white line appears between every pair of shapes -- measured on the first run, it showed as
    a pale gap across the whole figure. Growing each shape by one pixel makes the pair overlap, and the later shape wins,
    which is what happens on paper too: the second colour covers the first along their shared edge.
    """
    count = int(labels.max())
    boxes = ndimage.find_objects(labels)
    areas = np.bincount(labels.ravel(), minlength=count + 1)
    rings = []
    h, w = labels.shape
    for i in range(1, count + 1):
        if areas[i] < min_area or i - 1 >= len(boxes) or boxes[i - 1] is None:
            continue
        ys, xs = boxes[i - 1]
        y0 = max(0, int(ys.start) - grow)
        y1 = min(h, int(ys.stop) + grow)
        x0 = max(0, int(xs.start) - grow)
        x1 = min(w, int(xs.stop) + grow)
        local = (labels[y0:y1, x0:x1] == i).astype(np.uint8)
        if grow:
            local = ndimage.binary_dilation(local, structure=np.ones((3, 3), dtype=bool),
                                            iterations=grow).astype(np.uint8)
        ring = silhouette.boundary(local, local.shape[1], local.shape[0])
        if len(ring) < 6:
            continue
        rings.append((int(areas[i]), i, [(int(x) + x0, int(y) + y0) for x, y in ring]))
    return rings


def simplify_ring(ring, tol):
    """A ring reduced to the points that carry its shape, split at the far point so both halves stay open lines.

    **Douglas-Peucker keeps the first and the last point**, and on a closed ring those are the same point, so the walk
    around the ring is cut at the point furthest from the start and each half simplified as its own line. Without this
    the polygons come out with three hundred and fifty thousand points, because a nearest-neighbour upscale leaves every
    boundary as a staircase of single pixels.
    """
    if len(ring) < 8 or tol <= 0:
        return ring
    pts = np.asarray(ring, dtype=np.float64)
    far = int(np.hypot(pts[:, 0] - pts[0, 0], pts[:, 1] - pts[0, 1]).argmax())
    if far < 2 or far >= len(pts) - 2:
        return ring
    first = [(int(x), int(y)) for x, y in silhouette.douglas_peucker(pts[:far + 1], tol)]
    second = [(int(x), int(y)) for x, y in silhouette.douglas_peucker(np.vstack([pts[far:], pts[:1]]), tol)]
    out = first[:-1] + second[:-1]
    return out if len(out) >= 4 else ring


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True)
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--levels', type=int, default=20, help='quantisation levels per channel')
    ap.add_argument('--blur', type=float, default=1.0)
    ap.add_argument('--min-area', type=int, default=150, help='shapes below this, at the cut size, are folded away')
    ap.add_argument('--work-side', type=float, default=0.0,
                    help='if set, shrink the cut to this long side; a large reference is expensive because the cut is a '
                         'connected-components pass over every pixel. Zero leaves the reference at its own size')
    ap.add_argument('--cut-side', type=float, default=0.0,
                    help='explicit long side to cut at; may exceed the reference, which interpolates it smoothly rather '
                         'than inventing detail. Zero takes the rule described below')
    ap.add_argument('--upscale-cap', type=float, default=2400.0,
                    help='how far a small reference may be enlarged before the cut, in pixels on the long side')
    ap.add_argument('--simplify', type=float, default=0.0,
                    help='boundary tolerance in canvas pixels; zero means one pixel at the cut size')
    args = ap.parse_args()

    doc = json.loads(pathlib.Path(args.project).read_text(encoding='utf-8'))
    canvas = doc.get('canvas') or {}
    width, height = int(canvas.get('width', 0)), int(canvas.get('height', 0))
    if not width or not height:
        print('  the project has no canvas size')
        return 1

    image = Image.open(args.reference).convert('RGB')
    # **The cut size and the reference size are two different things.** Cutting at the reference's own size is cheap and
    # loses nothing on a large one, but on a six-hundred-wide reference every area is nineteen pixels across and its
    # boundary is stubble. Cutting at the canvas size costs more and invents no detail -- but the interpolation makes the
    # colour continuous across the bigger grid, so a boundary is a smooth curve there instead of a staircase of the small
    # grid scaled up. Measured on the 600x800 reference: cutting at its own size gave a whole-image p90 of 0.3961, at the
    # canvas 0.2484, at 2400 0.2536 -- so the gain is in leaving the small grid, not in matching the canvas exactly.
    #
    # **The reference is never shrunk**, because shrinking it throws away the detail the cut is reading; only a reference
    # smaller than the canvas is enlarged, and then only up to `--upscale-cap`, because the cut is a connected-components
    # pass over every pixel and a twelve-megapixel canvas took over fifteen minutes for a 1.2x gain.
    reference_long = float(max(image.size))
    if args.cut_side:
        target = args.cut_side
    else:
        target = max(reference_long, min(float(max(width, height)), args.upscale_cap))
        if args.work_side:
            target = min(target, args.work_side)
    scale = target / reference_long
    work = image
    if abs(scale - 1.0) > 1e-6:
        work = image.resize((max(1, int(round(image.size[0] * scale))), max(1, int(round(image.size[1] * scale)))),
                            Image.LANCZOS)
    area_threshold = max(1, int(round(args.min_area * scale * scale)))
    blur = args.blur * scale
    rgb = np.asarray(work, dtype=np.float32) / 255.0
    w, h = rgb.shape[1], rgb.shape[0]
    gray = (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]).astype(np.float32)

    # **A step that prints nothing for fifteen minutes is not diagnosable.** The cut has four stages whose costs differ by
    # two orders of magnitude depending on the picture, and three separate runs were spent guessing which one was slow.
    mark = time.perf_counter()

    def tick(label):
        nonlocal mark
        now = time.perf_counter()
        print('    %6.1fs  %s' % (now - mark, label))
        mark = now

    person = value_pass.person_mask(gray)
    tick('figure mask')

    key = np.where(person, quantise(rgb, args.levels, blur), -1)
    labels = equal_components(key)
    labels = np.where(person, labels, 0)
    tick('colour areas')
    before = int(np.count_nonzero(np.bincount(labels.ravel())[1:]))
    labels = absorb(labels, area_threshold)
    after = int(np.count_nonzero(np.bincount(labels.ravel())[1:]))
    areas = np.bincount(labels.ravel())
    tick('specks folded away')
    print('  cut at %dx%d, figure %.1f%% of the page: %d shapes, specks folded away leaving %d covering %.1f%%'
          % (w, h, 100.0 * person.sum() / (w * h), before, after,
             100.0 * areas[1:].sum() / max(1.0, float(person.sum()))))

    colours = colour_of(labels, rgb)
    tick('colours')

    # **The cut is written out beside the project, at the size it was made.** The line layer reads these instead of
    # cutting the reference a second time: two cuts of the same picture with the same settings are the same labels in
    # theory and one pixel apart in practice, and a line one pixel off its own boundary reads as a mistake.
    stem = pathlib.Path(args.out)
    labels_path = stem.with_name('%s-labels.npy' % stem.stem)
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(labels_path, labels)
    meta_path = stem.with_name('%s-meta.json' % stem.stem)
    meta_path.write_text(json.dumps({'cut': [w, h], 'canvas': [width, height], 'scale': scale,
                                     'levels': args.levels, 'blur': blur, 'min_area': area_threshold}),
                         encoding='utf-8')
    print('    areas written to %s' % labels_path.name)

    # **Scaled to the drawing's canvas before the outlines are taken.** The cut is made where it is affordable; the
    # polygons are built at the size the picture is drawn at, so a boundary is one canvas pixel and not a visible step.
    grow = float(width) / float(w)
    if (w, h) != (width, height):
        labels = np.asarray(Image.fromarray(labels, mode='I').resize((width, height), Image.NEAREST))
    tick('scaled to the canvas')

    rings = outlines(labels, grow=max(1, int(round(grow))), min_area=1)
    tick('outlines traced')
    tol = args.simplify if args.simplify > 0 else max(1.5, grow)
    rings = [(area, label, simplify_ring(ring, tol)) for area, label, ring in rings]
    tick('outlines simplified')
    # **Largest first.** A shape drawn later covers what was drawn before, so a small shape sits in the hole its larger
    # neighbour has instead of being painted over by it.
    rings.sort(key=lambda item: -item[0])

    new_marks = []
    for seq, (area, label, ring) in enumerate(rings, start=1):
        new_marks.append({
            'id': 's%05d' % seq,
            'kind': 'fill',
            'stage': 'colour',
            'seq': seq,
            'layer': 'value',
            'geometry': {'points': [list(p) for p in ring],
                         'd': 'M ' + ' L '.join('%d %d' % p for p in ring) + ' Z'},
            'appearance': {'fill': colours.get(label, '#808080'), 'opacity': 1.0, 'blend': 'normal'},
            'provenance': {'source': args.reference, 'note': 'colour area', 'turn': 0},
            'state': 'live',
        })
    print('  %d shapes to draw, %d points in total'
          % (len(new_marks), sum(len(m['geometry']['points']) for m in new_marks)))

    out_doc = dict(doc)
    for i, mark in enumerate(out_doc.get('marks', [])):
        mark['seq'] = len(new_marks) + i
    out_doc['marks'] = new_marks + out_doc.get('marks', [])
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps(out_doc, ensure_ascii=False, separators=(',', ':')),
                                      encoding='utf-8')
    print('  %d shapes under %d line marks, written to %s'
          % (len(new_marks), len(doc.get('marks', [])), args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
