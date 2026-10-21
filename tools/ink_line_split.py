"""Separate what is drawn with a line from what is filled in with ink.

**Why the distinction is not cosmetic.** A stroke has a width that belongs to the pen; a filled patch has a width that
belongs to the shape. Tracing treats both the same way -- the distance transform measures whichever it meets -- so a
solid black pupil comes out as a very heavy line and a hatched shadow as a dozen parallel ones. **A drawing is made of
two different marks and this measures how much of each a reference contains.**

**The measurement is the distance transform again, read as a distribution.** A line's half-width is small and stable; a
patch's grows to whatever the patch is. So the share of ink whose half-width exceeds a threshold is the share that is
fill, and the threshold is where a pen stops and a brush begins.
"""
import os
import sys

import numpy as np

sys.path.insert(0, r'E:\lineweight\tools')

import copy_linework as cl

#: Work pixels of half-width above which a mark is a patch rather than a line. **Six is a wide nib at the reading size**:
#: at 2880 across a drawn line measures one to four, and a sleeve's hatching or a filled pupil grows past ten.
FILL_HALF = 6.0


def stats(path, min_long_side=2880, ink=205):
    binary, w, h = cl.load_ink(path, min_long_side, ink)
    if not binary.any():
        return None
    weight = cl.ink_weight(binary)
    inside = weight[binary > 0]
    total = float(inside.size)
    thick = float((inside > FILL_HALF).sum())
    return {
        'name': os.path.basename(path),
        'w': w, 'h': h,
        'ink': total / (w * h),
        'p50': float(np.percentile(inside, 50)),
        'p95': float(np.percentile(inside, 95)),
        'max': float(inside.max()),
        'fill': thick / total,
    }


def main():
    rows = []
    for path in sys.argv[1:]:
        if not os.path.isfile(path):
            continue
        r = stats(path)
        if r:
            rows.append(r)
    print('  %-30s %10s %7s %7s %7s %8s' % ('file', 'ink', 'half p50', 'p95', 'max', 'fill share'))
    for r in rows:
        print('  %-30s %10.4f %7.2f %7.2f %7.2f %8.3f'
              % (r['name'][:30], r['ink'], r['p50'], r['p95'], r['max'], r['fill']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
