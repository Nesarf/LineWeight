"""An apple, painted from nothing: the first picture here that was not traced.

**An example, not a tool.** Nothing is copied in it -- no reference, no measurement, no acceptance row that could pass
or fail it. A light direction, a colour ladder, and a few thousand marks; every decision belongs to the caller. It sits
in `tools/` because the shapes it exercises (`soft` sections, pigment that changes colour inside one mark, and
thickness read by `raster.light`) are the ones a painting pipeline needs and a line-art pipeline never did.

Four passes got here. The first three were a rasteriser wearing a brush's clothes: build a silhouette, evaluate a
lighting formula, fill it with a gradient sampled per pixel. What changed -- and each change was visible, which is why
it was kept:

* **An apple is a walk of marks, not a formula.** No rows, no per-pixel shading: points scattered over the fruit, sorted
  from dark to light and laid down in that order, each one turned along the surface it sits on.
* **Oil has no line layer.** The stem was drawn with a pencil brush in the first pass; now it is a few small dark marks,
  the same kind of mark as everything else.
* **A gloss is thick paint, not a glow.** Small, blunt, opaque, same brush as the body.
* **Five steps, not a gradient.** A painter mixes a handful of tones and lets the eye read the boundary as the turn of
  the form; mixing continuously gives a sphere that is smoothly shaded and flat.
* **The edge is the last mark's edge.** A mask was tried and removed: it made a vector boundary. Three later attempts to
  correct the rim by painting over it each read as a ring, so the edge is left as the marks leave it.

**Cold into the darks and heat into the lights**, which is the other thing a mixed palette gives you for free: the
shadow side of a red apple goes towards violet, the last of the light towards orange, and a whisper of reflected light
along the lower rim is cooler than either. Kept quiet -- a reflected light that outweighs the fruit's own red stops
reading as reflected light and starts reading as a blue apple.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineweight import core, project          # noqa: E402
from lineweight import raster as r            # noqa: E402

W, H = 1100, 1100
# **The output goes beside the caller, not beside the author.** This script was written inside a scratch directory and
# read the author's own tree back; a tool in the repository cannot assume either, so the destination is the working
# directory unless the caller says otherwise.
OUT = os.environ.get('APPLE_OUT') or os.path.join(os.getcwd(), 'apple')
LIGHT = (-0.46, -0.54, 0.70)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def hexed(colour):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in colour)


def jitter(colour, amount, rng):
    return (colour[0] + rng.uniform(-amount, amount),
            colour[1] + rng.uniform(-amount * 0.85, amount * 0.85),
            colour[2] + rng.uniform(-amount * 0.9, amount * 0.9))


def apple_colour(diffuse, rim):
    """Five steps, not a gradient.

    A painter working a sphere does not mix one hundred values between the light and the shadow. The passage is built
    from a handful of tones -- deep madder, madder, vermilion, orange vermilion, a warm light -- each of which holds a
    little variation of its own, and the eye reads the boundary between two neighbouring tones as the turn of the form.
    Mixing continuously instead gives a sphere that is smoothly shaded and flat: everything correct, nothing modelled.

    So the input is quantised onto a ladder and only a small excursion is allowed inside a step, which is what the
    scatter of pigment around each tone then does anyway.
    """
    ladder = ((0.00, 0.20, (36, 10, 24)),
              (0.20, 0.42, (78, 13, 28)),
              (0.42, 0.64, (146, 22, 30)),
              (0.64, 0.84, (206, 66, 42)),
              (0.84, 1.01, (238, 130, 82)))
    body = ladder[-1][2]
    for low, high, colour in ladder:
        if diffuse < high:
            within = (diffuse - low) / (high - low)
            body = mix(colour, (colour[0] * 1.10, colour[1] * 1.06, colour[2] * 1.05), within * 0.55)
            break
    if rim > 0.0:
        body = mix(body, (104, 92, 120), min(0.26, rim * 0.34))
    return body


def ground(cx, cy, radius):
    """Primed canvas, then the room brushed over it.  The priming covers the whole picture, which is what a ground is."""
    layer = r.Layer(W, H)
    r.fill_polygon(layer, [(-20, -20), (W + 20, -20), (W + 20, H + 20), (-20, H + 20)], (46, 30, 24), 1.0)
    rng = random.Random(7)
    fig = project.Project(width=W, height=H, title='ground')
    marks = []
    for i in range(34):
        y = rng.uniform(-80, H + 80)
        x0 = rng.uniform(-240, W * 0.72)
        length = rng.uniform(320, 760)
        tone = jitter(mix((38, 26, 21), (108, 84, 64), rng.random() ** 1.6), 7, rng)
        marks.append(core.stroke_record(
            [(x0, y), (x0 + length * 0.45, y - rng.uniform(8, 44)), (x0 + length, y - rng.uniform(0, 70))],
            'brush', seed=i, colour=hexed(tone),
            width_profile=[rng.uniform(130, 240)] * 3,
            alpha_profile=[rng.uniform(0.22, 0.48)] * 3,
            absolute_width=True, edge=20.0))
    for mark in marks:
        fig.add_stroke(mark, stage='line', layer='paint', note='')
    painted = r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True)
    return r.blend(layer, painted, 'normal', 1.0)


def table_shadow(cx, cy, radius):
    layer = r.Layer(W, H)
    for scale, alpha in ((1.18, 0.17), (0.98, 0.21), (0.76, 0.25)):
        points = [(cx + radius * 0.26 + radius * 0.92 * scale * math.cos(a),
                   cy + radius * 0.98 + radius * 0.16 * scale * math.sin(a))
                  for a in (2.0 * math.pi * k / 96.0 for k in range(96))]
        r.fill_polygon(layer, points, (20, 12, 11), alpha=alpha)
    return layer


def scatter(cx, cy, radius, count, seed):
    """Points over the fruit, denser towards the rim, each carrying the light there and the surface's own direction."""
    rng = random.Random(seed)
    spots = []
    for _ in range(count):
        reach = radius * (rng.random() ** 0.55)
        angle = 2.0 * math.pi * rng.random()
        x = cx + reach * math.cos(angle) * 1.06
        y = cy + reach * math.sin(angle) * 0.95
        ux = (x - cx) / (radius * 1.06)
        uy = (y - cy) / (radius * 0.95)
        inside = 1.0 - ux * ux - uy * uy
        uz = math.sqrt(max(0.0, inside))
        diffuse = max(0.0, ux * LIGHT[0] + uy * LIGHT[1] + uz * LIGHT[2])
        spin = math.atan2(uy, ux) + math.pi * 0.5 + rng.uniform(-0.35, 0.35)
        spots.append((diffuse, x, y, math.cos(spin), math.sin(spin), uz, ux, uy))
    spots.sort(key=lambda row: row[0])
    return spots, rng


