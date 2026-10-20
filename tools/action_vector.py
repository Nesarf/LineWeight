"""How far a figure leans, and where: the geometry of "the moment before the action".

**Why this is a measurement and not a mood.** A drawing that predicts its next movement does it in a way the silhouette
can be asked about: **the body's centre line is not vertical**. One shoulder is higher, the hips are turned, the head is
past the feet -- and a figure standing square on both feet with everything above the pelvis in line reads as a statue,
which is the fault every book in the library names and none of them quantifies.

So this reads the figure's own mask and reports the centre line against the line through the feet:

    offset(y) = (centre of the figure at height y - centre of the feet) / height

**The feet are the anchor because they are what the figure stands on.** A body leaning past its feet is already falling
or already moving, and the size of that offset is the size of the prediction.

    python tools/action_vector.py --src "F:\\素材\\图\\16+\\illust_83038160.png"
"""
import argparse
import pathlib
import sys

sys.path.insert(0, r'E:\lineweight')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import quantise_trace as qt


def centre_profile(mask, w, h):
    """(height fraction, centre x, width) at every row the figure occupies."""
    rows = []
    for y in range(h):
        row = mask[y]
        try:
            lo = row.index(1)
        except ValueError:
            continue
        hi = w - 1 - row[::-1].index(1)
        rows.append((y, (lo + hi) / 2.0, hi - lo + 1))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--colours', type=int, default=12)
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    if not src.exists():
        print('  missing: %s' % src)
        return 1
    labels, w, h = qt.load_and_quantise(src, args.colours, 1000)
    regs = qt.regions(labels, w, h)
    mask, kept, before = qt.largest_component(qt.figure_mask(regs, w, h), w, h)
    if mask is None or not kept:
        print('  no figure found')
        return 1

    rows = centre_profile(mask, w, h)
    if len(rows) < 20:
        print('  the figure is too short to have a centre line')
        return 1
    top, bottom = rows[0][0], rows[-1][0]
    height = float(bottom - top + 1)

    # **The feet are the bottom eighth**, and their centre is taken from the mask's own extent there rather than from
    # the whole figure -- a figure standing on one foot leans by definition, and that is the point.
    foot_rows = [r for r in rows if (r[0] - top) / height > 0.92]
    foot_x = sum(r[1] for r in foot_rows) / float(len(foot_rows))

    print('  %s  figure %d px tall, %d px wide' % (src.name, int(height), kept and max(r[2] for r in rows)))
    print()
    print('    %-7s %8s %8s %8s' % ('height', 'centre', 'offset', 'width'))
    worst = 0.0
    worst_at = 0.0
    for frac in (0.05, 0.12, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.97):
        y = top + frac * height
        near = min(rows, key=lambda r: abs(r[0] - y))
        offset = (near[1] - foot_x) / height
        if abs(offset) > abs(worst):
            worst, worst_at = offset, frac
        print('    %-7.2f %8.1f %8.3f %8d' % (frac, near[1], offset, near[2]))
    print()
    print('  the centre line leans %.3f of the height, at %.0f%% up' % (worst, 100 * worst_at))
    print('  a figure that stands square would read 0.000 at every row')

    # **And the lean is only half of it.** A body that leaves the vertical on one side and comes back on the other is an
    # S, which is a figure in motion; a body that leaves it and stays is a figure falling.
    signs = []
    for r in rows:
        off = (r[1] - foot_x) / height
        if abs(off) > 0.01:
            signs.append(1 if off > 0 else -1)
    if signs:
        crossings = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
        print('  the centre line crosses its own foot line %d time(s) on the way up' % crossings)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
