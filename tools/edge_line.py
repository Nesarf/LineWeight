"""Where a painted picture changes quickly, which is where its structure is: a line drawing derived from tone.

**Why this is a different problem from tracing.** A line drawing states its structure directly -- the lines *are* the
structure. A painted picture states it in the rate of change of tone: an arm is a place where the brightness turns
sharply, and the inside of the arm is not. So the structure is a property of the gradient, and the tool that finds it is
the edge detector, with the two things that make an edge detector useful here rather than noisy everywhere:

- **non-maximum suppression**, so a ramp becomes one pixel of edge instead of a band; and
- **hysteresis**, so an edge is kept only if it is either strong or attached to something strong. A painted reference
  has a gradient almost everywhere; what separates a contour from a cheek's blush is the strength of the change, not
  the fact of it.

The result is a one-pixel structure line which is then walked into polylines and drawn, exactly as a traced skeleton is.

    python tools/edge_line.py --src "...jpg" --out out.json --png out.png --render
"""
import argparse
import pathlib
import sys

import numpy as np

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from lineweight import core, project

import trace as silhouette

#: Blur before differentiating. **A painted reference has noise at the scale of one pixel** -- texture, brushwork, the
#: JPEG's own blocks -- and differentiating that noise gives edges everywhere. The blur is the scale below which a
#: difference stops being structural.
BLUR = 2.0

#: Percentiles of the surviving gradient magnitude that divide strong from weak. **Chosen as quantiles of this
#: picture's own distribution**, so a darker or a flatter reference does not need its numbers changed.
STRONG_PCT = 88.0
WEAK_PCT = 96.0

#: Shortest polyline kept, in work pixels. Shorter runs are the stubble of a noisy gradient.
MIN_SEGMENT = 10


def structure(gray, blur, strong_pct, weak_pct, pair_distance=4):
    """A one-pixel structure mask: Canny, on the reference's own gradient distribution.

    **Two sides of one band become one line.** A painted highlight is a pale band between two dark ones, so the gradient
    peaks on each of its sides and non-maximum suppression keeps both -- which is right for the gradient and wrong for a
    drawing, where a highlight is one line and not two. Where a structure pixel finds another within `pair_distance`
    across its own gradient, the weaker of the two goes. That is the light rule from the library finally doing work: of
    a band's two edges, the one that survives is the one whose change is greater, and a line is thickened on the side the
    light does not reach.
    """
    from scipy import ndimage
    g = ndimage.gaussian_filter(gray.astype(np.float32), blur)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)
    angle = (np.rad2deg(np.arctan2(gy, gx)) + 180.0) % 180.0
    octant = ((angle + 22.5) // 45.0).astype(np.int32) % 4

    left = np.roll(mag, 1, axis=1)
    right = np.roll(mag, -1, axis=1)
    up = np.roll(mag, 1, axis=0)
    down = np.roll(mag, -1, axis=0)
    ul = np.roll(up, 1, axis=1)
    dr = np.roll(down, -1, axis=1)
    ur = np.roll(up, -1, axis=1)
    dl = np.roll(down, 1, axis=1)
    pairs = ((left, right), (ul, dr), (up, down), (ur, dl))

    keeps = np.zeros_like(mag, dtype=bool)
    for k, (a, b) in enumerate(pairs):
        # **Only where the gradient points this way, and only if it is a local maximum along it.** That is what turns a
        # ramp into a line; without it every edge is a band and the "line width" is the ramp's width.
        keeps |= (octant == k) & (mag >= a) & (mag >= b)
    thinned = np.where(keeps, mag, 0.0)

    positive = thinned[thinned > 0]
    if not positive.size:
        return np.zeros_like(mag, dtype=bool)
    hi = float(np.percentile(positive, 100.0 - strong_pct))
    lo = float(np.percentile(positive, 100.0 - weak_pct))
    strong = thinned >= hi
    weak = thinned >= lo
    labels, count = ndimage.label(weak, structure=np.ones((3, 3), dtype=np.uint8))
    if not count:
        return strong
    # **An edge is kept if any part of its connected run is strong.** This is the hysteresis: it lets a contour continue
    # through the soft places instead of stopping wherever the paint got light.
    attached = np.zeros(count + 1, dtype=bool)
    attached[np.unique(labels[strong])] = True
    attached[0] = False
    kept = attached[labels]

    if pair_distance > 0:
        h, w = g.shape
        ys, xs = np.mgrid[0:h, 0:w]
        ux = gx / (mag + 1e-6)
        uy = gy / (mag + 1e-6)
        drop = np.zeros_like(kept)
        for sign in (1, -1):
            sx = np.clip((xs + sign * pair_distance * ux).round().astype(np.int32), 0, w - 1)
            sy = np.clip((ys + sign * pair_distance * uy).round().astype(np.int32), 0, h - 1)
            # **A partner across the gradient that is stronger, and the two are near enough to be one band's two sides.**
            # Distance is measured against the gradient, so "across" means across the edge, not along it.
            partner = kept[sy, sx] & (mag[sy, sx] > mag)
            drop |= partner & kept
        kept &= ~drop
    return kept


def walks(mask, min_segment):
    """The mask's structure lines, walked the way a skeleton is walked."""
    import copy_linework as cl
    skel = cl.thin(mask.astype(np.uint8))
    segments = cl.trace(skel)
    out = []
    for seg in segments:
        if len(seg) < min_segment:
            continue
        pts = [(float(x), float(y)) for y, x in seg]
        out.append(silhouette.douglas_peucker(pts, 0.8))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--png', default='')
    ap.add_argument('--min-long-side', type=int, default=2880)
    ap.add_argument('--canvas-side', type=float, default=0)
    ap.add_argument('--blur', type=float, default=BLUR)
    ap.add_argument('--strong', type=float, default=STRONG_PCT)
    ap.add_argument('--weak', type=float, default=WEAK_PCT)
    ap.add_argument('--min-segment', type=int, default=MIN_SEGMENT)
    ap.add_argument('--pair-distance', type=float, default=4.0,
                    help='how far across the gradient to look for the other side of one band; 0 keeps both')
    ap.add_argument('--width', type=float, default=2.4, help='pen width on the page')
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()

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
    gray = np.asarray(img, dtype=np.float32)
    w, h = work
    s = canvas_long / float(max(w, h))
    print('  %s  work %dx%d, page %dx%d'
          % (pathlib.Path(args.src).name, w, h, round(w * s), round(h * s)))

    mask = structure(gray, args.blur, args.strong, args.weak, args.pair_distance)
    print('  structure pixels %d (%.2f%% of the page)' % (int(mask.sum()), 100.0 * mask.sum() / (w * h)))
    lines = walks(mask, args.min_segment)
    print('  %d structure lines, %d points'
          % (len(lines), sum(len(l) for l in lines)))

    proj = project.Project(width=int(round(w * s)), height=int(round(h * s)),
                           title='structure of %s' % pathlib.Path(args.src).stem)
    for i, pts in enumerate(lines):
        if len(pts) < 2:
            continue
        scaled = [(x * s, y * s) for x, y in pts]
        rec = core.stroke_record(scaled, 'fine', seed=i, resolution=4,
                                 width_profile=[args.width] * (4 * (len(scaled) - 1) + 1))
        proj.add_stroke(rec, stage='line', layer='ink', note='structure %d' % i)
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