def body_marks(cx, cy, radius, seed=20261106):
    """Three brushes in the order a hand uses them, laying light over dark, with the middle pass crossed against the
    form so the paint stacks instead of reading as a smooth turn."""
    spots, rng = scatter(cx, cy, radius, 2600, seed)
    stages = ((380, 46, 64, 0.00, 0.42, 0.0),
              (900, 26, 40, 0.20, 0.78, 0.9),
              (1300, 13, 24, 0.50, 1.00, 0.4))
    fig = project.Project(width=W, height=H, title='apple body')
    index = 0
    for count, narrow, broad, low, high, cross in stages:
        band = [row for row in spots if low <= row[0] <= high]
        rng.shuffle(band)
        for diffuse, x, y, tx, ty, uz, ux, uy in band[:count]:
            if cross:
                turn = rng.uniform(-cross, cross)
                tx, ty = tx * math.cos(turn) - ty * math.sin(turn), tx * math.sin(turn) + ty * math.cos(turn)
            body = apple_colour(diffuse, max(0.0, -uy * 0.8 + ux * 0.25) if uz < 0.55 else 0.0)
            width = rng.uniform(narrow, broad)
            length = rng.uniform(42.0, 118.0)
            bend = rng.uniform(-0.25, 0.25) * length
            points = []
            for step in range(4):
                t = (step / 3.0 - 0.5) * length
                off = bend * (1.0 - (2.0 * step / 3.0 - 1.0) ** 2)
                points.append((x + tx * t - ty * off, y + ty * t + tx * off))
            pigment = jitter(body, 11.0, rng)
            fig.add_stroke(core.stroke_record(
                points, 'brush', seed=index, colour=hexed(pigment), soft=1.0,
                height=width / 125.0 * rng.uniform(0.55, 1.05),
                colour_profile=[[v * 0.86 for v in pigment], [v * 0.95 for v in pigment],
                                list(pigment), [v * 0.82 for v in pigment]],
                width_profile=[width] * 4, alpha_profile=[rng.uniform(0.72, 0.90),
                                                          rng.uniform(0.88, 0.98),
                                                          rng.uniform(0.88, 0.98),
                                                          rng.uniform(0.70, 0.88)],
                absolute_width=True, edge=rng.uniform(2.2, 6.5)), stage='line', layer='paint', note='')
            index += 1
    return fig


