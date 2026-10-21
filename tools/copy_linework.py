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

import numpy as np

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, project

#: Working size for the long side, or 0 to keep the reference's own. **Downscaling was the first attempt and it lost
#: the drawing**: the lines are about one pixel wide at 800 across, and resampling them to 320 spread each one over
#: two and a half pixels of white, which took the ink count from 7614 to 15. A thin line does not survive being averaged.
MAX_SIDE = 0

#: How far from white a pixel has to be to count as ink, out of 255. **A pencil line is grey, not black**: at 110 this
#: reference kept 5036 pixels and at 180 it keeps 7614, and the difference is the line's soft edge rather than noise.
INK = 180

#: Segments shorter than this many pixels are dropped. **They are what a skeleton leaves at every junction** -- two or
#: three pixels of a stub -- and drawn they read as dirt on the page.
MIN_SEGMENT = 6


def load_ink(path, max_side, ink, min_component=30):
    """Ink as a boolean array, **with the small islands removed**.

    **The reference's own line is one connected run of hundreds of pixels; a JPEG leaves thousands of three and four
    pixel specks beside it**, and a skeleton of specks is a thousand tiny segments -- which is what the first trace
    produced: 4967 skeleton pixels cut into 1291 pieces, average length 3.8. Those are not lines and they cost most of
    the render.
    """
    from PIL import Image
    from scipy import ndimage
    im = Image.open(path).convert('L')
    w, h = im.size
    if max_side:
        s = min(1.0, float(max_side) / max(w, h))
        if s < 1.0:
            im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
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
    """Every run between an end point or a junction, as a list of (x, y) in page order."""
    h, w = skel.shape
    ends, junctions = set(), set()
    # **Only the skeleton's own pixels are visited.** Walking every pixel of a page to find a few thousand set ones
    # cost most of a 46 second trace; `nonzero` hands the list over instead.
    ys, xs = np.nonzero(skel)
    for y, x in zip(ys.tolist(), xs.tolist()):
        n = len(neighbours(skel, y, x, h, w))
        if n == 1:
            ends.add((y, x))
        elif n > 2:
            junctions.add((y, x))

    stops = ends | junctions
    visited = set()
    segments = []

    def walk(start, first):
        path = [start, first]
        visited.add((start, first))
        visited.add((first, start))
        cur, prev = first, start
        while True:
            if cur in stops:
                break
            nxt = [n for n in neighbours(skel, cur[0], cur[1], h, w) if n != prev]
            if len(nxt) != 1:
                break
            n2 = nxt[0]
            visited.add((cur, n2))
            visited.add((n2, cur))
            path.append(n2)
            prev, cur = cur, n2
        return path

    for node in sorted(ends):
        for first in neighbours(skel, node[0], node[1], h, w):
            if (node, first) in visited:
                continue
            segments.append(walk(node, first))
    # **What is left is a closed loop with no end and no junction** -- a circle, or a shape whose outline never forks.
    ys, xs = np.nonzero(skel)
    for y, x in zip(ys.tolist(), xs.tolist()):
        for first in neighbours(skel, y, x, h, w):
            if ((y, x), first) in visited:
                continue
            segments.append(walk((y, x), first))
    return segments


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
    ap.add_argument('--max-side', type=int, default=MAX_SIDE)
    ap.add_argument('--ink', type=int, default=INK)
    ap.add_argument('--min-segment', type=int, default=MIN_SEGMENT)
    ap.add_argument('--min-component', type=int, default=30, help='ink blobs smaller than this are specks')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    binary, w, h = load_ink(args.src, args.max_side, args.ink, args.min_component)
    print('  %s  %dx%d  ink pixels %d (%.2f%%)' % (pathlib.Path(args.src).name, w, h, int(binary.sum()),
                                                    100.0 * binary.sum() / (w * h)))
    skel = thin(binary)
    print('  skeleton pixels %d' % int(skel.sum()))

    segments = trace(skel)
    kept = []
    for seg in segments:
        if len(seg) < args.min_segment:
            continue
        pts = [(float(x), float(y)) for y, x in seg]
        kept.append(simplify(pts, 0.9))
    print('  segments %d, kept %d, points %d' % (len(segments), len(kept), sum(len(s) for s in kept)))

    proj = project.Project(width=w, height=h, title='copy of %s' % pathlib.Path(args.src).stem)
    marks = 0
    for i, pts in enumerate(kept):
        if len(pts) < 2:
            continue
        # **One width for now.** The reference has a taper and this does not read it yet; what is being checked here is
        # whether the paths are where the artist put them.
        rec = core.stroke_record(pts, 'fine', seed=i, resolution=6,
                                 width_profile=[2.2] * (6 * (len(pts) - 1) + 1))
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
