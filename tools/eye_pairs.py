"""Eyes as a pair of enclosed regions, found without a model.

**Why not a detector.** Every ready-made face detector is a fitted model, and a fitted model is the thing this library
exists to not be: it answers a face-like pattern with a face, cannot say why, and cannot be corrected by a measurement. What
a pair of eyes actually is can be written down instead -- two closed regions of similar size, at a similar height, side by
side, inside the top sixth of the figure -- and that statement can be checked, argued with and fixed.

**The measurement.** Fill the line drawing: what the strokes enclose becomes a solid, and subtracting the strokes leaves
the holes. A drawn eye is such a hole -- the whites and the iris are one enclosed region between the lashes and the lid --
and a speck of noise is a hole too, so size does the first cut and pairing does the rest.

**What this cannot do.** An eye whose outline is broken, a profile view with one eye, and a pair drawn at different
heights all defeat it. The count it returns is a candidate list, and a person still says whether the pair is eyes.
"""

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for extra in (ROOT, HERE):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np                       # noqa: E402
from PIL import Image                    # noqa: E402
from scipy import ndimage                # noqa: E402


def holes_of(mask):
    """The regions the strokes enclose, as `(area, cx, cy, w, h)` rows, largest first."""
    filled = ndimage.binary_fill_holes(mask)
    holes = filled & ~mask
    if not holes.any():
        return []
    labelled, count = ndimage.label(holes)
    rows = []
    for index, box in enumerate(ndimage.find_objects(labelled), start=1):
        y0, y1 = box[0].start, box[0].stop
        x0, x1 = box[1].start, box[1].stop
        area = float(ndimage.sum(holes, labelled, index))
        rows.append((area, (x0 + x1) * 0.5, (y0 + y1) * 0.5, x1 - x0, y1 - y0))
    rows.sort(reverse=True)
    return rows


def pairs(rows, min_area=120.0, max_area=20000.0, size_ratio=0.45, height_ratio=0.18,
          gap_ratio=0.35, span_ratio=8.0):
    """The candidates that could be one face's two eyes: similar size, similar height, side by side.

    **Each threshold is a statement about a face, not a tuned constant.** Two eyes are drawn at about the same size
    (`size_ratio`), on about the same line (`height_ratio`), separated by less than half a face's width (`gap_ratio`),
    and a pair that is further apart than eight of its own widths (`span_ratio`) is not one face's pair.
    """
    candidates = [r for r in rows if min_area <= r[0] <= max_area]
    out = []
    for i, first in enumerate(candidates):
        for second in candidates[i + 1:]:
            a1, x1, y1, w1, h1 = first
            a2, x2, y2, w2, h2 = second
            small, large = min(a1, a2), max(a1, a2)
            if small / large < size_ratio:
                continue
            width = 0.5 * (w1 + w2)
            height = 0.5 * (h1 + h2)
            if abs(y1 - y2) > height_ratio * max(height, 1.0) * 6.0:
                continue
            gap = abs(x2 - x1) - 0.5 * (w1 + w2)
            if gap < 0 or gap > gap_ratio * width * 3.0:
                continue
            span = abs(x2 - x1)
            if span > span_ratio * width:
                continue
            out.append((0.5 * (a1 + a2), 0.5 * (x1 + x2), 0.5 * (y1 + y2), span, max(height, 1.0)))
    out.sort(reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--ink', type=float, default=200.0, help='pixels darker than this are strokes')
    ap.add_argument('--head-band', type=float, default=0.22,
                    help='only look inside the top share of the figure, where a head is')
    args = ap.parse_args()

    gray = np.asarray(Image.open(args.image).convert('L'), dtype=np.float32)
    mask = gray < args.ink
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size == 0:
        print('  no ink')
        return 1
    top, bottom = int(rows[0]), int(rows[-1])
    band = top + args.head_band * (bottom - top)
    found = [r for r in holes_of(mask) if top <= r[2] <= band]
    print('  %d enclosed regions in the head band' % len(found))
    for row in found[:6]:
        print('    area %6d at (%.0f, %.0f) size %dx%d' % (row[0], row[1], row[2], row[3], row[4]))
    best = pairs(found)
    print()
    if not best:
        print('  no pair: no two similar regions side by side in the head band')
        return 0
    area, cx, cy, span, height = best[0]
    print('  best pair: centres %.0f apart, at y %.0f, average height %.0f, mean area %.0f'
          % (span, cy, height, area))
    print('  %d candidate pair%s' % (len(best), '' if len(best) == 1 else 's'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
