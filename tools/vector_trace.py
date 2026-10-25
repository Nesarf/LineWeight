"""Outline the ink itself: the reference's dark pixels become polygons, not centre lines.

**Why this exists next to the line tracer.** A centre line plus a width is how a drawn line is described, and it
reproduces the *path* of a stroke but not its *pixels*: the skeleton sits half a pixel off centre, the simplification
moves it again, and when it is drawn back the boundary lands one or two pixels away. Measured against the one per cent
standard that shows up as 79 per cent of the ink in the wrong place -- the amount of ink was already right at 98 per
cent, the positions were not.

**Outlining the ink has no such freedom.** The polygon *is* the shape the ink has, so the only error left is the
rasteriser's own: the same shape filled again. That is a different kind of drawing -- the result is a filled region and
not a stroke -- and it is the only route to a difference of one per cent.

    python tools/vector_trace.py --src "...png" --out out.json --png out.png --render
"""
import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from lineweight import core, project

import copy_linework as cl
import trace as silhouette

#: Douglas-Peucker tolerance for the outline, in work pixels. **Tighter than the line tracer's**, because here the
#: polygon is the shape itself: a tolerance of one pixel is a pixel of shape thrown away.
TOLERANCE = 0.6

#: Blobs smaller than this many pixels are specks. The tracer's own number, for the same reason.
MIN_AREA = 20


def outlines(mask, tolerance, min_area, gray=None, inset=0.5):
    """Every blob as **an outside and its insides**: the boundary plus the holes it encloses.

    **The holes are the difference between a silhouette and a shape.** A dark garment with pale patterning is one
    outside and many insides; filled as a single polygon it becomes a black slab carrying far more ink than the
    reference had. The insides are the regions of paper the blob surrounds -- found by labelling the background *inside
    the blob's own box* and keeping the pieces that touch no side of it, since a piece that touches a side is the
    outside rather than a hole.

    Each ring is moved `inset` pixels along the greyscale's gradient, which points across the edge at sub-pixel
    accuracy; the walk itself travels along pixel edges and so leaves every boundary half a pixel out.
    """
    from scipy import ndimage
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    normal = None
    if gray is not None and inset:
        gy, gx = np.gradient(gray.astype(np.float32))
        mag = np.hypot(gx, gy) + 1e-6
        normal = (gx / mag, gy / mag)

    def nudged(ring, x0, y0):
        pts = []
        for x, y in ring:
            fx, fy = float(x + x0), float(y + y0)
            if normal is not None:
                iy = int(min(gray.shape[0] - 1, max(0, round(fy))))
                ix = int(min(gray.shape[1] - 1, max(0, round(fx))))
                fx -= inset * float(normal[0][iy, ix])
                fy -= inset * float(normal[1][iy, ix])
            pts.append((fx, fy))
        return silhouette.douglas_peucker(pts, tolerance)

    shapes = []
    for i in range(1, count + 1):
        blob = (labels == i)
        if int(blob.sum()) < min_area:
            continue
        ys, xs = np.nonzero(blob)
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        local = blob[y0:y1, x0:x1].astype(np.uint8)
        ring = silhouette.boundary(local, x1 - x0, y1 - y0)
        if len(ring) < 4:
            continue
        outer = nudged(ring, x0, y0)
        holes = []
        inner = (1 - local).astype(np.uint8)
        inner_labels, inner_count = ndimage.label(inner, structure=np.ones((3, 3), dtype=np.uint8))
        for k in range(1, inner_count + 1):
            piece = (inner_labels == k)
            if int(piece.sum()) < 30:
                continue
            py, px = np.nonzero(piece)
            # **A piece touching the box's edge is the outside, not a hole.**
            if py.min() == 0 or px.min() == 0 or py.max() == local.shape[0] - 1 or px.max() == local.shape[1] - 1:
                continue
            hole_ring = silhouette.boundary(piece.astype(np.uint8), local.shape[1], local.shape[0])
            if len(hole_ring) < 4:
                continue
            holes.append(nudged(hole_ring, x0, y0))
        shapes.append((outer, holes))
    return shapes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--png', default='')
    ap.add_argument('--min-long-side', type=int, default=2880)
    ap.add_argument('--canvas-side', type=float, default=0)
    ap.add_argument('--ink', type=int, default=cl.INK)
    ap.add_argument('--tolerance', type=float, default=TOLERANCE)
    ap.add_argument('--inset', type=float, default=0.5,
                    help='pixels each outline is pulled inward along the greyscale gradient; 0 turns it off')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

    # **The ink read plainly, with no closing and no cleanup.** The line tracer closes the ink because a skeleton
    # needs a connected net, and that closing widens every mark; here the mask *is* the shape, so a widened mask is a
    # widened shape -- the first run drew 448 per cent of the reference's ink and the surplus was exactly the ring the
    # closing added.
    from PIL import Image
    img = Image.open(args.src).convert('L')
    ref_size = img.size
    ref_long = float(max(ref_size))
    canvas_long = max(2880.0, ref_long * 1.2, args.canvas_side)
    work_long = max(float(args.min_long_side), ref_long)
    scale = work_long / ref_long
    work = (int(round(ref_size[0] * scale)), int(round(ref_size[1] * scale)))
    if work != ref_size:
        img = img.resize(work, Image.LANCZOS)
    arr = np.asarray(img, dtype=np.uint8)
    binary = (arr < args.ink).astype(np.uint8)
    w, h = work
    s = canvas_long / float(max(w, h))
    print('  %s  work %dx%d, page %dx%d, ink %d px'
          % (pathlib.Path(args.src).name, w, h, round(w * s), round(h * s), int(binary.sum())))

    shapes = outlines(binary, args.tolerance / s, MIN_AREA, gray=arr, inset=args.inset * s)
    print('  %d shapes, %d points, %d holes'
          % (len(shapes), sum(len(o) for o, _h in shapes), sum(len(h) for _o, h in shapes)))

    proj = project.Project(width=int(round(w * s)), height=int(round(h * s)),
                           title='vector trace of %s' % pathlib.Path(args.src).stem)
    for i, (ring, holes) in enumerate(shapes):
        pts = [(x * s, y * s) for x, y in ring]
        if len(pts) < 3:
            continue
        d = 'M ' + ' L '.join('%.2f %.2f' % p for p in pts) + ' Z'
        hole_pts = [[tuple(p) for p in ((x * s, y * s) for x, y in h)] for h in holes if len(h) >= 3]
        proj.add_fill(core.Region(points=[tuple(p) for p in pts], d=d, holes=hole_pts),
                      stage='colour', colour='#141018', note='ink outline %d' % i)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    project.save_project(proj, str(out))
    print('  written to %s' % out)
    if args.render:
        import subprocess
        png = args.png or str(out.with_suffix('.png'))
        subprocess.run([sys.executable, '-m', 'lineweight', '--render', str(out), '--out', png],
                       capture_output=True, text=True, cwd=r'E:\lineweight')
        print('  rendered to %s' % png)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
