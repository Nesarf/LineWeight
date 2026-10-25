"""Copy a line drawing: ink to a one-pixel skeleton, skeleton to fitted polylines, polylines to strokes.

**What this is, and what it is not.** It is a trace, in the sense a beginner traces: the line running down the inside of
an arm comes out where the reference has it, with the reference's wobble in it. It is not a reconstruction -- nothing is
read here about a shoulder being a ball or an elbow a hinge. **Tracing first is the point**: a reconstruction has to be
checked against something, and this produces the something.

**Three steps, each with one rule.**

    ink        a pixel is ink when it is far enough from the paper's own brightness
    skeleton   Zhang-Suen thinning, so a stroke is one pixel wide wherever it is drawn thin or thick
    polylines  end points and junctions become the ends of a segment, and each run between them is one line

**Why the skeleton matters.** Without it, an ink region two pixels across traced along its boundary gives two parallel
lines where the artist drew one, which the project already paid for once. The skeleton is the line the artist meant.

    python tools/copy_linework.py --src "E:\\DaShaoHuo\\downloads\\pixiv-senga\\150921295.jpg" --render
"""
import argparse
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project

#: **The shortest the long side may be, and it may never be shorter.** Illustrations are commonly larger than this, and
#: the trace must not shrink them: the first attempt downscaled to 480 and the ink count went from 7614 to 15, because a
#: one-pixel line does not survive being averaged. A reference smaller than this is enlarged instead, so that the
#: geometry is always taken at a working size where a line is a line -- **the enlargement adds no information, it keeps
#: the scale at which the reading happens constant.**
MIN_LONG_SIDE = 2880

#: How far from white a pixel has to be to count as ink, out of 255. **A pencil line is grey, not black**: at 110 this
#: reference kept 5036 pixels and at 180 it keeps 7614, and the difference is the line's soft edge rather than noise.
INK = 205

#: The page the strokes are rendered onto, long side. **2880 is a floor, not a default.**
#:
#: Two rules meet here. The long side of a drawing from this tool is never below 2880, which is also the size the
#: reference is read at, so the two are on the same grid and no resampling stands between them. And when a reference
#: happens to be smaller than that, its own smaller size is what the comparison is made at: the drawing is scaled down
#: to the reference, and the difference there is what the one per cent standard is measured on.
CANVAS_SIDE = 2880

#: Segments shorter than this many pixels are dropped. **They are what a skeleton leaves at every junction** -- two or
#: three pixels of a stub -- and drawn they read as dirt on the page.
MIN_SEGMENT = 6


def load_ink(path, min_long_side, ink, min_component=30):
    """Ink as a boolean array **at no less than `min_long_side` across**, with the small burrs removed.

    **The reference's own line is one connected run of hundreds of pixels; a JPEG leaves thousands of three and four
    pixel specks beside it**, and a skeleton of specks is a thousand tiny segments -- which is what the first trace
    produced: 4967 skeleton pixels cut into 1291 pieces, average length 3.8. Those are not lines and they cost most of
    the render.
    """
    from PIL import Image
    from scipy import ndimage
    im = Image.open(path).convert('L')
    w, h = im.size
    long_side = max(w, h)
    if long_side < min_long_side:
        s = float(min_long_side) / long_side
        im = im.resize((int(round(w * s)), int(round(h * s))), Image.LANCZOS)
    a = np.asarray(im, dtype=np.uint8)
    ink_mask = (a < ink).astype(np.uint8)
    # **A closing, before the thinning, because the specks are attached rather than loose.** Removing small blobs left
    # the segment count where it was -- 1291 to 1258 -- so the noise is not an island, it is a burr on the line's own
    # edge: JPEG ringing leaves a ragged boundary, and every ragged tooth becomes a junction the moment the shape is
    # thinned. Filling the teeth first is cheaper than pruning them afterwards.
    ink_mask = ndimage.binary_closing(ink_mask, structure=np.ones((3, 3), dtype=bool)).astype(np.uint8)
    labels, count = ndimage.label(ink_mask, structure=np.ones((3, 3), dtype=np.uint8))
    if count:
        sizes = ndimage.sum(ink_mask, labels, range(1, count + 1))
        small = {i + 1 for i, s in enumerate(sizes) if s < min_component}
        if small:
            ink_mask = np.where(np.isin(labels, list(small)), 0, ink_mask).astype(np.uint8)
    return ink_mask, a.shape[1], a.shape[0]