def rim_marks(cx, cy, radius, seed=77):
    """The edge of the fruit is a ring of wheel-spoke marks, because that is what a brush does round a sphere."""
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='rim')
    for i in range(150):
        angle = 2.0 * math.pi * rng.random()
        ux, uy = math.cos(angle), math.sin(angle)
        keep = rng.random()
        if keep < 0.28:
            continue
        diffuse = max(0.0, ux * LIGHT[0] + uy * LIGHT[1])
        rim = max(0.0, -uy * 0.8 + ux * 0.25)
        body = apple_colour(diffuse * 0.9, rim)
        body = mix(body, (52, 14, 24), 0.28)
        reach = radius * rng.uniform(0.96, 1.04)
        x = cx + reach * ux * 1.06
        y = cy + reach * uy * 0.95
        tx, ty = -uy, ux
        length = rng.uniform(26.0, 62.0)
        points = []
        for step in range(3):
            t = (step / 2.0 - 0.5) * length
            points.append((x + tx * t, y + ty * t))
        fig.add_stroke(core.stroke_record(
            points, 'brush', seed=800 + i, colour=hexed(jitter(body, 8.0, rng)),
            width_profile=[rng.uniform(12, 22)] * 3, alpha_profile=[rng.uniform(0.75, 0.95)] * 3,
            absolute_width=True, edge=rng.uniform(1.6, 3.2)), stage='line', layer='paint', note='')
    return fig


def dip_marks(cx, cy, radius, seed=404):
    """The hollow the stem sits in, and only there.

    The first attempt walked the whole upper rim in sixteen marks and drew a dotted arc across the fruit -- the third
    time in this script that marks arranged *along a contour* read as a ring.  A hollow is a small place, so it gets a
    small place: a scatter within a fifth of a radius of the stem's foot, turned along the lip of the dip.
    """
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='dip')
    for i in range(20):
        x = cx + rng.uniform(-0.26, 0.20) * radius
        y = cy - radius * rng.uniform(0.66, 0.84)
        tone = jitter(mix((26, 7, 17), (62, 14, 24), rng.random()), 7, rng)
        angle = rng.uniform(-0.9, 0.9)
        length = rng.uniform(16.0, 34.0)
        tx, ty = math.cos(angle), math.sin(angle) * 0.45
        fig.add_stroke(core.stroke_record(
            [(x - tx * length * 0.5, y - ty * length * 0.5), (x, y),
             (x + tx * length * 0.5, y + ty * length * 0.5)],
            'brush', seed=500 + i, colour=hexed(tone), soft=1.0,
            width_profile=[rng.uniform(10, 17)] * 3, alpha_profile=[0.55, 0.90, 0.55],
            absolute_width=True, edge=rng.uniform(2.0, 4.5)), stage='line', layer='paint', note='')
    return fig


def stem_marks(cx, cy, radius, seed=31):
    """No line: a few short dark marks, the same kind of mark as everything else."""
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='stem')
    for i in range(11):
        t = i / 10.0
        x = cx - radius * 0.02 + radius * (0.02 + 0.12 * t)
        y = cy - radius * (0.84 + 0.20 * t)
        tone = jitter(mix((52, 34, 20), (30, 19, 12), rng.random()), 6, rng)
        fig.add_stroke(core.stroke_record(
            [(x - 4, y + 10), (x + 2, y), (x + 8, y - 10)], 'brush', seed=600 + i,
            colour=hexed(tone), width_profile=[rng.uniform(11, 17)] * 3,
            alpha_profile=[rng.uniform(0.80, 0.96)] * 3, absolute_width=True, edge=1.8),
            stage='line', layer='paint', note='')
    return fig


