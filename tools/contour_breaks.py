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
    """The two ends of every mark's centre line, one row per end, with the mark and the outward direction.

    **The outward direction is what separates a break from an occlusion.** Two runs whose ends meet and whose outward
    directions agree are one line cut in two, which is what a join repairs. Two whose outward directions face each other
    are head to head: either one line behind something, or two lines meeting, and the pair cannot tell those apart.
    """
    rows, owner, heading = [], [], []
    for index, mark in enumerate(marks):
        centre = mark.get('geometry', {}).get('centre') or []
        if len(centre) < 2:
            continue
        rows.append([centre[0][0], centre[0][1]])
        owner.append(index)
        heading.append((centre[0][0] - centre[1][0], centre[0][1] - centre[1][1]))
        rows.append([centre[-1][0], centre[-1][1]])
        owner.append(index)
        heading.append((centre[-1][0] - centre[-2][0], centre[-1][1] - centre[-2][1]))
    return (np.asarray(rows, dtype=np.float64), np.asarray(owner, dtype=np.int32), heading)


def run_lengths(marks):
    """Each mark's own length in canvas pixels, with the mark it belongs to."""
    out, owner = [], []
    for index, mark in enumerate(marks):
        centre = mark.get('geometry', {}).get('centre') or []
        if len(centre) < 2:
            continue
        total = 0.0
        for a, b in zip(centre, centre[1:]):
            total += math.hypot(b[0] - a[0], b[1] - a[1])
        out.append(total)
        owner.append(index)
    return np.asarray(out, dtype=np.float64), np.asarray(owner, dtype=np.int32)


def all_points(marks):
    """Every centre-line control point, with the mark it belongs to.

    **The control points, not the pixel chain.** A simplification leaves them a few pixels apart, and the question
    asked of them -- is another run anywhere near this end -- is answered at the scale of a reach, which is larger.
    """
    rows, owner = [], []
    for index, mark in enumerate(marks):
        for point in mark.get('geometry', {}).get('centre') or []:
            rows.append((point[0], point[1]))
            owner.append(index)
    return np.asarray(rows, dtype=np.float64), np.asarray(owner, dtype=np.int32)


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

    points, owner, heading = endpoints(marks)
    runs, run_owner = run_lengths(marks)
    length_by_mark = {int(run_owner[k]): float(runs[k]) for k in range(len(runs))}
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
    agreeing = 0
    facing = 0
    agree_distances = []
    for i, (x, y) in enumerate(points):
        cx, cy = int(x // cell), int(y // cell)
        ax, ay = heading[i]
        span_a = math.hypot(ax, ay)
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for j in buckets.get((cx + ox, cy + oy), ()):
                    if j <= i or owner[j] == owner[i]:
                        continue
                    span = math.hypot(points[j][0] - x, points[j][1] - y)
                    if span > limit:
                        continue
                    pairs += 1
                    if span_a == 0.0:
                        continue
                    bx, by = heading[j]
                    span_b = math.hypot(bx, by)
                    if span_b == 0.0:
                        continue
                    cosine = (ax * bx + ay * by) / (span_a * span_b)
                    if cosine >= 0.5:
                        agreeing += 1
                        agree_distances.append(span)
                    elif cosine <= -0.5:
                        facing += 1
    print('  ends of different marks within %.1f px: %d pairs, %.2f per mark'
          % (limit, pairs, pairs / max(1, len(marks))))
    # **Two ends that meet are not one thing.** Agreeing directions mean one line cut in two, which is what a join
    # repairs. Facing directions mean head to head: one line behind something, or two lines meeting, and this pair of
    # ends cannot tell those apart. So the two columns are different questions and neither is a count of faults.
    print('    outward directions agree: %d   face each other: %d   neither: %d'
          % (agreeing, facing, pairs - agreeing - facing))
    # **How far apart the ones a join should take still are.** "Just outside the reach" and "nowhere near it" are
    # different problems, and only the first gets better by widening a threshold. Measured on the joined project, the
    # distribution says which one this is.
    if agree_distances:
        spread = np.asarray(agree_distances)
        print('    agreeing pairs lie %.1f px apart at the median, %.1f at p90, %.1f at most (reach %.1f)'
              % (float(np.median(spread)), float(np.percentile(spread, 90)), float(spread.max()), limit))

    # **An end with no other run anywhere near it.** The row `floating_contact` describes a hair tip that stops by fading
    # into water: nothing in the line layer marks where it ends. That end is isolated -- no other mark passes within the
    # reach of it -- while an ordinary taper ends beside whatever it was drawn against. A short run finishing in open
    # space is the first case, a long one is the row's, so the two are counted apart.
    every, every_owner = all_points(marks)
    grid = {}
    for k, (x, y) in enumerate(every):
        grid.setdefault((int(x // cell), int(y // cell)), []).append(k)
    median_run = float(np.median(runs)) if len(runs) else 0.0
    isolated = 0
    isolated_long = 0
    for i, (x, y) in enumerate(points):
        cx, cy = int(x // cell), int(y // cell)
        found = False
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for k in grid.get((cx + ox, cy + oy), ()):
                    if every_owner[k] == owner[i]:
                        continue
                    if math.hypot(every[k][0] - x, every[k][1] - y) <= limit:
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if not found:
            isolated += 1
            if length_by_mark.get(int(owner[i]), 0.0) > median_run:
                isolated_long += 1
    print('    ends with no other run within reach: %d of %d (%.1f%%), %d on a run longer than the median'
          % (isolated, len(points), 100.0 * isolated / max(1, len(points)), isolated_long))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