def thin(binary):
    """Zhang-Suen, vectorised. **A line one pixel wide whatever the pen was**, which is what makes one segment a line."""
    b = binary.copy()
    rows, cols = b.shape
    shifts = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    for _ in range(200):
        changed = False
        for step in (0, 1):
            pad = np.pad(b, 1)
            nb = [pad[1 + dy:1 + dy + rows, 1 + dx:1 + dx + cols] for dy, dx in shifts]
            count = sum(nb)
            turns = ((nb[0] == 0) & (nb[1] == 1)).astype(np.uint8)
            for i in range(1, 8):
                turns = turns + ((nb[i] == 0) & (nb[(i + 1) % 8] == 1)).astype(np.uint8)
            cand = (b == 1) & (count >= 2) & (count <= 6) & (turns == 1)
            if step == 0:
                cand &= ((nb[0] * nb[2] * nb[4]) == 0) & ((nb[2] * nb[4] * nb[6]) == 0)
            else:
                cand &= ((nb[0] * nb[2] * nb[6]) == 0) & ((nb[0] * nb[4] * nb[6]) == 0)
            if cand.any():
                b[cand] = 0
                changed = True
        if not changed:
            break
    return b


def neighbours(skel, y, x, h, w):
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and skel[ny, nx]:
                out.append((ny, nx))
    return out


def trace(skel):
    """Every run between end points, **walking on through the junctions**.

    **A junction is where two lines cross, not where a line stops.** The first trace treated every junction as a wall,
    so a long line passing through four crossings became five short segments -- and each segment is a stroke with its
    own entry and exit taper, which on a twenty pixel segment means the whole thing is taper. That is why the result
    read as a dotted line: the gaps were not missing ink, they were the two ends of every fragment thinning away.

    So at a junction the walk takes the neighbour that continues the current direction most nearly straight, which is
    what a hand does and what the line means. Every edge is used once, so nothing is drawn twice and nothing is skipped.
    """
    h, w = skel.shape
    ys, xs = np.nonzero(skel)
    points = set(zip(ys.tolist(), xs.tolist()))

    def nbrs(p):
        y, x = p
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                q = (y + dy, x + dx)
                if q in points:
                    out.append(q)
        return out

    ends = [p for p in points if len(nbrs(p)) == 1]
    used = set()

    def take(a, b):
        used.add((a, b))
        used.add((b, a))

    def walk(start, first):
        path = [start, first]
        take(start, first)
        prev, cur = start, first
        while True:
            cand = [q for q in nbrs(cur) if q != prev and (cur, q) not in used]
            if not cand:
                break
            if len(cand) == 1:
                nxt = cand[0]
            else:
                # **Straightest first, because that is the line's own continuation.** The dot product of the step we
                # arrived on with each candidate step is the cheapest way to say "which of these looks like more of
                # the same line".
                ay, ax = cur[0] - prev[0], cur[1] - prev[1]
                nxt = max(cand, key=lambda q: ay * (q[0] - cur[0]) + ax * (q[1] - cur[1]))
            take(cur, nxt)
            path.append(nxt)
            prev, cur = cur, nxt
            if cur == start:
                break
        return path

    segments = []
    for start in ends:
        for first in nbrs(start):
            if (start, first) in used:
                continue
            segments.append(walk(start, first))
    # **What is left is a closed loop with no end point**, so it has to be started from any of its own pixels.
    for p in sorted(points):
        for first in nbrs(p):
            if (p, first) in used:
                continue
            segments.append(walk(p, first))
    return segments


def prune(skel, min_len):
    """Cut the short branches off a skeleton: a run that leaves a junction and dies within `min_len` pixels.

    **This is what turns twenty-four thousand segments into hundreds.** A hand-drawn line on a JPEG has a ragged edge,
    and thinning turns every ragged tooth into a junction with a two or three pixel spur; each spur is its own segment,
    and each segment is its own stroke to render. **The spurs are not lines** -- they are shorter than any mark a hand
    makes -- so they go, and what is left is the line the artist drew.
    """
    from scipy import ndimage
    b = skel.copy()
    rows, cols = b.shape
    for _ in range(4):
        count = ndimage.convolve(b, np.ones((3, 3), dtype=np.uint8), mode='constant') - b
        ends = np.argwhere((b == 1) & (count == 1))
        removed = 0
        for y, x in ends.tolist():
            path = [(y, x)]
            prev = None
            cur = (y, x)
            while len(path) <= min_len:
                nbs = [n for n in neighbours(b, cur[0], cur[1], rows, cols) if n != prev]
                if len(nbs) != 1:
                    break
                prev, cur = cur, nbs[0]
                path.append(cur)
            # **The last point is left alone**: it is the junction the spur hangs from, and removing it would open a
            # hole in the line the spur was hanging on.
            if len(path) <= min_len:
                for p in path[:-1]:
                    b[p[0], p[1]] = 0
                removed += 1
        if not removed:
            break
    return b


