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
import os
import sys

import numpy as np
from PIL import Image

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)

from copy_linework import prune, simplify, thin, trace
from lineweight import core, project
from line_width_library import line_mask


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
    written = 0
    for i, run in enumerate(kept):
        points = simplify([(float(x) * scale, float(y) * scale) for y, x in run], 0.9)
        if len(points) < 2:
            continue
        samples = 4 * (len(points) - 1) + 1
        record = core.stroke_record(points, 'fine', seed=i, resolution=4,
                                    width_profile=[2.0 * scale] * samples)
        canvas.add_stroke(record, stage='line', layer='ink', note='reference %d' % i)
        written += 1

    project.save_project(canvas, args.out)
    print('  %s %dx%d, %d line px, %d runs, %d marks -> %s'
          % (os.path.basename(args.picture), image.size[0], image.size[1],
             int(mask.sum()), len(runs), written, args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
