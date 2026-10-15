"""Is a cel shadow a multiply, a subtraction, or a desaturation -- and by how much?

**Why the first attempt was not good enough.** It took the lightest flat colour in each hue bucket and called anything
between 55 and 98 per cent of its value a shadow of it. **Two unrelated colours that happen to share a hue satisfy
that**, so the pairs were contaminated and the distribution it produced was of contaminated pairs. The number was
plausible; the criterion behind it was not.

**What replaces it is a criterion the hypothesis has to pass.** If a shadow is the lit colour multiplied by a constant,
then the ratios of the three channels are **all equal to that constant**:

    (r2/r1, g2/g1, b2/b1) ~ (k, k, k)

That is a much narrower thing to satisfy than "same hue, darker", and it is falsifiable: a subtraction gives ratios
that differ per channel, a desaturation moves the channels toward their mean, and both fail it. **So this measures the
three hypotheses against each other rather than assuming one and reporting its constant.**

    python cel_shadow_measure.py --limit 60
"""
import argparse
import collections
import json
import pathlib
import statistics
import sys

from PIL import Image

CORPUS = pathlib.Path(r'E:\DaShaoHuo\downloads\pixiv-cel')
OUT = pathlib.Path(r'E:\DaShaoHuo\cache\tmp\cel-shadow.json')


