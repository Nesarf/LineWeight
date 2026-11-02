"""The line against the field it crosses, separated by a morphological top hat rather than by a threshold.

**Why not a threshold.** Ink is darker than paper on a line drawing, so `gray < 205` finds the line. On a shaded picture
the same rule finds every dark fill as well: the helmet, the shadows and the line are all "ink", and a ring drawn around
them can only reach pale background. Measured that way every drawing returns 100 per cent "the line is darker",
including the ones where the line is visibly a bright seam.

**What separates them is thickness.** A closing with a small structuring element removes thin dark structures and
leaves the field behind them, so `closing - a` is how much darker than its local field a pixel is, and it is large
exactly on a dark line. Opening gives the same for a light line over a dark field. Taking whichever is larger at each
pixel finds the line, and the closing or opening value there is the field it sits on -- so the difference is measured on
whichever side the line chose, which is the question.

**What the number is for.** A line drawn at one lightness has `|line - field|` equal to the distance from that lightness
to the field, so it grows wherever the field moves away from the chosen colour. A line whose lightness tracks the field
keeps one distance everywhere. Comparing that magnitude against drawings is how "the palette does not follow the field"
was tested -- and refuted: see `AESTHETIC-LIBRARY.md` 4.30.

**The element size is a choice and it is stated.** A line on a 2880-long page is about seven pixels across; nine pixels
is wide enough to close over it and narrow enough not to close over a shape.

    python tools/line_field.py --pictures one.png two.jpg --element 9 --floor 12
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

LONG_SIDE = 2880
ELEMENT = 9
FLOOR = 12.0


def measure(path, long_side=LONG_SIDE, element=ELEMENT, floor=FLOOR):
    """The line's difference from its field, or None when no line is found at these settings."""
    im = Image.open(path).convert('L')
    w, h = im.size
    if max(w, h) < long_side:
        s = float(long_side) / max(w, h)
        im = im.resize((int(round(w * s)), int(round(h * s))), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float64)
    closed = ndimage.grey_closing(a, size=element)
    opened = ndimage.grey_opening(a, size=element)
    darker = closed - a
    lighter = a - opened
    is_dark = (darker > floor) & (darker >= lighter)
    is_light = (lighter > floor) & (lighter > darker)
    line = is_dark | is_light
    if line.sum() < 500:
        return None
    field = np.where(is_dark, closed, opened)
    diff = a[line] - field[line]
    mag = np.abs(diff)
    field_at_line = field[line]
    return dict(
        pixels=int(line.sum()),
        dark_share=float(is_dark.sum()) / float(line.sum()),
        median=float(np.median(diff)),
        mag_median=float(np.median(mag)),
        mag_p10=float(np.percentile(mag, 10)),
        mag_p90=float(np.percentile(mag, 90)),
        field_p10=float(np.percentile(field_at_line, 10)),
        field_p90=float(np.percentile(field_at_line, 90)),
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--pictures', nargs='+', required=True)
    ap.add_argument('--element', type=int, default=ELEMENT,
                    help='structuring element in pixels; a line on the 2880 page is about seven across')
    ap.add_argument('--floor', type=float, default=FLOOR,
                    help='how much darker or lighter than its field a pixel must be before it counts as line')
    args = ap.parse_args(argv)
    print('  %-26s %8s %9s %9s %9s %9s %9s'
          % ('file', 'dark%', 'diff med', '|diff| med', '|diff| p10', '|diff| p90', 'field med'))
    for path in args.pictures:
        r = measure(path, element=args.element, floor=args.floor)
        name = os.path.basename(path)
        if r is None:
            print(f'  {name:26s} no line found at these settings')
            continue
        print('  %-26s %7.1f%% %9.1f %9.1f %9.1f %9.1f %9.1f'
              % (name, r['dark_share'] * 100, r['median'], r['mag_median'],
                 r['mag_p10'], r['mag_p90'], (r['field_p10'] + r['field_p90']) / 2.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
