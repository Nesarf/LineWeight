"""Whether the lines drawn are the lines an artist would draw, against a reference that has both colour and line.

**Why this needs a top hat.** The reference is a painted illustration, so `gray < 205` finds every dark fill along with
every line and the comparison would be against the wrong set. A closing with a small element removes thin dark
structures and leaves the field behind them, and an opening does the same for a light line over a dark field; whichever
is larger at a pixel is a line. That is thickness, so a dark fill cannot be mistaken for one -- see `AESTHETIC-LIBRARY.md`
4.30 and `tools/line_field.py`.

**What the two numbers say.** `precision` is the share of the drawn line that lands within a tolerance of the artist's
line: a low precision is line that should not have been drawn. `recall` is the share of the artist's line that the
drawing reaches: a low recall is line that is missing. `overdrawn_lines` in `learn/errors.jsonl` is a coverage failure,
which says how much ink there is and nothing about which of it is wrong; this is the measurement that can say.

**The tolerance is stated.** Six pixels on the 2880 page is about one line width at the lower end of the artists' range,
so a line that sits on the artist's line counts as agreement and a line a full width away does not.

    python tools/line_agreement.py --reference ref.png --drawn cache/paint20/lines.png
"""
import argparse
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

LONG_SIDE = 2880
ELEMENT = 9
FLOOR = 12.0
TOLERANCE = 6.0
#: The ink threshold for the drawn layer only. A line layer is drawn on a pale page, so a fixed threshold is right
#: there; the reference goes through the top hat instead.
INK = 205


def load_gray(path, long_side=LONG_SIDE):
    im = Image.open(path).convert('L')
    w, h = im.size
    if max(w, h) < long_side:
        s = float(long_side) / max(w, h)
        im = im.resize((int(round(w * s)), int(round(h * s))), Image.LANCZOS)
    return np.asarray(im, dtype=np.float64)


def artist_line(a, element=ELEMENT, floor=FLOOR):
    """The reference's own lines, by thickness rather than by lightness."""
    closed = ndimage.grey_closing(a, size=element)
    opened = ndimage.grey_opening(a, size=element)
    darker = closed - a
    lighter = a - opened
    return (((darker > floor) & (darker >= lighter))
            | ((lighter > floor) & (lighter > darker)))


def drawn_line(gray):
    return gray < INK


def agreement(drawn, art, tolerance=TOLERANCE):
    """Precision and recall of the drawn line against the artist's, within a distance."""
    if drawn.shape != art.shape:
        return None
    to_art = ndimage.distance_transform_edt(~art)
    to_drawn = ndimage.distance_transform_edt(~drawn)
    hit = to_art[drawn] <= tolerance
    reached = to_drawn[art] <= tolerance
    return dict(
        drawn_px=int(drawn.sum()),
        art_px=int(art.sum()),
        precision=float(hit.mean()) if hit.size else 0.0,
        recall=float(reached.mean()) if reached.size else 0.0,
        # How far off the misses are, which says whether a line is misplaced or merely shifted.
        miss_median=float(np.median(to_art[drawn][~hit])) if (~hit).any() else 0.0,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--reference', required=True, help='a painted picture that has both colour and line')
    ap.add_argument('--drawn', required=True, help='the line layer drawn from it')
    ap.add_argument('--tolerance', type=float, default=TOLERANCE)
    ap.add_argument('--element', type=int, default=ELEMENT)
    ap.add_argument('--floor', type=float, default=FLOOR)
    args = ap.parse_args(argv)

    reference = load_gray(args.reference)
    drawn_gray = load_gray(args.drawn)
    if reference.shape != drawn_gray.shape:
        raise SystemExit('the two pictures differ in size after scaling: %s vs %s'
                         % (reference.shape, drawn_gray.shape))
    art = artist_line(reference, element=args.element, floor=args.floor)
    drawn = drawn_line(drawn_gray)
    r = agreement(drawn, art, tolerance=args.tolerance)
    if r is None:
        raise SystemExit('nothing to compare')
    print('  reference line  %8d px   (%.2f%% of the page)' % (r['art_px'], 100.0 * r['art_px'] / art.size))
    print('  drawn line      %8d px   (%.2f%% of the page)' % (r['drawn_px'], 100.0 * r['drawn_px'] / drawn.size))
    print('  precision       %7.1f%%   the share of the drawn line within %.1f px of the artist\'s'
          % (r['precision'] * 100.0, args.tolerance))
    print('  recall          %7.1f%%   the share of the artist\'s line the drawing reaches' % (r['recall'] * 100.0))
    if r['miss_median']:
        print('  missed lines sit %.1f px from the artist\'s at the median' % r['miss_median'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