def ink_weight(ink_mask):
    """Half the line's width at every ink pixel: **its distance to the nearest paper.**

    **This is the only place the reference's own line weight can come from.** The ink mask says where the line is; the
    distance transform says how far it reaches, and twice that is the width the artist's pen was set to at that point.
    A line drawn heavier on one side than the other therefore carries the difference, and the trace can reproduce it
    without anyone deciding what the weight should be.
    """
    from scipy import ndimage
    return ndimage.distance_transform_edt(ink_mask)


def resample(values, n):
    """`values` stretched onto `n` samples, linearly, for a width profile that matches the stroke's own sampling."""
    m = len(values)
    if m == 1 or n < 2:
        return [values[0]] * n
    out = []
    for i in range(n):
        t = i / float(n - 1) * (m - 1)
        lo = int(t)
        hi = min(lo + 1, m - 1)
        out.append(values[lo] + (values[hi] - values[lo]) * (t - lo))
    return out


#: Half-width, in work pixels, above which a mark is a filled patch rather than a line. **A pen is one to four pixels
#: across at the reading size; a pupil, a hatched sleeve or a solid shadow grows past ten.** Measured over six
#: references, the four clean line drawings hold 0.3 to 1.6 per cent of their ink above this and one dynamic drawing
#: holds 20 -- **which is what a heavy pen had been hiding.**
FILL_HALF = 6.0

#: A patch smaller than this many work pixels is a spot on the paper, not a shape.
MIN_FILL = 400


def region_of(points):
    """A `Region` from a closed polygon -- points and a path, which is all a fill mark needs."""
    d = 'M ' + ' L '.join('%.2f %.2f' % (x, y) for x, y in points) + ' Z'
    return core.Region(points=[tuple(p) for p in points], d=d)


def form_lines(blob, spacing, max_layers=64):
    """Closed lines inside a patch, each parallel to the one outside it.

    **This is what "follow the form" means as a procedure.** A patch is eroded a few pixels at a time and the boundary
    of each step is kept, so every line is the same distance inside its neighbour and **the direction of the hatching is
    whatever the shape's edge says it is**. A horizontal sweep is easy to generate and tells the eye nothing; these are
    the lines a hand draws when it shades a shape inward from its contour.
    """
    from scipy import ndimage
    import trace as silhouette
    rings = []
    cur = blob.astype(bool)
    structure = np.ones((3, 3), dtype=bool)
    for _ in range(max_layers):
        if not cur.any():
            break
        ys, xs = np.nonzero(cur)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        local = cur[y0:y1, x0:x1].astype(np.uint8)
        ring = silhouette.boundary(local, x1 - x0, y1 - y0)
        if len(ring) >= 6:
            rings.append([(x + x0, y + y0) for x, y in ring])
        cur = ndimage.binary_erosion(cur, structure=structure, iterations=max(1, spacing))
        if int(cur.sum()) < spacing * spacing:
            break
    return rings


