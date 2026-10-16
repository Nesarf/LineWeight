"""Is the joint between two bones thinner than the bones themselves?

**The mechanism this tests, and it is a guess until measured.** The drawing is thirty-three separate strokes and the
ends of a parent and a child do coincide -- so the ink is continuous in position. **But each stroke carries its own
taper**: `stroke_record` runs the pressure model on every mark, and a mark that ends tapers out. So at a joint two
ended strokes meet, each thinned near its own end, and the join becomes the thinnest place in the limb.

**Which would explain both observations at once**: why the figure reads as marks laid near each other rather than as a
drawing, and why `taper_ratio` -- the thinnest fifth of the runs over their mean -- came out 25 per cent low without
any single line width being wrong.

**Measured across the stroke, not along it.** An earlier round established that a centreline stays smooth while the
boundary is where a defect shows, so the width here is taken perpendicular to the path at every sample.

    python joint_width.py
"""
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, r'E:\lineweight')
import numpy as np
from PIL import Image

PROJECT = pathlib.Path(r'E:\DaShaoHuo\cache\cel-drawing.json')
RENDER = pathlib.Path(r'E:\DaShaoHuo\cache\cel3.png')

#: A chain whose joints are interior: the upper arm meets the forearm at the elbow, and neither end is an extremity,
#: so a thinning at the join cannot be explained by a fingertip taper.
CHAIN = ('Bip001 L UpperArm', 'Bip001 L Forearm')


def load_strokes():
    d = json.loads(PROJECT.read_text(encoding='utf-8'))
    out = {}
    for m in d['marks']:
        if m.get('kind') != 'stroke':
            continue
        note = m.get('provenance', {}).get('note') or ''
        out[note.replace('bone ', '').strip()] = m['geometry']
    return out


def width_across(lum, ix, iy, nx, ny, threshold, limit=60):
    """Ink pixels along the perpendicular at a sample point, counted both ways from the centre.

    **By luminance and not by alpha.** The render is RGB with no transparency at all -- alpha is 255 everywhere and
    has a single distinct value -- so the first version counted to its own limit in both directions and reported 79
    for every sample, which is the limit rather than a measurement. **A check sitting where it belongs while examining
    something else**, which is the shape this work keeps meeting; this time it was caught by printing the channel
    being tested instead of trusting it.

    Two thresholds are reported. 128 matches `ref.measure`; 200 takes in the soft edge of a stroke. What is compared
    here is one place against another on the same drawing, so either serves, and both are printed so the choice is
    visible rather than buried.
    """
    total = 0
    for direction in (1, -1):
        for step in range(1, limit):
            x = int(round(ix + nx * step * direction))
            y = int(round(iy + ny * step * direction))
            if not (0 <= x < lum.shape[1] and 0 <= y < lum.shape[0]):
                break
            if lum[y, x] >= threshold:
                break
            total += 1
    return total + 1


def main():
    strokes = load_strokes()
    lum = np.array(Image.open(RENDER).convert('L'))

    for name in CHAIN:
        g = strokes.get(name)
        if not g:
            print('  no stroke named %r' % name)
            return 1
        pts = [tuple(p) for p in g['centre']]
        prof = list(g.get('width_profile') or [])
        if len(pts) < 3:
            continue
        samples = []
        for i in range(1, len(pts) - 1):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i + 1]
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L, dx / L
            w128 = width_across(lum, pts[i][0], pts[i][1], nx, ny, 128)
            w200 = width_across(lum, pts[i][0], pts[i][1], nx, ny, 200)
            t = i / (len(pts) - 1.0)
            nominal = prof[min(len(prof) - 1, i)] if prof else 0.0
            samples.append((t, w128, w200, nominal))

        print('  %s -- %d samples across the stroke' % (name, len(samples)))
        print('    %-9s %8s %8s %9s' % ('t along', 'px<128', 'px<200', 'nominal'))
        step = max(1, len(samples) // 9)
        for row in samples[::step] + [samples[-1]]:
            print('    %-9.2f %8d %8d %9.1f' % row)

        ends = [r[1] for r in samples if r[0] < 0.12 or r[0] > 0.88]
        mid = [r[1] for r in samples if 0.30 < r[0] < 0.70]
        if ends and mid:
            e, m = statistics.median(ends), statistics.median(mid)
            print('    ends median %d px against middle median %d px  ->  %+.0f%%' % (e, m, 100.0 * (e - m) / max(1, m)))
        # **And the nominal profile, which the renderer was given.** If the ink across the stroke tracks it, the
        # deposition is doing what it was asked; if the ink at the ends is thinner than the profile, the taper came
        # from the pressure model rather than from the width.
        nom_ends = [r[3] for r in samples if r[0] < 0.12 or r[0] > 0.88]
        nom_mid = [r[3] for r in samples if 0.30 < r[0] < 0.70]
        if nom_ends and nom_mid:
            ne, nm = statistics.median(nom_ends), statistics.median(nom_mid)
            print('    nominal ends %.1f against nominal middle %.1f  ->  %+.0f%%'
                  % (ne, nm, 100.0 * (ne - nm) / max(1e-9, nm)))
        print()

    print('  ** the two ends of a limb chain are joined to something else, and each stroke tapers at its own end.')
    print('     If the ends come out thinner than the middles -- beyond what the nominal profile asks for -- then')
    print('     the taper at a joint is the discontinuity, and joining the chain is the fix. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
