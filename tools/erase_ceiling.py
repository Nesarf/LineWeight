"""What a perfect eraser could reach -- the ceiling on repairing a line layer by subtraction.

**The question this answers.** The eraser mark exists, and the next thing anyone will want to do with it is erase the ink
that is not on a line. Before writing a decider (which pixels are not on a line) it is worth knowing what perfect
deciding would buy, because that number says whether the layer is reachable at all.

So this keeps every drawn pixel within `t` of the artist's own line and erases the rest, for a sweep of `t`, and quotes
the symmetric difference against the thresholds the project measures itself by:

    1 per cent      82 944 px on a 2880 square
    0.05 per cent    4 147 px
    0.0008 per cent     66 px

**Read it as an upper bound.** A real eraser decides without being told where the artist's line is; this one is handed
the answer. **And read `precision` with it**: at every cut the precision is 100 per cent by construction -- what survives
is defined as "within t" -- so the number that moves is the symmetric difference, and what it is made of is then the
question. At 6 px, 969 817 px of difference remain while the precision reads 100, which means the difference is not the
ink that was erased at all: it is the ink that was kept, sitting near the line rather than on it.

    python tools/erase_ceiling.py --reference ref.png --drawn cache/paint21/lines.png
"""
import argparse
import sys

import numpy as np
from scipy import ndimage

import line_agreement as la

#: The cuts to report, in page pixels. Below one the erase is wider than the tolerance and starts eating the line it is
#: supposed to keep; above six there is nothing left to erase that could be called wrong.
CUTS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--reference', required=True, help='the picture the layer was drawn from')
    ap.add_argument('--drawn', required=True, help='the line layer, as PNG')
    ap.add_argument('--long-side', type=int, default=la.LONG_SIDE)
    ap.add_argument('--tolerance', type=float, default=la.TOLERANCE)
    #: **The reference line's own definition, and it moves the answer more than the eraser does.** `line_agreement`
    #: explains why 40 is the honest floor for ink; 12 is included here because it is the other number the project has
    #: recorded, and running both turns "how close is the copy" into "how close, under which definition of the line".
    ap.add_argument('--floor', type=float, default=la.FLOOR)
    ap.add_argument('--element', type=int, default=la.ELEMENT)
    args = ap.parse_args(argv)

    long_side = args.long_side
    page = long_side * long_side
    art = la.artist_line(la.load_gray(args.reference, long_side), element=args.element, floor=args.floor)
    drawn = la.drawn_line(la.load_gray(args.drawn, long_side))
    if art.shape != drawn.shape:
        raise SystemExit('the two pictures differ in size: %s vs %s' % (art.shape, drawn.shape))
    to_art = ndimage.distance_transform_edt(~art)

    def sd(d):
        return int((d ^ art).sum())

    print('  page            %8d px   1%% = %d   0.05%% = %d   0.0008%% = %d'
          % (page, int(0.01 * page), int(0.0005 * page), int(0.000008 * page)))
    print('  reference line  %8d px   (%.2f%%)' % (art.sum(), 100.0 * art.sum() / page))
    print('  drawn line      %8d px   (%.2f%%)' % (drawn.sum(), 100.0 * drawn.sum() / page))
    print()
    print('  %-8s %10s %10s %10s %11s %8s %10s'
          % ('keep<=', 'drawn px', 'SD px', 'SD/ink', 'precision', 'recall', 'erased px'))
    print('  %-8s %10d %10d %9.1f%% %10.1f%% %7.1f%% %10d'
          % ('all', drawn.sum(), sd(drawn), 100.0 * sd(drawn) / max(1, art.sum()),
             100.0 * (to_art[drawn] <= args.tolerance).mean(), 100.0, 0))
    for t in CUTS:
        kept = drawn & (to_art <= t)
        if not kept.any():
            continue
        to_kept = ndimage.distance_transform_edt(~kept)
        print('  %-8s %10d %10d %9.1f%% %10.1f%% %7.1f%% %10d'
              % ('%g' % t, kept.sum(), sd(kept), 100.0 * sd(kept) / max(1, art.sum()),
                 100.0 * (to_art[kept] <= args.tolerance).mean(),
                 100.0 * (to_kept[art] <= args.tolerance).mean(),
                 int((drawn & (to_art > t)).sum())))
    print()
    # **The same difference under the page's own rule and under the ink's.** The thresholds this project carries --
    # 1, 0.05, 0.0008 per cent -- are shares of the *page*, and a page holds whatever ink the drawing happens to hold.
    # Measured over eleven line drawings, the symmetric difference comes out at 15 to 35 per cent of the reference's
    # ink whatever its absolute size, because it is made of boundary pixels and a boundary's length follows the ink. So
    # an absolute figure compares one drawing with itself across two attempts, and a share compares two drawings.
    threshold = int(0.01 * page)
    print('  **Two readings of the same difference.** It is %d px, which is %.3f per cent of the page and %.1f per cent'
          % (sd(drawn), 100.0 * sd(drawn) / page, 100.0 * sd(drawn) / max(1, art.sum())))
    print('  of this reference\'s ink. The one per cent threshold is %d px -- %.1f per cent of this reference\'s ink.'
          % (threshold, 100.0 * threshold / max(1, art.sum())))
    print('  The page figure is what the project quotes; the ink figure is what travels between drawings.')
    print()
    print('  **The precision column is 100 by construction at every cut** -- what survives is *defined* as being within')
    print('  the cut -- so the number to read is the symmetric difference, and what makes it up is the next question.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