def fill_shapes(binary, weight, threshold, min_area, spacing=3, style='form'):
    """The filled patches, as **an outline and the lines inside it**.

    **A patch in this kind of drawing is hatched, not poured.** The ink of a shadow or a solid area is a density of
    curves, and pouring a flat colour over the shape throws away the one thing the reference has to teach. So a patch
    yields two things: its boundary, which is a line like any other, and the lines that fill its inside -- **shape first,
    then lines, which is also the order a person works in.**

    `style='form'` draws each inner line parallel to the contour, which is what shading a shape from its edge looks
    like; `style='lines'` sweeps the patch horizontally, which is cheaper and tells the eye less.
    """
    from scipy import ndimage
    mask = ((binary > 0) & (weight > threshold)).astype(np.uint8)
    mask = ndimage.binary_closing(mask, structure=np.ones((3, 3), dtype=bool)).astype(np.uint8)
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    import trace as silhouette
    outlines = []
    inner = []
    for i in range(1, count + 1):
        blob = (labels == i)
        if int(blob.sum()) < min_area:
            continue
        ys, xs = np.nonzero(blob)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        local = blob[y0:y1, x0:x1].astype(np.uint8)
        ring = silhouette.boundary(local, x1 - x0, y1 - y0)
        if len(ring) >= 8:
            outlines.append([(x + x0, y + y0) for x, y in ring])
        if style == 'form':
            inner.extend(form_lines(blob, spacing)[1:])
        else:
            for y in range(y0, y1, max(1, spacing)):
                row = np.nonzero(blob[y])[0]
                if not len(row):
                    continue
                start = prev = int(row[0])
                for x in row[1:]:
                    x = int(x)
                    if x != prev + 1:
                        if prev > start:
                            inner.append([(start, y), (prev, y)])
                        start = x
                    prev = x
                if prev > start:
                    inner.append([(start, y), (prev, y)])
    return outlines, inner, int(mask.sum())


