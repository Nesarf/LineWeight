"""Where the three masses sit inside a silhouette, found by measuring width along height.

**Why this works and the edge tracer did not.** The edge tracer needed the premise "lines are separate from fills", and a
painted illustration has that premise false everywhere. **This one needs no premise beyond the silhouette being a
silhouette**: a figure is wide at the shoulders, narrow at the neck, wide at the hips, and narrow where the legs part.
Those are extrema of a single one-dimensional function, and extrema are what a person can read off a graph.

**What the numbers are and are not.** The waist found this way is the waist **the silhouette has** -- a coat, a skirt or
a long braid can put it somewhere the body is not. So this reports a position and says what it is the position of; it
does not claim to recover a skeleton from a picture.

    python tools/silhouette_profile.py --src E:\\DaShaoHuo\\cache\\trace-mmk.json
"""
import argparse
import json
import pathlib
import sys


def load_control(path):
    """The dense resampled outline, not the simplified control points.

    **The dense one is needed here.** The control points are 227 for a figure 1152 tall, so most height bands contain no
    point at all and the width reads as zero -- a curve full of holes. `centre` holds the same outline resampled to
    roughly one point every half pixel of arc, which is what a width-per-height measurement needs.
    """
    d = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    pts = []
    for m in d.get('marks', []):
        g = m['geometry']
        pts.extend(g.get('centre') or g.get('control') or [])
    return pts


def profile(points, bins=120):
    """The horizontal span of the silhouette at each height, as (y, x_min, x_max, width)."""
    if not points:
        return []
    ys = [p[1] for p in points]
    y0, y1 = min(ys), max(ys)
    step = (y1 - y0) / bins
    rows = []
    for i in range(bins):
        lo = y0 + i * step
        hi = lo + step
        band = [p[0] for p in points if lo <= p[1] < hi]
        if band:
            rows.append((lo + step / 2.0, min(band), max(band), max(band) - min(band)))
    return rows


def extrema(rows, win=7):
    """Local minima and maxima of the width curve.

    **A minimum is a narrowing and a maximum a widening**, and a window is used rather than the immediate neighbours
    because the boundary is simplified and its width jitters by a couple of points at every step. Seven bins is about a
    twentieth of the figure's height, which is roughly the scale of a feature rather than of a jitter.
    """
    mins, maxs = [], []
    w = [r[3] for r in rows]
    for i in range(len(rows)):
        lo, hi = max(0, i - win), min(len(rows), i + win + 1)
        if w[i] == min(w[lo:hi]) and (not mins or i - mins[-1][0] > win):
            mins.append((i, rows[i][0], w[i]))
        if w[i] == max(w[lo:hi]) and (not maxs or i - maxs[-1][0] > win):
            maxs.append((i, rows[i][0], w[i]))
    return mins, maxs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--bins', type=int, default=120)
    ap.add_argument('--win', type=int, default=7)
    ap.add_argument('--bars', type=int, default=56)
    args = ap.parse_args()

    pts = load_control(args.src)
    if not pts:
        print('  no control points in %s' % args.src)
        return 1
    rows = profile(pts, args.bins)
    if not rows:
        print('  empty profile')
        return 1
    top, bottom = rows[0][0], rows[-1][0]
    height = bottom - top
    widest = max(r[3] for r in rows)
    print('  %s' % pathlib.Path(args.src).name)
    print('  %d points, height %.1f, widest %.1f' % (len(pts), height, widest))
    print()
    print('  the width curve, top to bottom (each bar is one bin):')
    for y, x0, x1, w in rows:
        frac = (y - top) / height if height else 0.0
        n = int(round(args.bars * w / widest)) if widest else 0
        print('    %4.3f  %-*s %6.1f' % (frac, args.bars, '#' * n, w))

    mins, maxs = extrema(rows, args.win)
    print()
    print('  narrowings (candidates for neck and waist), as a fraction of the height:')
    for i, y, w in mins:
        print('    y = %.3f of the figure   width %.1f  (%.0f%% of the widest)' % ((y - top) / height, w, 100.0 * w / widest if widest else 0))
    print('  widenings (candidates for rib cage and pelvis):')
    for i, y, w in maxs:
        print('    y = %.3f of the figure   width %.1f  (%.0f%% of the widest)' % ((y - top) / height, w, 100.0 * w / widest if widest else 0))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
