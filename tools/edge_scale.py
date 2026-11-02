"""Is the transition hard or soft, measured by how much of it a larger element still finds?

A drawn line is a step: the value goes from the field to the ink within a pixel or two. A modelled shadow is a ramp: the
same total change spread over twenty pixels. A single threshold on the size of the change cannot tell them apart -- a
strong ramp and a faint line have the same difference -- which is why `min-light-gap` traded precision for recall and
nothing else.

**What separates them is how the change behaves when the measuring element grows.** A closing with an element of size k
fills any dark structure narrower than k and leaves the field behind it, so `closing_k(a) - a` is the depth of the dark
structure at that scale. A two-pixel line is filled at nine and at forty-one alike, so the two measurements agree. A
twenty-pixel ramp is filled only at forty-one: at nine the element sits inside the ramp and finds nothing to fill.

    small = closing  9(a) - a     the depth seen at the scale of a line
    large = closing 41(a) - a     the depth seen at the scale of a shadow

`large >= small` always, and `small / large` is near one on a step and near zero on a ramp. **That ratio is what a
brush's hardness is**, and it is the axis the line finder has been missing: it does not ask how dark the transition is,
it asks whether the transition happens all at once.

    python tools/edge_scale.py --picture ref.png
"""
import argparse
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

SMALL = 9
LARGE = 41
FLOOR = 12.0


def load_gray(path, long_side=2880):
    im = Image.open(path).convert('L')
    w, h = im.size
    if max(w, h) < long_side:
        s = float(long_side) / max(w, h)
        im = im.resize((int(round(w * s)), int(round(h * s))), Image.LANCZOS)
    return np.asarray(im, dtype=np.float64)


def scales(gray, small=SMALL, large=LARGE):
    """The depth of every dark structure and every light one, at two element sizes."""
    dark_small = ndimage.grey_closing(gray, size=small) - gray
    dark_large = ndimage.grey_closing(gray, size=large) - gray
    light_small = gray - ndimage.grey_opening(gray, size=small)
    light_large = gray - ndimage.grey_opening(gray, size=large)
    return dark_small, dark_large, light_small, light_large


def hardness(dark_small, dark_large, light_small, light_large, floor=FLOOR):
    """The share of each structure's depth that a forty-one-pixel element still finds, and the candidate mask."""
    candidate = (dark_small > floor) | (light_small > floor)
    dark_wins = dark_small >= light_small
    narrow = np.where(dark_wins, dark_small, light_small)
    wide = np.where(dark_wins, dark_large, light_large)
    kept = narrow / np.maximum(wide, 1.0)
    return candidate, kept, narrow


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--picture', required=True)
    ap.add_argument('--floor', type=float, default=FLOOR)
    args = ap.parse_args(argv)
    a = load_gray(args.picture)
    dsmall, dlarge, lsmall, llarge = scales(a)
    candidate, kept, narrow = hardness(dsmall, dlarge, lsmall, llarge, floor=args.floor)
    if candidate.sum() < 500:
        raise SystemExit('no candidate structure at these settings')
    k = kept[candidate]
    print('  candidates  %d px  (%.2f%% of the page)'
          % (int(candidate.sum()), 100.0 * candidate.sum() / candidate.size))
    print()
    print('  how much of the depth a 41-pixel element still finds:')
    for q in (5, 10, 25, 50, 75, 90, 95):
        print('    p%-3d %5.1f%%' % (q, np.percentile(k, q) * 100.0))
    print()
    for cut in (0.05, 0.3, 0.5, 0.7, 0.9, 0.95):
        hard = candidate & (kept >= cut)
        print('  keeping %3.0f%% of the depth or more: %7d px  (%.2f%% of the page, %.1f%% of the candidates)'
              % (cut * 100, int(hard.sum()), 100.0 * hard.sum() / hard.size, 100.0 * hard.sum() / candidate.sum()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
