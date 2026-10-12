"""Where the blobs actually are, measured in two dimensions rather than along a line.

**Why the shape of the measurement changed.** Every attempt so far sampled the alpha **along a line** -- the chord
between a bone's endpoints, then its own centreline -- and treated whatever it found as the stroke's profile. That
assumes the pattern is a one-dimensional phenomenon lying along the stroke, and **that assumption was never checked**:
a pattern that is periodic *across* the stroke, or that consists of local maxima scattered in two dimensions, would
look like a noisy profile to a line sampler and like scallops to an eye.

So this finds the local maxima of alpha **inside the stroke's own pixels** and reports the distance to each one's
nearest neighbour. A deposition pattern has one answer -- the dab spacing -- and anything else is something else.

    python blobs_2d.py
"""
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, r'E:\lineweight')

from lineweight import core, raster

DRAWING = pathlib.Path(r'E:\DaShaoHuo\cache\first-drawing.json')


def local_maxima(layer, threshold=8, radius=3):
    """Every pixel whose alpha is the largest within `radius`, and above `threshold`."""
    w, h = layer.width, layer.height
    data = layer.data
    alpha = [[data[(y * w + x) * 4 + 3] for x in range(w)] for y in range(h)]
    out = []
    for y in range(radius, h - radius):
        row = alpha[y]
        for x in range(radius, w - radius):
            v = row[x]
            if v < threshold:
                continue
            best = True
            for dy in range(-radius, radius + 1):
                arow = alpha[y + dy]
                for dx in range(-radius, radius + 1):
                    if (dx or dy) and arow[x + dx] > v:
                        best = False
                        break
                if not best:
                    break
            if best:
                out.append((x, y, v))
    return out


def main():
    d = json.loads(DRAWING.read_text(encoding='utf-8'))
    arm = next(m for m in d['marks'] if m['layer'] == 'arm' and m['kind'] == 'stroke'
               and len(m['geometry'].get('width_profile') or []) > 0)
    g = arm['geometry']
    rec = {'brush': g['brush'], 'centre': g['centre'], 'pressure': g['pressure'], 'seed': g.get('seed', 0),
           'width_profile': g['width_profile'], 'alpha_profile': [], 'colour_int': (26, 22, 32)}

    for label, dens in (('maximum (accumulate=False)', False), ('density (ratio of sums)', True)):
        layer = raster.stroke_layer(rec, 800, 600, 1.0, density=dens)
        pts = local_maxima(layer)
        print('=== %s' % label)
        print('    local maxima with alpha > 8: %d' % len(pts))
        if len(pts) < 3:
            print()
            continue
        # nearest-neighbour distance between maxima
        nn = []
        for i, (x, y, _) in enumerate(pts):
            best = min(math.hypot(x - px, y - py) for j, (px, py, _) in enumerate(pts) if j != i)
            nn.append(best)
        nn.sort()
        print('    nearest-neighbour distance: median %.1f  p25 %.1f  p75 %.1f  min %.1f  max %.1f'
              % (statistics.median(nn), nn[len(nn) // 4], nn[3 * len(nn) // 4], nn[0], nn[-1]))
        # and the dab spacing the renderer used
        b = core.BRUSHES[g['brush']]
        rad = max(g['width_profile']) / 2
        print('    the dab spacing the renderer used: %.1f px  (radius %.1f x 2 x spacing %.2f)'
              % (max(1.0, rad * 2 * b.get('spacing', 0.7)), rad, b.get('spacing', 0.7)))
        print('    alpha at the maxima: median %.0f  min %.0f  max %.0f'
              % (statistics.median(p[2] for p in pts), min(p[2] for p in pts), max(p[2] for p in pts)))
        print()


if __name__ == '__main__':
    main()