def simplify(points, tolerance):
    """Douglas-Peucker, the same one the silhouette tracer uses -- a run of pixels is a path with a staircase in it."""
    import trace as silhouette
    if len(points) < 3:
        return points
    return silhouette.douglas_peucker(points, tolerance)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', default=r'E:\DaShaoHuo\cache\copy.json')
    ap.add_argument('--png', default=r'E:\DaShaoHuo\cache\copy.png')
    ap.add_argument('--min-long-side', type=int, default=MIN_LONG_SIDE)
    ap.add_argument('--canvas-side', type=int, default=CANVAS_SIDE)
    ap.add_argument('--ink', type=int, default=INK)
    ap.add_argument('--min-segment', type=int, default=MIN_SEGMENT)
    ap.add_argument('--prune', type=int, default=8, help='drop skeleton spurs shorter than this many pixels')
    ap.add_argument('--max-width', type=float, default=6.0, help='widest a stroke may be drawn, in page pixels')
    ap.add_argument('--width-scale', type=float, default=1.0,
                    help='multiplies every width; calibrated against the reference\'s own amount of ink')
    ap.add_argument('--fill-half', type=float, default=FILL_HALF,
                    help='half-width above which a mark is a filled patch rather than a line')
    ap.add_argument('--min-fill', type=int, default=MIN_FILL)
    ap.add_argument('--hatch-spacing', type=int, default=3,
                    help='work pixels between the lines inside a filled patch; smaller is darker')
    ap.add_argument('--hatch-style', default='form', choices=('form', 'lines'),
                    help='form follows the contour inward; lines sweeps horizontally')
    ap.add_argument('--min-component', type=int, default=30, help='ink blobs smaller than this are specks')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    t0 = time.perf_counter()
    binary, w, h = load_ink(args.src, args.min_long_side, args.ink, args.min_component)
    t_load = time.perf_counter()
    print('  %s  %dx%d  ink pixels %d (%.2f%%)  load %.1fs'
          % (pathlib.Path(args.src).name, w, h, int(binary.sum()), 100.0 * binary.sum() / (w * h), t_load - t0))
    weight = ink_weight(binary)
    t_weight = time.perf_counter()
    print('  line half-width on the ink: %.2f .. %.2f px   distance %.1fs'
          % (float(weight[binary > 0].min()), float(weight[binary > 0].max()), t_weight - t_load))

    # **The ink is cut in two before anything is drawn.** What is thin is a line and is traced; what is thick is a
    # filled shape and is outlined. Tracing a patch turns it into a heavy line through its middle, which is the one
    # thing the reference never did.
    rings, hatch_lines, patch_px = fill_shapes(binary, weight, args.fill_half, args.min_fill,
                                               args.hatch_spacing, args.hatch_style)
    line_ink = ((binary > 0) & (weight <= args.fill_half)).astype(np.uint8)
    print('  filled patches: %d outlines, %d hatch lines, %d px (%.2f%% of the ink); lines keep %d px'
          % (len(rings), len(hatch_lines), patch_px,
             100.0 * patch_px / max(1, int(binary.sum())), int(line_ink.sum())))
    t_split = time.perf_counter()
    skel = thin(line_ink)
    t_lines = time.perf_counter()
    print('  line skeleton %d px   thin %.1fs' % (int(skel.sum()), t_lines - t_split))
    skel = prune(skel, args.prune)
    t_prune = time.perf_counter()
    print('  after pruning spurs shorter than %d: %d pixels   prune %.1fs'
          % (args.prune, int(skel.sum()), t_prune - t_lines))

    segments = trace(skel)
    t_trace = time.perf_counter()
    print('  segments %d   trace %.1fs' % (len(segments), t_trace - t_prune))
    kept = []
    for seg in segments:
        if len(seg) < args.min_segment:
            continue
        pts = [(float(x), float(y)) for y, x in seg]
        kept.append(simplify(pts, 0.9))
    t_simplify = time.perf_counter()
    print('  kept %d, points %d   simplify %.1fs' % (len(kept), sum(len(s) for s in kept), t_simplify - t_trace))

    # **The page is at least 2880 across and at least 1.2 times the reference.** Three rules meet here: a drawing from
    # this tool never has a long side below 2880; it is never smaller than the picture it copies, and not by a hair
    # either -- a tenth more would be a copy at the same size, and the point of a larger page is that shrinking it back
    # for comparison costs nothing; and `--canvas-side` can ask for more, up to the absurd (a ten thousand pixel page is
    # allowed and will simply take a while). A reference of ten thousand square would therefore be traced at twelve
    # thousand, and one of eight hundred by twelve hundred is traced at 2880.
    from PIL import Image as _Image
    ref_long = float(max(_Image.open(args.src).size))
    canvas_long = max(2880.0, ref_long * 1.2, float(args.canvas_side or 0))
    s = canvas_long / float(max(w, h))
    canvas_w = max(1, int(round(w * s)))
    canvas_h = max(1, int(round(h * s)))
    proj = project.Project(width=canvas_w, height=canvas_h, title='copy of %s' % pathlib.Path(args.src).stem)
    marks = 0
    # **The patch's outline first, then the lines inside it**, which is the order the reference was drawn in and the
    # order a hand works in: the shape is stated, then the ink goes in as lines rather than as a pour.
    for i, pts in enumerate(rings):
        scaled = [(x * s, y * s) for x, y in pts]
        if len(scaled) < 3:
            continue
        outline = core.stroke_record(scaled, 'fine', seed=100 + i, resolution=6,
                                     width_profile=[1.6] * (6 * (len(scaled) - 1) + 1))
        proj.add_stroke(outline, stage='line', layer='ink', note='patch outline %d' % i)
        marks += 1
    for i, pts in enumerate(hatch_lines):
        scaled = [(x * s, y * s) for x, y in pts]
        if len(scaled) < 2:
            continue
        samples = 4 * (len(scaled) - 1) + 1
        rec = core.stroke_record(scaled, 'fine', seed=200 + i, resolution=4,
                                 width_profile=[1.2] * samples)
        proj.add_stroke(rec, stage='line', layer='hatch', note='inner line %d' % i)
        marks += 1
    for i, pts in enumerate(kept):
        if len(pts) < 2:
            continue
        scaled = [(x * s, y * s) for x, y in pts]
        # **The width comes from the ink, not from a constant.** Twice the distance transform at each point is the
        # diameter the pen had there, scaled from the reading size to the page. The floor of one page pixel keeps a
        # hairline visible; below that a line is not drawn, it is suggested.
        widths = []
        for x, y in pts:
            half = weight[int(round(y)), int(round(x))]
            # **Clamped, because the widest distance in a drawing is a filled area rather than a line.** The measured
            # half-widths on this reference run from 1 to 42 pixels: the 42 is a solid patch of ink, and drawn at its
            # own weight it becomes a black slab where the artist drew a sleeve. A line is what this is copying, so the
            # width stops where a line ends.
            # **A floor of half a pixel, not one.** The floor exists so a faint line still marks the page; at one pixel
            # it also stops the width calibration dead, because every hairline hits the same number and the ink stops
            # responding to the setting.
            widths.append(min(args.max_width, max(0.5, 2.0 * float(half) * s * args.width_scale)))
        samples = 6 * (len(scaled) - 1) + 1
        rec = core.stroke_record(scaled, 'fine', seed=i, resolution=6,
                                 width_profile=resample(widths, samples))
        proj.add_stroke(rec, stage='line', layer='ink', note='traced %d' % i)
        marks += 1
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out))
    print('  %d strokes written to %s' % (marks, out))
    if args.render:
        import subprocess
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', args.png],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % args.png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