def gloss_marks(cx, cy, radius, seed=99):
    """Thick paint, not a glow: small, blunt, opaque white, and one cool note along the reflected edge."""
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='gloss')
    for i in range(26):
        a = rng.uniform(-0.85, -0.35)
        reach = radius * rng.uniform(0.02, 0.26)
        x = cx + radius * (-0.42) + reach * math.cos(a)
        y = cy + radius * (-0.50) + reach * math.sin(a) * 0.7
        tone = mix((255, 247, 232), (255, 255, 250), rng.random())
        fig.add_stroke(core.stroke_record(
            [(x - 7, y + 3), (x, y), (x + 7, y - 2)], 'brush', seed=700 + i,
            colour=hexed(tone), width_profile=[rng.uniform(8, 15)] * 3,
            alpha_profile=[rng.uniform(0.82, 1.0)] * 3, absolute_width=True, edge=1.4),
            stage='line', layer='paint', note='')
    return fig


def trim_marks(cx, cy, radius, backdrop, seed=555):
    """The edge is corrected the way a painter corrects it: by painting over it, with the colour that is already there.

    The body's marks run past the form and their ends decide the outline, which is why the fruit came out square. The
    digital answer would be a mask; the painter's answer is a brush loaded with the room and dragged along the rim --
    so the boundary is painted, not clipped, and it stays slightly irregular because a hand made it.

    **The colour is read off the room itself, not averaged.** A mean of the ground is darker than the ground where the
    rim is, so a mean turns the correction into a grey halo around the fruit -- which is exactly what the first attempt
    drew. Reading the backdrop's own pixel means the mark is invisible except for the coverage it replaces.

    **Only the upper rim.** Along the bottom the fruit meets its own shadow, and there the boundary should be lost
    rather than corrected, so nothing is painted over that half.
    """
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='trim')
    for i in range(18):
        angle = math.pi * (-1.0 + 2.0 * i / 18.0) + rng.uniform(-0.05, 0.05)
        ux, uy = math.cos(angle), math.sin(angle)
        reach = radius * rng.uniform(1.03, 1.08)
        x = cx + reach * ux * 1.06
        y = cy + reach * uy * 0.95
        xi = int(min(W - 1, max(0, round(x + ux * 6.0))))
        yi = int(min(H - 1, max(0, round(y + uy * 6.0))))
        at = (yi * W + xi) * 4
        tone = (backdrop.data[at], backdrop.data[at + 1], backdrop.data[at + 2])
        tx, ty = -uy, ux
        length = rng.uniform(95.0, 150.0)
        fig.add_stroke(core.stroke_record(
            [(x - tx * length * 0.5, y - ty * length * 0.5), (x, y),
             (x + tx * length * 0.5, y + ty * length * 0.5)],
            'brush', seed=900 + i, colour=hexed(tone), soft=1.0,
            width_profile=[rng.uniform(22, 38)] * 3, alpha_profile=[0.60, 0.95, 0.60],
            absolute_width=True, edge=rng.uniform(6, 11)), stage='line', layer='paint', note='')
    return fig


def main():
    os.makedirs(OUT, exist_ok=True)
    cx, cy, radius = W * 0.50, H * 0.53, 232.0
    backdrop = ground(cx, cy, radius)
    picture = backdrop
    picture = r.blend(picture, table_shadow(cx, cy, radius), 'normal', 1.0)
    order = (body_marks(cx, cy, radius), dip_marks(cx, cy, radius),
             stem_marks(cx, cy, radius), gloss_marks(cx, cy, radius))
    for fig in order:
        picture = r.blend(picture, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True),
                          'normal', 1.0)
    path = os.path.join(OUT, 'apple.png')
    r.save_png(r.light(picture, direction=(-0.50, -0.58, 1.15), strength=0.34, tilt=1.15), path,
               background=(22, 16, 13))
    project.save_project(order[0], os.path.join(OUT, 'pass-body.json'))
    print('%s  %d marks in %d passes' % (path, sum(len(fig.marks) for fig in order), len(order) + 2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
