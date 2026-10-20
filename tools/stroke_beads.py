"""Measure the bead chain along a stroke: how often its opacity dips, and by how much.

**Why this exists.** A line came out looking like it was laid down dot by dot, and the answer was not in the path, the
control points or the width profile. It was in how the dabs of *one* stroke combine: the maximum path takes the higher
of two overlapping tips, so **a seam between two tips keeps only their falloff**, and a stroke becomes a chain of circles
that touch. `raster.WIDE_STROKE` used to send every stroke thinner than eight pixels down that path, on the recorded
belief that below that width the two methods give the same picture.

**They do not, and this is the measurement that says so.** The same stroke, deposited both ways:

    width 3 px, 161 px long      local minima     mean alpha    middle of the line
    maximum                              60             197    99 to 254
    integral                              6             223    255

A dip every 2.7 pixels is the dab step, and the dab step is set by the radius -- so **the finer the line, the more
beads per inch**, which is why an outline is the worst case rather than an edge case.

    python tools/stroke_beads.py --width 3.0 --length 160
"""
import argparse
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, raster


def alpha_row(layer, y):
    return [layer.data[(y * layer.width + x) * 4 + 3] for x in range(layer.width)]


def local_minima(seq):
    """How many times the opacity turns back up. **One turn is one bead.**"""
    turns = 0
    for k in range(1, len(seq) - 1):
        if seq[k] < seq[k - 1] and seq[k] <= seq[k + 1]:
            turns += 1
    return turns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--width', type=float, default=3.0, help='stroke width in pixels')
    ap.add_argument('--length', type=float, default=160.0, help='length in pixels')
    ap.add_argument('--brush', default='fine')
    ap.add_argument('--seed', type=int, default=11)
    ap.add_argument('--show', type=int, default=48, help='how many samples of the profile to print')
    args = ap.parse_args()

    pts = [(20.0, 32.0), (20.0 + args.length, 32.0)]
    profile = [args.width] * (16 * (len(pts) - 1) + 1)
    rec = core.stroke_record(pts, args.brush, seed=args.seed, resolution=16, width_profile=profile)
    rec['colour_int'] = 0

    print('  brush %s, width %.1f px, %.0f px long' % (args.brush, args.width, args.length))
    print('    %-10s %8s %8s %8s %8s' % ('path', 'mean', 'min', 'max', 'dips'))
    for density in (False, True):
        layer = raster.stroke_layer(rec, int(40 + args.length), 64, 1.0, density=density)
        inside = [a for a in alpha_row(layer, 32) if a > 0]
        if not inside:
            print('    %-10s  nothing laid down' % ('integral' if density else 'maximum'))
            continue
        print('    %-10s %8.1f %8d %8d %8d'
              % ('integral' if density else 'maximum', sum(inside) / float(len(inside)),
                 min(inside), max(inside), local_minima(inside)))
        print('       %s' % inside[:args.show])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
