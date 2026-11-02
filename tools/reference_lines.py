"""A project built from a reference picture's own lines, so the break counter can be pointed at a drawing that is known good.

The counter has only ever run on output, where "279 breaks" has nothing to mean anything against. A picture an artist made
is the obvious baseline, and its lines can be taken with `line_mask` -- thin, and darker than its own surroundings -- which
4.12 validated across four styles: on a line drawing it finds the ink, and on a painted one it finds the linework the paint
did not cover.

**What this is not.** These are the artist's own lines, so nothing here was reconstructed and there is no join step behind
them. The number says what the same counter reads on a drawing where the lines were drawn rather than recovered, and that
is exactly the comparison the row was missing.

    python tools/reference_lines.py --picture ref.jpg --out ref-lines.json
"""

import argparse
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)

from copy_linework import prune, thin, trace
from lineweight import core, project
from line_width_library import line_mask


def _bilinear(field, xs, ys):
    """The mask sampled between pixels, so a cross-section is a length instead of a count."""
    height, width = field.shape
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    fx = xs - x0
    fy = ys - y0
    x0 = np.clip(x0, 0, width - 1)
    y0 = np.clip(y0, 0, height - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    return (field[y0, x0] * (1 - fx) * (1 - fy) + field[y0, x1] * fx * (1 - fy)
            + field[y1, x0] * (1 - fx) * fy + field[y1, x1] * fx * fy)


def subpixel_axis(mask, run, edt=None, step=0.25, extra=2.0):
    """The ink's own centre and thickness across a skeleton run, at sub-pixel positions.

    **The skeleton is a pixel path; the ink is not.** A skeleton pixel names a corner of the grid, so its own distance to
    the boundary is quantised to half a pixel, and where strokes meet or bend the thinning algorithm drifts off the centre
    line altogether. Measured on a reference's own lines, a project rebuilt from the skeleton left **40 per cent of the
    ink uncovered at the pixel level** while reaching all of it within six pixels -- so the lines were in the right place
    and were not the same pixels.

    Each run point therefore gets a cross-section: the ink sampled along the normal at a quarter-pixel step, its centroid
    as the offset to apply, and its extent as the width. **That is what turns a centre line into something the ink agrees
    with**, and it costs one bilinear sample per offset rather than a new skeletoniser.

    Returns `(points, widths)` in image pixels, one entry per run point.
    """
    field = mask.astype(np.float64)
    if edt is None:
        edt = ndimage.distance_transform_edt(mask)
    count = len(run)
    points, widths = [], []
    for i in range(count):
        y, x = run[i]
        prev = run[max(0, i - 1)]
        nxt = run[min(count - 1, i + 1)]
        ty, tx = float(nxt[0] - prev[0]), float(nxt[1] - prev[1])
        length = math.hypot(tx, ty)
        if length < 1e-9:
            tx, ty = 1.0, 0.0
        else:
            tx, ty = tx / length, ty / length
        nx, ny = -ty, tx
        # **The reach follows the local half width.** A fixed window clips a heavy line and swallows its neighbour on a
        # fine one; two pixels beyond the measured half width is enough to see both edges of anything narrower than that.
        reach = max(4.0, 2.0 * float(edt[y, x]) + extra)
        offsets = np.arange(-reach, reach + step, step)
        vals = _bilinear(field, x + nx * offsets, y + ny * offsets)
        total = float(vals.sum())
        if total <= 1e-6:
            points.append((float(x), float(y)))
            widths.append(1.0)
            continue
        shift = float((offsets * vals).sum() / total)
        points.append((x + nx * shift, y + ny * shift))
        widths.append(total * step)
    return points, widths


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--picture', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--prune', type=int, default=4, help='skeleton spurs shorter than this are cut')
    parser.add_argument('--min-segment', type=int, default=6, help='runs shorter than this are dropped')
    args = parser.parse_args()

    image = Image.open(args.picture).convert('L')
    gray = np.asarray(image, dtype=np.float64)
    mask = line_mask(gray)
    # **The page follows the same rule as the rest of the tools**, so this project can be measured against one the
    # pipeline produced: a long side of at least 2880, never smaller than what it copies. Without it, a reference at 800
    # px and an output at 2880 px cannot be compared at any fixed pixel threshold -- a 200 px run is 25 per cent of one
    # canvas and 7 per cent of the other.
    canvas_long = max(2880.0, float(max(image.size)))
    scale = canvas_long / float(max(image.size))
    canvas = project.Project(width=int(round(image.size[0] * scale)), height=int(round(image.size[1] * scale)),
                             title='lines of %s' % os.path.basename(args.picture))

    skeleton = prune(thin(mask.astype(np.uint8)), args.prune)
    runs = trace(skeleton)
    kept = [run for run in runs if len(run) >= args.min_segment]
    # **The ink's own width and centre, from a cross-section at each skeleton point.** This wrote a constant `2 * scale`
    # for every mark, which is the same fault `render_to_project` had: a traced picture came out at one thickness whatever
    # the reference said. Then it read the distance transform, which gets the width right and still leaves the centre on
    # the integer grid -- measured, 40 per cent of the ink was uncovered at the pixel level while all of it was reached
    # within six. `subpixel_axis` samples across the line instead: the centroid moves the point off the grid and the
    # extent is the width.
    edt = ndimage.distance_transform_edt(mask)
    written = 0
    for i, run in enumerate(kept):
        px_points, px_widths = subpixel_axis(mask, run, edt=edt)
        if len(px_points) < 2:
            continue
        # **`resolution=1` keeps every cross-section**, because `catmull` at one sample per segment returns the points it
        # was given. Simplifying first would put the width profile at control-point resolution and describe a different
        # polyline than the one drawn -- which is what the previous version had to work around by expanding twice.
        points = [(x * scale, y * scale) for x, y in px_points]
        widths = [max(1.0, w * scale) for w in px_widths]
        record = core.stroke_record(points, 'fine', seed=i, resolution=1,
                                    width_profile=widths, absolute_width=True)
        canvas.add_stroke(record, stage='line', layer='ink', note='reference %d' % i)
        written += 1

    project.save_project(canvas, args.out)
    print('  %s %dx%d, %d line px, %d runs, %d marks -> %s'
          % (os.path.basename(args.picture), image.size[0], image.size[1],
             int(mask.sum()), len(runs), written, args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
