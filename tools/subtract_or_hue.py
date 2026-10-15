"""Is the 32 per cent called "subtract" a subtraction, or is it a hue shift wearing the name?

**Two explanations, and they make opposite predictions.** Of 13,808 adjacent light/dark pairs, 67.6 per cent satisfy a
multiply and 32.2 per cent satisfy a subtraction -- equal differences across the three channels. Two things could
produce the second group:

  * **A dark base.** A multiply by 0.74 on a colour at value 0.2 moves it by very little in absolute terms, so an
    artist working on dark material might darken by a fixed amount instead. If this is the explanation, the subtract
    pairs have **darker lit colours** than the multiply pairs.
  * **A hue shift.** A shadow that changes hue as well as value fails the ratio test -- the three channel ratios come
    out unequal -- while its differences may still be close enough to pass. If this is the explanation, the subtract
    pairs have a **larger hue difference** between the two colours, and "subtract" is a misnomer for something else.

Both are measured here from the same pairs, so the two predictions are set against each other rather than one being
assumed. **A third outcome is possible and would be the honest one if it happens: neither separates them, and the
group is a mixture.**

    python subtract_or_hue.py [--limit 120]
"""
import argparse
import collections
import colorsys
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import importlib.util

spec = importlib.util.spec_from_file_location('cel_m', str(pathlib.Path(__file__).parent / 'cel_shadow_measure.py'))
cel_m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cel_m)


def value_of(rgb):
    return colorsys.rgb_to_hsv(*[c / 255.0 for c in rgb])[2]


def hue_gap(a, b):
    """Difference in hue in degrees, folded to 0..180."""
    ha = colorsys.rgb_to_hsv(*[c / 255.0 for c in a])[0] * 360.0
    hb = colorsys.rgb_to_hsv(*[c / 255.0 for c in b])[0] * 360.0
    d = abs(ha - hb) % 360.0
    return min(d, 360.0 - d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    files = sorted(cel_m.CORPUS.glob('*.jpg'))
    if args.limit:
        files = files[:args.limit]
    print('  %d images' % len(files))

    groups = collections.defaultdict(lambda: {'value': [], 'hue': [], 'sat': []})
    for i, f in enumerate(files, 1):
        try:
            cols = [(s, c) for s, c in cel_m.dominant_colours(f) if s >= 0.004]
        except Exception:
            continue
        touching = cel_m.adjacency(f, [c for _, c in cols])
        for _, a in cols:
            for _, b in cols:
                if a == b or (a, b) not in touching:
                    continue
                got = cel_m.classify(a, b)
                if not got:
                    continue
                kind = got[0]
                groups[kind]['value'].append(value_of(a))
                groups[kind]['hue'].append(hue_gap(a, b))
                groups[kind]['sat'].append(colorsys.rgb_to_hsv(*[c / 255.0 for c in a])[1])
        if i % 40 == 0:
            print('    %4d/%d  %s' % (i, len(files), {k: len(v['value']) for k, v in groups.items()}), flush=True)

    print()
    print('  %-12s %8s %26s %26s %10s' % ('kind', 'pairs', 'lit value (p25/med/p75)',
                                          'hue gap deg (p25/med/p75)', 'sat median'))
    for kind in ('multiply', 'subtract', 'desaturate'):
        g = groups.get(kind)
        if not g or not g['value']:
            continue
        v = sorted(g['value']); h = sorted(g['hue']); s = sorted(g['sat'])
        n = len(v)
        def q(xs, p): return xs[int(p * (len(xs) - 1))]
        print('  %-12s %8d %10.3f %6.3f %6.3f %12.1f %5.1f %5.1f %10.3f'
              % (kind, n, q(v, .25), q(v, .5), q(v, .75), q(h, .25), q(h, .5), q(h, .75), q(s, .5)))

    # **The saturation is the column that resolved it, and it resolved it against every guess made here.** A neutral
    # grey satisfies a multiply and a subtraction equally, so whichever the classifier tests first takes all of them;
    # the classification therefore splits on *saturation* rather than on what the artist did. Printed with the rest,
    # because a median of 0.080 next to a median of 0.286 is the whole finding and it was invisible until it was here.
    print()
    print('  share of each group that is neutral (saturation below 0.10):')
    for kind in ('multiply', 'subtract', 'desaturate'):
        g = groups.get(kind)
        if g and g['sat']:
            grey = sum(1 for x in g['sat'] if x < 0.10)
            print('    %-12s %5.1f%% of %d' % (kind, 100.0 * grey / len(g['sat']), len(g['sat'])))

    print()
    mult = groups.get('multiply'); sub = groups.get('subtract')
    if not mult or not sub:
        print('  one of the two groups is empty')
        return 0

    # **The two predictions, stated as numbers rather than as a verdict.**
    mv, sv = statistics.median(mult['value']), statistics.median(sub['value'])
    mh, sh = statistics.median(mult['hue']), statistics.median(sub['hue'])
    print('  A: a dark base  -> subtract pairs should have a DARKER lit colour')
    print('       multiply median value %.3f   subtract median value %.3f   difference %+.3f' % (mv, sv, sv - mv))
    print('  B: a hue shift  -> subtract pairs should have a LARGER hue gap')
    print('       multiply median gap  %.1f deg   subtract median gap  %.1f deg   difference %+.1f' % (mh, sh, sh - mh))
    print()
    # and how much of the two distributions overlap, because a median difference can be real and still not separate
    def overlap(xs, ys):
        xs, ys = sorted(xs), sorted(ys)
        lo, hi = min(xs[0], ys[0]), max(xs[-1], ys[-1])
        if hi == lo:
            return 1.0
        BINS = 24
        bx = collections.Counter(int((x - lo) / (hi - lo) * (BINS - 1)) for x in xs)
        by = collections.Counter(int((y - lo) / (hi - lo) * (BINS - 1)) for y in ys)
        shared = sum(min(bx[i], by[i]) for i in range(BINS))
        return shared / min(len(xs), len(ys))
    print('  how much the two groups overlap (1.0 would be indistinguishable):')
    print('    on lit value  %.2f' % overlap(mult['value'], sub['value']))
    print('    on hue gap    %.2f' % overlap(mult['hue'], sub['hue']))
    print()
    print('  ** a median that differs while the distributions sit on top of each other means the group is a mixture,')
    print('     not a category. That outcome is as much an answer as a clean separation. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
