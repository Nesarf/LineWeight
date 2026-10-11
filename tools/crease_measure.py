"""Does a stroke that curves back on itself crease where its two feathered edges meet?

**The question comes from Compositor's brush note, and it describes the step after the one this library took.** Both
projects began with per-dab accumulation, where spacing was silently a darkness parameter. Compositor fixed that with
the maximum falloff -- and then recorded what the maximum does next:

    The initial continuous-tip implementation took the maximum falloff at each pixel. That removed stamp ridges, but
    the meeting point of two feathered edges formed a sharp crease. Soft tips now integrate optical density along
    each curve segment, then convert the accumulated density to coverage.

`raster.stroke_layer` here does that first thing: `accumulate=False` on the wet dabs, so a pixel takes the maximum of
the dabs covering it. **So the question is whether this library has the crease as well**, and it is asked by
measurement rather than by adopting someone else's answer.

**The shape that exposes it is a hairpin**, drawn close enough to itself that the two arms' feathered edges overlap
across the gap. Under a maximum those two profiles meet at `max(a, b)`, which has a corner at the meeting; under an
integration they meet as a sum, which does not. **Everything depends on the edges actually overlapping**, so the
parameters are chosen for that and the run says so when they do not -- a gap measured where nothing meets is a
measurement of nothing.

    python crease_measure.py
"""
import math
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, raster

CANVAS = 260


def hairpin(cx, cy, arm, reach):
    """A U in canvas pixels: down one arm, round the turn, up the other, `2 * arm` apart."""
    pts = []
    top = cy - reach
    turn = cy + reach * 0.5
    for i in range(20):
        t = i / 19.0
        pts.append((cx - arm, top + (turn - top) * t))
    for i in range(1, 13):
        a = math.pi * i / 12.0
        pts.append((cx - arm * math.cos(a), turn + arm * math.sin(a)))
    for i in range(19):
        t = i / 18.0
        pts.append((cx + arm, (turn + arm) - ((turn + arm) - top) * t))
    return pts


def profile(layer, y, x0, x1):
    row = int(y) * layer.width * 4
    return [layer.data[row + x * 4 + 3] / 255.0 for x in range(int(x0), int(x1))]


def kink(values):
    """How much the gradient jumps, as a multiple of its typical step. Near 1 is smooth."""
    d = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    steps = sorted(abs(x) for x in d if abs(x) > 1e-9)
    if len(d) < 3 or not steps:
        return 0.0
    typical = steps[len(steps) // 2]
    return max(abs(d[i + 1] - d[i]) for i in range(len(d) - 1)) / typical if typical else 0.0


def one(brush, arm):
    width = core.BRUSHES[brush]['width']
    cx, cy = CANVAS / 2, CANVAS / 2 - 10
    record = core.stroke_record(hairpin(cx, cy, arm, 70.0), brush, seed=7, resolution=24)
    layer = raster.stroke_layer(record, CANVAS, CANVAS, scale=1.0)
    cover = sum(1 for i in range(0, CANVAS * CANVAS * 4, 4) if layer.data[i + 3])

    print()
    print('=== %s brush (diameter %.0f px), arms %g px apart' % (brush, width, 2 * arm))
    print('    coverage: %d px' % cover)
    if 2 * arm >= width:
        print('    the arms are further apart than the brush is wide, so the edges cannot meet:')
        print('    this run cannot show a crease either way')
        return None

    # **The probe window is taken from the coverage, not from a fraction of a fixed span.** The first version
    # sampled `cx - 60 .. cx + 60` and then took the middle half of that, which is 120 pixels wide -- wider than the
    # stroke -- so the minimum landed on the empty paper outside it and every configuration reported "nothing
    # overlaps" while the coverage map showed the arms overlapping all along.
    rows = []
    for y in range(int(cy - 55), int(cy + 30), 2):
        full = profile(layer, y, 0, CANVAS)
        covered = [i for i, v in enumerate(full) if v > 0.003]
        if len(covered) < 8:
            continue
        lo, hi = covered[0], covered[-1]
        span = full[lo:hi + 1]
        # drop a quarter from each end, so the arms' own outer fall-off is not what is being minimised
        trim = max(1, len(span) // 4)
        gap = span[trim:len(span) - trim]
        if len(gap) < 3:
            continue
        rows.append((y, min(gap), kink(gap), lo, hi))
    if not rows:
        print('    no profile along the probe line')
        return None
    mins = [r[1] for r in rows]
    # **The largest minimum is the interesting one**: the crease is deepest where the arms are closest, so a row
    # whose gap minimum is near zero is a row where they had not yet met.
    meet = [r for r in rows if r[1] > 0.01]
    print('    minimum coverage in the gap: median %.4f, largest %.4f' % (sorted(mins)[len(mins) // 2], max(mins)))
    if not meet:
        print('    nothing overlaps in the gap, so no crease can be measured here')
        return None
    print('    %-6s %-9s %-8s %-12s %s' % ('y', 'min', 'kink', 'covered span', ''))
    for y, m, k, lo, hi in meet:
        print('    %-6d %-9.4f %-8.2f %-12s %s' % (y, m, k, '%d..%d' % (lo, hi), 'corner' if k > 2.0 else ''))
    worst = max(k for _, _, k, _, _ in meet)
    print('    where the edges meet, the gradient jumps by up to %.2f x its typical step' % worst)
    return worst


def main():
    print('A crease shows as a corner in the coverage across the gap between a hairpin\'s own two arms.')
    print('Near 1.0 is smooth; a lurch means two feathered edges met at their maximum.')
    results = []
    for brush, arm in (('wash', 5.0), ('wash', 8.0), ('wash', 11.0), ('ink', 3.0), ('pencil', 4.0)):
        r = one(brush, arm)
        if r is not None:
            results.append((brush, arm, r))
    print()
    print('=== what the measurements say')
    if not results:
        print('  no configuration got the two edges to overlap, so this instrument measured nothing yet.')
    for brush, arm, k in results:
        verdict = 'smooth' if k <= 2.0 else 'a corner'
        print('  %-8s arm %-5g  kink %6.2f  ->  %s' % (brush, arm, k, verdict))


if __name__ == '__main__':
    main()
