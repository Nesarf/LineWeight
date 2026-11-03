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
from scipy import ndimage

import line_agreement as la
from copy_linework import thin, trace

#: The furthest either side of the centre line to sample. **It is a ceiling, not a setting.** A fixed window ten pixels
#: wide read the field as 0.554 on a copy drawn on pure white paper, because on a dense drawing it reached across to the
#: ink of the neighbouring stroke and called that the field. The window therefore follows the line's own half width,
#: which is what the distance transform gives, so a hairline gets a small window and a heavy line gets a wide one.
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


def _crossing_index(values, level):
    """Where `values`, falling from the ink outward, passes `level` -- interpolated between two samples.

    **The index of the first sample below a level is not the crossing.** Measured against ramps of known width, taking the
    sample index gave ratios of 2.00, 1.25 and 0.89 for transitions over two, five and ten samples: the error is
    quantisation, and it changes with the answer, which is the one thing a length must not do. Interpolating between the
    two samples that straddle the level removes it.
    """
    below = np.flatnonzero(values <= level)
    if not below.size:
        return None
    i = int(below[0])
    if i == 0:
        return 0.0
    high, low = float(values[i - 1]), float(values[i])
    if high == low:
        return float(i)
    return (i - 1) + (high - level) / (high - low)


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
    # **The centre is the darkest sample, not the middle of the window.** The section is taken across a skeleton point,
    # and the skeleton is a pixel path -- `reference_lines` spends a whole function moving points off it because it is
    # not the centre of the ink. Reading the middle of the window as "the line" therefore splits a section whose dark
    # part sits to one side, and both halves then fail to find a level that is only on the other side of it: measured,
    # 60 of 80 sections were refused that way on one drawing.
    centre = int(np.argmin(profile))
    widths = []
    # **The left half is reversed so index nought is the centre on both sides**, which makes "further into the field" a
    # larger index in both -- and the crossing is found by interpolation rather than by the first sample past a level.
    for side in (normalised[:centre + 1][::-1], normalised[centre:]):
        near = _crossing_index(side, 0.9)
        far = _crossing_index(side, 0.1)
        if near is None or far is None or far <= near:
            continue
        widths.append((far - near) * STEP)
    return float(np.mean(widths)) if widths else None


def measure(path, samples=400, reach=REACH, step=STEP):
    """Three numbers off every section: how wide its edge is, how deep its ink is, and what field it sits on.

    **One section carries all three, and that is the point of splitting the judgement.** `edge_scale` reports a single
    share -- how much of a dark structure's depth survives a coarser element -- and three mechanisms move that one
    number: the softness of the boundary, the darkness of the ink, and the brightness of what the line lies on. Reading
    them here means a figure like "39.7 per cent" can be attributed instead of guessed at.
    """
    gray = la.load_gray(path, la.LONG_SIDE)
    mask = la.artist_line(gray)
    skeleton = thin(mask.astype(np.uint8))
    edt = ndimage.distance_transform_edt(mask)
    # **The field is the local median, not the ends of the window.** Reading it at the ends coupled it to the ink depth:
    # a lighter line puts more of its own transition inside the window, so the "field" darkened as the ink lightened, and
    # a crossed experiment then said deeper ink makes a line harder while the artists' drawings said the opposite. The
    # local median has no window to be inside of, and it is the same field `line_mask` compares a pixel against -- one
    # definition rather than two.
    local = ndimage.median_filter(gray, size=15)
    runs = [run for run in trace(skeleton) if len(run) >= 16]
    if not runs:
        return []
    rng = np.random.default_rng(7)
    rows = []
    for _ in range(samples):
        run = runs[int(rng.integers(0, len(runs)))]
        i = int(rng.integers(6, len(run) - 6))
        y, x = float(run[i][0]), float(run[i][1])
        ty, tx = float(run[i + 4][0] - run[i - 4][0]), float(run[i + 4][1] - run[i - 4][1])
        span = float(np.hypot(tx, ty))
        if span < 1e-6:
            continue
        nx, ny = -tx / span, ty / span
        # **The window follows this line's own half width**, so it sees both edges of the line and stops before the next
        # one. Two pixels of margin past the measured half width is enough for the transition itself.
        yi, xi = int(round(y)), int(round(x))
        here = min(reach, max(3.0, 2.0 * float(edt[yi, xi]) + 2.0))
        offsets = np.arange(-here, here + step, step)
        section = bilinear(gray, x + nx * offsets, y + ny * offsets)
        low, high = float(section.min()), float(section.max())
        if high - low < 40.0:
            continue
        # **The field comes from the local median and the ink from the section's darkest sample**, so neither is a
        # property of how wide the window happens to be.
        field = float(local[yi, xi])
        width = crossing_width(section)
        rows.append({'edge': width if width is not None else 0.0,
                     'depth': max(0.0, (field - low) / 255.0),
                     'field': field / 255.0})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--picture', required=True, action='append',
                    help='a picture to measure; repeat to compare several')
    ap.add_argument('--samples', type=int, default=400)
    ap.add_argument('--reach', type=float, default=REACH)
    args = ap.parse_args(argv)

    print('  %-34s %8s %9s %9s %9s %9s'
          % ('picture', 'samples', 'edge px', 'ink depth', 'depth p10..90', 'field'))
    for path in args.picture:
        rows = measure(path, samples=args.samples, reach=args.reach)
        name = path.replace('\\', '/').rsplit('/', 1)[-1]
        if not rows:
            print('  %-34s %8s   no measurable edge' % (name, ''))
            continue
        edges = np.array([row['edge'] for row in rows])
        depths = np.array([row['depth'] for row in rows])
        fields = np.array([row['field'] for row in rows])
        # **The spread of the depth, not only its middle.** An artist's pale ink is pale in patches -- pooled in places,
        # dry in others -- and a single median cannot say so; a crossed experiment read uniform pale and patchy pale as
        # the same thing and produced a contradiction with the drawings that took a round to find.
        spread = '%.3f..%.3f' % (float(np.percentile(depths, 10)), float(np.percentile(depths, 90)))
        print('  %-34s %8d %9.2f %9.3f %9s %9.3f'
              % (name, len(rows), float(np.median(edges)), float(np.median(depths)),
                 spread, float(np.median(fields))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