def dominant_colours(path, top=64, sample=4):
    """The flat regions of a drawing, as (share, rgb), quantised to a 16-step grid per channel."""
    with Image.open(path) as im:
        im = im.convert('RGB')
        im = im.resize((max(1, im.width // sample), max(1, im.height // sample)), Image.NEAREST)
        counts = collections.Counter()
        for px in im.getdata():
            counts[(px[0] // 16 * 16 + 8, px[1] // 16 * 16 + 8, px[2] // 16 * 16 + 8)] += 1
    total = im.width * im.height
    return [(n / total, c) for c, n in counts.most_common(top)]


def adjacency(path, colours, sample=4):
    """Which of a drawing's flat colours actually touch each other.

    **The criterion the first two attempts were missing, and without it none of the numbers mean anything.** Both of
    them compared every flat colour with every other one and asked whether the arithmetic between them looked like a
    shadow. It does -- for colours that have nothing to do with each other. Printed out, the pairs that were being
    counted as shadows included `(216,216,216) -> (56,56,56)` between one area covering 39 per cent of the canvas and
    another covering 5.6, and `(56,72,104) -> (40,56,88)`, which differ by exactly sixteen in all three channels and
    are therefore a textbook subtraction and are also quite possibly two different materials.

    **A shadow touches the thing it shades**, and that is a property of the picture rather than of the colours. So a
    pair is only a candidate when the two regions share a boundary in the drawing, which is measured here by looking
    at neighbouring pixels and recording which quantised colours meet.
    """
    with Image.open(path) as im:
        im = im.convert('RGB')
        im = im.resize((max(1, im.width // sample), max(1, im.height // sample)), Image.NEAREST)
        w, h = im.size
        data = list(im.getdata())
    wanted = {c for c in colours}
    touches = set()
    for y in range(h):
        row = y * w
        for x in range(w):
            a = data[row + x]
            if x + 1 < w:
                b = data[row + x + 1]
                if a != b:
                    ka = (a[0] // 16 * 16 + 8, a[1] // 16 * 16 + 8, a[2] // 16 * 16 + 8)
                    kb = (b[0] // 16 * 16 + 8, b[1] // 16 * 16 + 8, b[2] // 16 * 16 + 8)
                    if ka in wanted and kb in wanted:
                        touches.add((ka, kb))
                        touches.add((kb, ka))
            if y + 1 < h:
                b = data[row + w + x]
                if a != b:
                    ka = (a[0] // 16 * 16 + 8, a[1] // 16 * 16 + 8, a[2] // 16 * 16 + 8)
                    kb = (b[0] // 16 * 16 + 8, b[1] // 16 * 16 + 8, b[2] // 16 * 16 + 8)
                    if ka in wanted and kb in wanted:
                        touches.add((ka, kb))
                        touches.add((kb, ka))
    return touches


def classify(a, b):
    """What relationship does b bear to a? Returns (kind, strength) or None.

    **The tolerances are the experiment.** A multiply is accepted when the three per-channel ratios agree to within
    0.06 of each other and the constant is below 0.97; the disagreement allowed is what a 16-step quantisation can
    introduce, and no more. A subtraction is accepted when the three differences agree that closely instead. A
    desaturation is accepted when b is a move of a toward its own greyscale by a consistent fraction. **Anything that
    fits none of them is reported as such rather than forced into the nearest one.**
    """
    r1, g1, b1 = a
    r2, g2, b2 = b
    if min(a) < 24 or max(a) > 248:
        return None

    ratios = [r2 / r1, g2 / g1, b2 / b1]
    k = statistics.median(ratios)
    if 0.35 < k < 0.97 and max(ratios) - min(ratios) < 0.06:
        return ('multiply', k)

    diffs = [r2 - r1, g2 - g1, b2 - b1]
    d = statistics.median(diffs)
    if -200 < d < -12 and max(diffs) - min(diffs) < 12:
        return ('subtract', d / 255.0)

    grey = sum(a) / 3.0
    if grey > 30:
        t = (sum(b) - sum(a)) / 3.0 / (grey - sum(a) / 3.0) if grey != sum(a) / 3.0 else None
        # toward grey: b = a + t*(grey - a); solve t per channel and require agreement
        ts = []
        for c1, c2 in zip(a, b):
            denom = grey - c1
            if abs(denom) > 8:
                ts.append((c2 - c1) / denom)
        if len(ts) == 3 and 0.05 < statistics.median(ts) < 0.95 and max(ts) - min(ts) < 0.12:
            return ('desaturate', statistics.median(ts))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--min-share', type=float, default=0.004)
    args = ap.parse_args()

    files = sorted(CORPUS.glob('*.jpg'))
    if args.limit:
        files = files[:args.limit]
    print('  %d images' % len(files))

    kinds = collections.Counter()
    strengths = collections.defaultdict(list)
    per_image = []
    for i, f in enumerate(files, 1):
        try:
            cols = [(s, c) for s, c in dominant_colours(f) if s >= args.min_share]
        except Exception as exc:
            print('    %s: %s' % (f.name, str(exc)[:50]))
            continue
        found = 0
        # **only colours that meet.** Every pair is still tested against the three hypotheses, but the candidate set
        # is now the touching pairs rather than all of them -- which is what makes the result about shadows instead of
        # about arithmetic.
        colours = [c for _, c in cols]
        touching = adjacency(f, colours)
        for share_a, a in cols:
            for share_b, b in cols:
                if a == b or (a, b) not in touching:
                    continue
                got = classify(a, b)
                if got:
                    kinds[got[0]] += 1
                    strengths[got[0]].append(got[1])
                    found += 1
        per_image.append(found)
        if i % 25 == 0:
            print('    %4d/%d  pairs %d  %s' % (i, len(files), sum(kinds.values()), dict(kinds)), flush=True)

    print()
    total = sum(kinds.values()) or 1
    print('  %d pairs over %d images' % (total, len(per_image)))
    print('  %-12s %8s %8s' % ('relationship', 'pairs', 'share'))
    for kind, n in kinds.most_common():
        print('  %-12s %8d %7.1f%%' % (kind, n, 100.0 * n / total))
    print()
    for kind in kinds:
        vals = sorted(strengths[kind])
        n = len(vals)
        if not n:
            continue
        if kind == 'multiply':
            print('  multiply constant: p05 %.3f  p25 %.3f  median %.3f  p75 %.3f  p95 %.3f'
                  % (vals[int(0.05 * (n - 1))], vals[int(0.25 * (n - 1))], vals[n // 2],
                     vals[int(0.75 * (n - 1))], vals[int(0.95 * (n - 1))]))
        elif kind == 'subtract':
            print('  subtract amount  : p05 %.3f  p25 %.3f  median %.3f  p75 %.3f  p95 %.3f  (of full scale)'
                  % (vals[int(0.05 * (n - 1))], vals[int(0.25 * (n - 1))], vals[n // 2],
                     vals[int(0.75 * (n - 1))], vals[int(0.95 * (n - 1))]))
        else:
            print('  desaturate t     : p05 %.3f  p25 %.3f  median %.3f  p75 %.3f  p95 %.3f'
                  % (vals[int(0.05 * (n - 1))], vals[int(0.25 * (n - 1))], vals[n // 2],
                     vals[int(0.75 * (n - 1))], vals[int(0.95 * (n - 1))]))

    print()
    print('  cel.py computes a multiply:  factor = 1 - 0.45 * (1/10) * 5 = %.3f' % (1.0 - 0.45 * 0.1 * 5.0))
    mult = sorted(strengths['multiply'])
    if mult:
        n = len(mult)
        below = sum(1 for v in mult if v <= 1.0 - 0.45 * 0.1 * 5.0)
        print('  fraction of real multiplies at or below that: %.1f%%' % (100.0 * below / n))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({k: {'n': len(v), 'median': statistics.median(v)} for k, v in strengths.items()}),
                   encoding='utf-8')
    print('  summary written to %s' % OUT)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
