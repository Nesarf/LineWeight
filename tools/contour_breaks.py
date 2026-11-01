"""How many breaks a drawing's contours have, measured on the project itself.

`broken_contour` sits in `learn/errors.jsonl` with `check: none` behind it. The check is a count of stroke
ends that sit close together and belong to different marks: a contour that came out as one run has none of
those inside it, and a contour that came out as forty has thirty-nine.

**What the number is not.** Two different contours genuinely pass near each other -- a skirt beside a leg,
a finger beside the next -- so some of these pairs are not breaks at all. The count is therefore a ceiling on
the breaks, not an exact tally, and it is useful for comparing one drawing with another rather than for
reading off "this picture has N faults".

    python tools/contour_breaks.py cache/paint16/lines.json
"""

import argparse
import json
import math

import numpy as np


def endpoints(marks):
    """The two ends of every mark's centre line, one row per end, with the mark it belongs to."""
    rows, owner = [], []
    for index, mark in enumerate(marks):
        centre = mark.get('geometry', {}).get('centre') or []
        if len(centre) < 2:
            continue
        rows.append([centre[0][0], centre[0][1]])
        owner.append(index)
        rows.append([centre[-1][0], centre[-1][1]])
        owner.append(index)
    return np.asarray(rows, dtype=np.float64), np.asarray(owner, dtype=np.int32)


def run_lengths(marks):
    """Each mark's own length, in canvas pixels."""
    out = []
    for mark in marks:
        centre = mark.get('geometry', {}).get('centre') or []
        if len(centre) < 2:
            continue
        total = 0.0
        for a, b in zip(centre, centre[1:]):
            total += math.hypot(b[0] - a[0], b[1] - a[1])
        out.append(total)
    return np.asarray(out, dtype=np.float64)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('project', help='a project file with stroke marks')
    parser.add_argument('--reach', type=float, default=0.0035,
                        help='two ends closer than this share of the canvas long side are candidates')
    args = parser.parse_args()

    with open(args.project, encoding='utf-8') as handle:
        data = json.load(handle)
    marks = [m for m in data['marks'] if m.get('state') in (None, 'live')]
    canvas = data['canvas']
    long_side = float(max(canvas['width'], canvas['height']))
    limit = args.reach * long_side

    points, owner = endpoints(marks)
    runs = run_lengths(marks)
    print('  %d marks, %d ends, canvas long side %.0f, reach %.1f px'
          % (len(marks), len(points), long_side, limit))
    print('  run length   median %.1f px, p10 %.1f, p90 %.1f, longest %.1f'
          % (float(np.median(runs)), float(np.percentile(runs, 10)),
             float(np.percentile(runs, 90)), float(runs.max())))

    # **A grid, because the pairs are the product of two large numbers.** Every end against every other is
    # a hundred million comparisons on this drawing; checking only the nine neighbouring cells is a walk.
    cell = max(limit, 1.0)
    buckets = {}
    for i, (x, y) in enumerate(points):
        buckets.setdefault((int(x // cell), int(y // cell)), []).append(i)
    pairs = 0
    for i, (x, y) in enumerate(points):
        cx, cy = int(x // cell), int(y // cell)
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for j in buckets.get((cx + ox, cy + oy), ()):
                    if j <= i or owner[j] == owner[i]:
                        continue
                    if math.hypot(points[j][0] - x, points[j][1] - y) <= limit:
                        pairs += 1
    print('  ends of different marks within %.1f px: %d pairs, %.2f per mark'
          % (limit, pairs, pairs / max(1, len(marks))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
