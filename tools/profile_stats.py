"""Turn a volume profile -- or a rendered picture -- into the few numbers a body is actually judged by.

**Why features instead of sixty-four band rows.** A profile is a curve and two curves cannot be compared by eye once
there are five of them. What can be compared is where a curve reaches its widest, how wide its legs are, where the
waist pinches. **Four numbers per body, so a rule can be a median and not an opinion.**

**The same four are measured from a rendering**, by the same background row walk `silhouette_compare.py` uses, so the
drawing sits in the same table as the models.

    python tools/profile_stats.py --profile model/shape/Zome-body.json --profile model/shape/Cian_VRM-body.json --png out.png
"""
import argparse
import json
import pathlib
import statistics

from silhouette_compare import load_png_rows

#: The bands each feature is read from, as fractions of the figure's height above its feet. **Named rather than magic**:
#: a modelling change that moves one of these has to say which one it moved.
ARM_BAND = (0.66, 0.88)
LEG_BAND = (0.08, 0.25)
HIP_BAND = (0.38, 0.56)
WAIST_BAND = (0.58, 0.70)


def mean(values):
    return sum(values) / float(len(values)) if values else 0.0


def features(points):
    """points: [(height above the feet, width)] -- one row per band, any number of rows."""
    if not points:
        return None
    in_arm = [p for p in points if ARM_BAND[0] <= p[0] <= ARM_BAND[1]]
    in_leg = [p for p in points if LEG_BAND[0] <= p[0] <= LEG_BAND[1]]
    in_hip = [p for p in points if HIP_BAND[0] <= p[0] <= HIP_BAND[1]]
    in_waist = [p for p in points if WAIST_BAND[0] <= p[0] <= WAIST_BAND[1]]
    widest = max(points, key=lambda p: p[1])
    return {
        'widest at': widest[0],
        'widest': widest[1],
        'arm span': max([p[1] for p in in_arm]) if in_arm else 0.0,
        'legs': mean([p[1] for p in in_leg]),
        'hip': max([p[1] for p in in_hip]) if in_hip else 0.0,
        'waist': min([p[1] for p in in_waist]) if in_waist else 0.0,
    }


def from_profile(path):
    data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    return features([(r['y'], r['w']) for r in data['rows']]), pathlib.Path(path).name


def from_png(path):
    rows = load_png_rows(path)
    if len(rows) < 10:
        return None, pathlib.Path(path).name
    top, bottom = rows[0][0], rows[-1][0]
    height = float(bottom - top + 1)
    points = []
    step = max(1, int(height / 128))
    for i in range(0, int(height), step):
        y = bottom - i
        near = min(rows, key=lambda r: abs(r[0] - y))
        points.append((i / height, (near[2] - near[1] + 1) / height))
    return features(points), pathlib.Path(path).name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', action='append', default=[])
    ap.add_argument('--png', action='append', default=[])
    args = ap.parse_args()

    table = []
    for p in args.profile:
        f, name = from_profile(p)
        if f:
            table.append((name, f))
    for p in args.png:
        f, name = from_png(p)
        if f:
            table.append((name, f))

    keys = ['widest at', 'widest', 'arm span', 'legs', 'hip', 'waist']
    print('  %-26s %s' % ('', '  '.join('%8s' % k for k in keys)))
    for name, f in table:
        print('  %-26s %s' % (name[:26], '  '.join('%8.3f' % f[k] for k in keys)))

    models = [f for name, f in table if not name.endswith('.png')]
    if len(models) >= 2:
        print()
        print('  median over %d models:' % len(models))
        print('    %s' % '  '.join('%s %.3f' % (k, statistics.median([m[k] for m in models])) for k in keys))
    drawn = [f for name, f in table if name.endswith('.png')]
    if drawn and models:
        print()
        print('  the drawing against the median:')
        for k in keys:
            m = statistics.median([m[k] for m in models])
            print('    %-10s model %6.3f   drawn %6.3f   difference %+.3f' % (k, m, drawn[0][k], drawn[0][k] - m))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
