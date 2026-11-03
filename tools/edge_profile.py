"""How many pixels a line's edge takes to cross from the field to the ink.

**The question this answers, and why `edge_scale` was not enough.** `edge_scale` says whether a dark structure keeps its
depth under a coarser element -- a good discriminator between a line and a gradient, and the wrong shape of answer for
"how soft is the edge". This walks across the line instead: from a skeleton point, along the normal, sample the grey and
read how far it takes to fall from 10 to 90 per cent of the way from the field into the ink. That is a length in pixels.

Measured on eleven artist drawings, the crossing is **2.70 to 4.43 pixels at the median**, and a line rasterised with one
pixel of anti-aliasing crosses in 1.75 to 2.00. So the number a drawn line needs is not zero: it is a material setting,
and `stroke_record(..., edge=...)` is where it lives.

    python tools/edge_profile.py --picture ref.jpg --picture cache/paint21/lines.png
"""
import argparse
import sys

import numpy as np

import line_agreement as la
from copy_linework import thin, trace

#: How far either side of the centre line to sample. A line wider than this is not a line this measure is for.
REACH = 10.0
#: The step across the section. A quarter pixel is finer than any rasteriser's own transition and keeps the centroid
#: from being quantised by the sampling.
STEP = 0.1


def bilinear(field, xs, ys):
    """The picture sampled between pixels, so a section is a length rather than a count."""
    height, width = field.shape
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    fx = xs - x0
    fy = ys - y0
    x0 = np.clip(x0, 0, width - 1)
    y0 = np.clip(y0, 0, height - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    return (field[y0, x0] * (1 - fx) * (1 - fy) + field[y0, x1] * fx * (1 - fy)
            + field[y1, x0] * (1 - fx) * fy + field[y1, x1] * fx * fy)


def crossing_width(profile):
    """How far along the section the ink goes from 10 to 90 per cent, averaged over the two sides.

    **Both sides, because a nib is not symmetric and neither is a rasteriser's anti-aliasing.** A section that never
    reaches both levels is not a line -- it is a field with a smudge in it -- so it returns nothing rather than a
    number nobody should average.
    """
    low, high = float(profile.min()), float(profile.max())
    if high - low < 40.0:
        return None
    normalised = (high - profile) / (high - low)      # 0 in the field, 1 in the ink
    centre = len(profile) // 2
    widths = []
    for side in (normalised[:centre + 1][::-1], normalised[centre:]):
        inside = np.flatnonzero(side >= 0.9)
        outside = np.flatnonzero(side <= 0.1)
        if not inside.size or not outside.size:
            continue
        before = outside[outside < inside[0]]
        if not before.size:
            continue
        widths.append((inside[0] - before[-1]) * STEP)
    return float(np.mean(widths)) if widths else None


def measure(path, samples=400, reach=REACH, step=STEP):
    """The crossing widths sampled along a picture's own skeleton."""
    gray = la.load_gray(path, la.LONG_SIDE)
    mask = la.artist_line(gray)
    skeleton = thin(mask.astype(np.uint8))
    runs = [run for run in trace(skeleton) if len(run) >= 16]
    if not runs:
        return []
    rng = np.random.default_rng(7)
    offsets = np.arange(-reach, reach + step, step)
    widths = []
    for _ in range(samples):
        run = runs[int(rng.integers(0, len(runs)))]
        i = int(rng.integers(6, len(run) - 6))
        y, x = float(run[i][0]), float(run[i][1])
        ty, tx = float(run[i + 4][0] - run[i - 4][0]), float(run[i + 4][1] - run[i - 4][1])
        span = float(np.hypot(tx, ty))
        if span < 1e-6:
            continue
        nx, ny = -tx / span, ty / span
        width = crossing_width(bilinear(gray, x + nx * offsets, y + ny * offsets))
        if width is not None:
            widths.append(width)
    return widths


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--picture', required=True, action='append',
                    help='a picture to measure; repeat to compare several')
    ap.add_argument('--samples', type=int, default=400)
    ap.add_argument('--reach', type=float, default=REACH)
    args = ap.parse_args(argv)

    print('  %-34s %8s %9s %9s %9s' % ('picture', 'samples', 'edge px', 'p10', 'p90'))
    for path in args.picture:
        widths = measure(path, samples=args.samples, reach=args.reach)
        name = path.replace('\\', '/').rsplit('/', 1)[-1]
        if not widths:
            print('  %-34s %8s   no measurable edge' % (name, ''))
            continue
        values = np.array(widths)
        print('  %-34s %8d %9.2f %9.2f %9.2f'
              % (name, len(values), float(np.median(values)),
                 float(np.percentile(values, 10)), float(np.percentile(values, 90))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
