"""Count finger-like protrusions in a region of a finished picture.

**Why this exists as a check at all.** The third table's first entries include a hand with six finger-like shapes and one
with four where five belong. Neither could be caught by anything in this repository, because every existing check reads
the project -- its marks, its layers, its invariants -- and those are faults in the picture. A hand is the easiest of them
to turn into a number: a drawn hand is a set of strokes that end in points, one point per finger, so **the number of
stroke ends in a hand's box is the number of fingers the drawing claims**.

**What this cannot do.** It counts ends of ink, so it counts a thumb crossing the palm as an end, counts a fold line in a
sleeve that enters the box as an end, and counts a broken stroke as two. The number is evidence and not a verdict; the
verdict is what a person says after looking at the same box.

    python tools/finger_count.py --image cache/paint16/final.png --box 1755,2074,2393,3031
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

import copy_linework as cl               # noqa: E402
import line_width_library as L           # noqa: E402


def ends_of(mask, min_length=6):
    """The tips of a stroke network: skeleton points with exactly one neighbour, grouped so one tip counts once.

    **A tip is usually several skeleton pixels wide**, so counting points overcounts by the width of the stroke's end. The
    points are labelled and each group counts as one tip -- a blunt end gives a little cluster, not four tips.
    """
    skeleton = cl.thin(mask.astype(np.uint8)).astype(bool)
    if not skeleton.any():
        return 0, skeleton
    kernel = np.ones((3, 3), dtype=np.uint8)
    kernel[1, 1] = 0
    neighbours = ndimage.convolve(skeleton.astype(np.uint8), kernel, mode='constant')
    tips = skeleton & (neighbours == 1)
    grouped, count = ndimage.label(tips, structure=np.ones((3, 3)))
    if min_length <= 0:
        return int(count), skeleton
    # **A tip on a stroke too short to be a finger is a speck**, and those come in numbers on a soft render.
    lengths = ndimage.sum(skeleton, grouped, range(1, count + 1))
    return int(count), skeleton


def count_fingers(gray, box, min_stroke=18):
    x0, y0, x1, y1 = box
    crop = gray[y0:y1, x0:x1]
    mask = L.line_mask(crop)
    skeleton = cl.thin(mask.astype(np.uint8)).astype(bool)
    if not skeleton.any():
        return {'tips': 0, 'strokes': 0, 'kept': 0}
    # **A finger is a stroke long enough to be one.** The skeleton is split into strokes by labelling the pixels that
    # remain after the branch points are removed, so a finger gives one long piece and a crack in the render gives a short
    # one.
    kernel = np.ones((3, 3), dtype=np.uint8)
    kernel[1, 1] = 0
    neighbours = ndimage.convolve(skeleton.astype(np.uint8), kernel, mode='constant')
    branch = skeleton & (neighbours >= 3)
    pieces, count = ndimage.label(skeleton & ~branch, structure=np.ones((3, 3)))
    lengths = ndimage.sum(skeleton, pieces, range(1, count + 1))
    kept = int((lengths >= min_stroke).sum())
    tips = int((skeleton & (neighbours == 1)).sum())
    return {'tips': tips, 'strokes': int(count), 'kept': kept,
            'longest': float(lengths.max()) if count else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--box', required=True, help='x0,y0,x1,y1 in pixels of the image as given')
    ap.add_argument('--min-stroke', type=float, default=18.0)
    args = ap.parse_args()

    box = tuple(int(v) for v in args.box.split(','))
    image = Image.open(args.image)
    gray = np.asarray(image.convert('L'), dtype=np.float32)
    print('  image %dx%d, box %s' % (image.size[0], image.size[1], box))
    result = count_fingers(gray, box, args.min_stroke)
    print('  stroke ends %d, skeleton pieces %d, of which %d are at least %.0f px long (longest %.0f)'
          % (result['tips'], result['strokes'], result['kept'], args.min_stroke, result['longest']))
    print()
    print('  **The count is evidence, not a verdict.** A thumb across the palm, a fold line entering the box and a broken')
    print('  stroke all report as ends. What this answers is whether a hand reports five; a person still has to look.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
