"""Measure the swell of one stroke along its own path, without a skeleton.

**Why the earlier attempt failed and what is different.** `joint_width.py` took the width across a stroke by walking
outward until it met something brighter -- and it walked into neighbouring strokes and into the soft edge of the fill,
so a forearm asked to be 9.5 pixels wide reported 28. The search had no idea which ink belonged to the stroke.

**It has one now**: the width the renderer was told to lay down. Searching outward from a sample stops at whichever
comes first, a brighter pixel or **the requested half-width times a margin**, and then the measurement can only ever
report the stroke's own edge. That is not a skeleton either -- it is the same perpendicular sample, given a leash.

**What it answers**: whether the pen lays down the width it is asked for, and whether that width swells and narrows
along the stroke the way a drawn one does. Those are two different questions and the table keeps them apart -- a pen
that is uniformly wrong is a scale problem, and a pen that is right on average and wrong in places is a dynamics
problem.

    python stroke_swell.py
    python stroke_swell.py --path E:/DaShaoHuo/cache/tmp/practice.png
"""
import argparse
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, r'E:\lineweight')
import numpy as np
from PIL import Image

TMP = pathlib.Path(r'E:\DaShaoHuo\cache\tmp')
PRACTICE = TMP / 'practice.json'


def width_along(lum, centre, profile, threshold=200, margin=1.35, limit=40):
    """The ink width across the stroke at each sample, leashed to the width that was asked for.

    **The leash is what makes this a measurement of one stroke.** Without it the search walks into whatever else is
    near; with it, a sample can report at most `margin` times its own requested half-width and the reading belongs to
    the stroke it was taken from.
    """
    out = []
    n = len(centre)
    for i in range(1, n - 1):
        x0, y0 = centre[i - 1]
        x1, y1 = centre[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        want = profile[min(len(profile) - 1, int(i * len(profile) / float(n)))]
        leash = max(2, int(math.ceil(margin * want * 0.5)))
        total = 0
        for direction in (1, -1):
            for step in range(1, min(limit, leash) + 1):
                x = int(round(centre[i][0] + nx * step * direction))
                y = int(round(centre[i][1] + ny * step * direction))
                if not (0 <= x < lum.shape[1] and 0 <= y < lum.shape[0]):
                    break
                if lum[y, x] >= threshold:
                    break
                total += 1
        out.append((i / float(n - 1), total + 1, want))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--path', default=str(PRACTICE))
    ap.add_argument('--png', default=str(TMP / 'practice.png'))
    args = ap.parse_args()

    d = json.loads(pathlib.Path(args.path).read_text(encoding='utf-8'))
    lum = np.array(Image.open(args.png).convert('L'))

    print('  %-10s %8s %8s %8s %10s %10s' % ('stroke', 'med laid', 'med want', 'ratio', 'swell', 'flatness'))
    for m in d.get('marks', []):
        if m.get('kind') != 'stroke':
            continue
        note = (m.get('provenance', {}).get('note') or '?')
        g = m['geometry']
        centre = [tuple(p) for p in g['centre']]
        prof = list(g.get('width_profile') or [])
        if len(prof) < 3 or len(centre) < 5:
            continue
        rows = width_along(lum, centre, prof)
        if not rows:
            continue
        laid = [r[1] for r in rows]
        want = [r[2] for r in rows]
        # **`swell` is the ratio of the widest tenth to the narrowest tenth along the stroke**, which is the number
        # that says whether a line breathes. `flatness` is the fraction of samples within a pixel of the median, and a
        # line that is flat everywhere is a computer's line even when its average width is right.
        laid.sort()
        k = max(1, len(laid) // 10)
        swell = laid[-k:][0] / max(1e-9, laid[:k][-1])
        med = statistics.median(laid)
        flat = sum(1 for w in laid if abs(w - med) <= 1) / float(len(laid))
        print('  %-10s %8.1f %8.1f %8.2f %10.2f %10.2f' % (
            note.replace('practice ', '')[:10], med, statistics.median(want),
            med / max(1e-9, statistics.median(want)), swell, flat))
    print()
    print('  ** ratio near one means the pen lays down what it is told; far from one is a scale problem. **')
    print('  ** swell near one with high flatness is a line that does not breathe -- and that is the one thing about a')
    print('     pen that geometry cannot supply, because a shape has no opinion about pressure. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
