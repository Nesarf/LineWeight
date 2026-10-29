"""How far apart the dabs of a stroke may sit, judged by the **edge** rather than by the centre line.

**Two questions, and the table only answered one.** `spacing = 0.56` was swept by asking whether a straight stroke stays
one run of ink: at 0.8 of a dab's diameter it does, at 1.0 it breaks into beads. That is a question about the *centre
line*. The eye reads the *edge*, and on a six-pixel brush with hard dabs the edge is a run of scallops at 3.6 pixels
apart -- visible in `cache/brushes.png` on every wide brush and absent on the two narrow ones.

So this measures the width along a straight stroke: for each column, how many pixels carry ink. A row of dabs meeting in
overlapping circles gives a width that rises and falls with the spacing; the amplitude of that rise and fall, as a
fraction of the median width, is the scallop.

    python tools/dab_spacing.py --brush ink --sweep 0.56,0.35,0.25,0.15,0.10
"""
import argparse
import pathlib
import sys

import numpy as np

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, raster

#: What counts as ink when the widths are counted. Eight of 255 is far below anything visible, so the measurement is of
#: where the mark ends rather than of how dark it is.
LIT = 8


def width_profile(record, width, height):
    """The **ink** carried by each column of a rendered stroke, in units of one fully covered pixel.

    **Counting lit pixels was tried first and it cannot answer the question.** A count is an integer, so the smallest
    wobble it can report is one whole pixel -- and on a fine brush the median width is two pixels, which made the scallop
    read as 1.00 there whatever the spacing was. Summing alpha instead is continuous: a column that is 40 per cent
    covered counts as 0.4 of a pixel, so a sub-pixel scallop is a number rather than a rounding.
    """
    layer = raster.stroke_layer(record, width, height)
    data = np.frombuffer(bytes(layer.data), dtype=np.uint8).reshape(height, width, 4)
    return data[:, :, 3].astype(np.float64).sum(axis=0) / 255.0


def scallop(profile, left, right):
    """The rise and fall of the width in the middle of a stroke, as pixels and as a fraction of the median.

    **The ends are excluded on purpose.** A taper is a deliberate narrowing over tens of pixels and would swamp a
    measurement about a three-pixel wobble; what is wanted here is the middle, where the width should be flat.
    """
    middle = np.asarray(profile[left:right], dtype=np.float64)
    if middle.size < 10:
        return 0.0, 0.0, 0.0
    median = float(np.median(middle))
    if median <= 0:
        return 0.0, 0.0, 0.0
    spread = float(np.percentile(middle, 95) - np.percentile(middle, 5))
    return median, spread, spread / median


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--brush', default='ink')
    ap.add_argument('--sweep', default='0.56,0.44,0.35,0.25,0.18,0.12')
    ap.add_argument('--size', type=float, default=1.0, help='the brush size multiplier')
    ap.add_argument('--length', type=int, default=900)
    ap.add_argument('--pad', type=int, default=120, help='columns skipped at each end, past the taper')
    args = ap.parse_args()

    brush = core.BRUSHES[args.brush]
    # **The taper is a multiple of the width, so the guard has to be too** -- and it is what decides where the middle
    # starts, which is why the pad is quoted in pixels rather than guessed.
    entry = brush['taper_in'] * brush['width'] * args.size
    pad = max(args.pad, int(entry * 1.5))
    height = int(brush['width'] * args.size * 3) + 40
    width = args.length

    print('  %s: width %.1f, taper entry %.1f px, measuring columns %d..%d'
          % (args.brush, brush['width'] * args.size, entry, pad, width - pad))
    print('  %-7s %8s %10s %10s' % ('spacing', 'median', 'scallop px', 'as fraction'))

    original = brush['spacing']
    rows = []
    try:
        for value in (float(v) for v in args.sweep.split(',')):
            brush['spacing'] = value
            record = core.stroke_record([(20.0, height / 2.0), (width - 20.0, height / 2.0)],
                                        args.brush, seed=5, size=args.size)
            record['colour_int'] = (0, 0, 0)
            profile = width_profile(record, width, height)
            median, spread, fraction = scallop(profile, pad, width - pad)
            rows.append((value, median, spread, fraction))
            print('  %-7.2f %8.2f %10.2f %10.3f' % (value, median, spread, fraction))
    finally:
        brush['spacing'] = original

    # **A scallop of half a pixel is invisible** -- it is inside the anti-aliasing of the edge itself. That is the
    # threshold this reports against, and it is deliberately a physical quantity rather than a chosen fraction.
    good = [row for row in rows if row[2] <= 0.5]
    if good:
        print('  the widest spacing whose scallop is still under half a pixel: %.2f' % max(r[0] for r in good))
    else:
        print('  no spacing in the sweep brings the scallop under half a pixel')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
