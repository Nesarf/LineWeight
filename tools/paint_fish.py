"""A fish: the third example, and the first one whose form comes from data rather than from a formula.

The apple and the cloth were both shapes something could write down — a sphere has a radius, a hanging cloth has two
edge functions. **An irregular object has neither.** There is no closed form for a fish, and a drawing tool that can
only paint shapes with equations cannot draw most of the world.

So the form is data: a list of control points, closed, and nothing else. From that outline the painter's two questions
are answered without any further knowledge of the subject:

* **How thick is it here?** The distance from a point to the outline, normalised by the largest such distance. The
  medial axis is the ridge of the form, the outline is its edge, and everything between them is a falloff.
* **Which way does the surface face?** The gradient of that height field — the same thing `raster.light` does with
  pigment thickness, except here the thickness is the object rather than the paint.

Everything after that is the machinery the apple used: marks scattered over the form, pigment that varies inside a mark,
wet dragging, bristle, and a side light at the end.

**One scale trap, recorded because it cost a pass.** The gradient of a normalised height field is of order a thousandth
per pixel — the whole fish is where the field travels from zero to one — so multiplying it by thirty leaves the normal
within a fraction of vertical and the Lambert term constant across the entire picture. Every colour is then correct and
the fish is flat. The tilt has to match the scale the height field lives at, which for a form is a few hundred;
`raster.light`'s own `tilt` means the same thing and carries the same dependence.
"""

import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineweight import core, project          # noqa: E402
from lineweight import raster as r            # noqa: E402

W, H = 1400, 900
OUT = os.environ.get('FISH_OUT') or os.path.join(os.getcwd(), 'fish')
LIGHT = (-0.42, -0.50, 0.76)

# **The whole of the subject, and all of it arbitrary.** A snout at the right, a tail at the left, a dorsal ridge, a
# belly; the numbers came from looking at a fish, not from solving for one.
BODY = [(168, 452), (238, 402), (326, 376), (430, 356), (556, 338), (700, 332), (826, 344),
        (930, 372), (1012, 414), (1064, 462), (1068, 508), (1030, 556), (944, 596),
        (846, 620), (726, 634), (594, 638), (468, 630), (356, 610), (272, 580), (200, 540), (162, 494)]
FIN = [(188, 446), (120, 348), (96, 300), (150, 386), (176, 430)]
TAIL = [(168, 452), (58, 430), (22, 462), (52, 496), (166, 498)]
DORSAL = [(470, 336), (520, 306), (588, 296), (660, 304), (700, 336), (586, 340)]
EYE = (1002, 452)


def mask_of(points):
    image = Image.new('L', (W, H), 0)
    ImageDraw.Draw(image).polygon(points, fill=255)
    return np.asarray(image) > 127


def height_of(mask, exponent=0.52):
    """到轮廓的距离归一化再开方 —— 中线是脊，轮廓是边，中间是落差。"""
    inside = ndimage.distance_transform_edt(mask)
    peak = float(inside.max()) or 1.0
    return (inside / peak) ** exponent


def shading(relief, tilt=0.9):
    """高度场的梯度当法线 —— 与 `raster.light` 同一个式子，只是这里的高度是形体本身。

    **`30.0` 那个旧尺度是错的。** `relief` 归一化在 0 到 1，跨过整条鱼才走完这一段，所以每像素的梯度在千分之三量级；
    乘三十仍然只有零点一，法线几乎垂直，朗伯项于是到处一样 —— 画面平不是因为颜色浅，是因为法线根本没转。
    形体尺度的一张图要乘到几百才让法线真的偏过去。
    """
    gy, gx = np.gradient(relief)
    nx = -gx * tilt * 380.0
    ny = -gy * tilt * 380.0
    norm = np.sqrt(nx * nx + ny * ny + 1.0)
    lx, ly, lz = LIGHT
    length = math.sqrt(lx * lx + ly * ly + lz * lz)
    lambert = (nx * lx + ny * ly + lz) / (norm * length)
    return np.clip(0.16 + 1.05 * lambert, 0.0, 1.35)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def hexed(colour):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in colour)


def jitter(colour, amount, rng):
    return (colour[0] + rng.uniform(-amount, amount),
            colour[1] + rng.uniform(-amount * 0.9, amount * 0.9),
            colour[2] + rng.uniform(-amount * 0.8, amount * 0.8))


def fish_colour(value, rng):
    """银背、粉腹、背脊偏青 —— 鱼的体色是上下分带的，不是从亮到暗一路排下去。"""
    deep, mid, back = (34, 38, 48), (172, 162, 150), (208, 204, 190)
    body = mix(deep, mid, value / 0.55) if value <= 0.55 else mix(mid, back, (value - 0.55) / 0.55)
    body = mix(body, (150, 132, 138), 0.18)
    return jitter(body, 9.0, rng)


def canvas(title):
    return project.Project(width=W, height=H, title=title)


def ground():
    layer = r.Layer(W, H)
    r.fill_polygon(layer, [(-20, -20), (W + 20, -20), (W + 20, H + 20), (-20, H + 20)], (38, 34, 32), 1.0)
    rng = random.Random(11)
    fig = canvas('ground')
    for i in range(22):
        y = rng.uniform(-60, H + 60)
        x0 = rng.uniform(-200, W * 0.7)
        tone = jitter(mix((30, 26, 25), (78, 68, 60), rng.random() ** 1.4), 6, rng)
        fig.add_stroke(core.stroke_record(
            [(x0, y), (x0 + 360, y - rng.uniform(6, 34)), (x0 + 760, y - rng.uniform(0, 52))],
            'brush', seed=700 + i, colour=hexed(tone), soft=1.0,
            width_profile=[rng.uniform(110, 230)] * 3, alpha_profile=[rng.uniform(0.20, 0.42)] * 3,
            absolute_width=True, edge=20.0), stage='line', layer='paint', note='')
    return r.blend(layer, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True), 'normal', 1.0)


def fish_marks(seed=8181):
    """在轮廓内撒点，笔触沿水平走 —— 鱼身的肌理是横的，而阴影是高度场给的。"""
    rng = random.Random(seed)
    mask = mask_of(BODY) | mask_of(TAIL)
    relief = height_of(mask)
    tone = shading(relief)
    fig = canvas('fish body')
    rows, cols = np.nonzero(mask)
    index = 0
    for _ in range(3400):
        pick = rng.randrange(rows.size)
        y, x = int(rows[pick]), int(cols[pick])
        value = float(tone[y, x])
        pigment = fish_colour(value, rng)
        length = rng.uniform(28.0, 86.0)
        drift = rng.uniform(-7.0, 7.0)
        points = [(x - length * 0.5, y - drift * 0.5), (x, y), (x + length * 0.5, y + drift * 0.5)]
        width = rng.uniform(11.0, 26.0)
        fig.add_stroke(core.stroke_record(
            points, 'brush', seed=index, colour=hexed(pigment), soft=1.0,
            colour_profile=[[v * 0.90 for v in pigment], list(pigment), [v * 0.86 for v in pigment]],
            height=width / 140.0 * rng.uniform(0.5, 1.0),
            bristle=0.38, bristle_pitch=rng.uniform(2.4, 3.4),
            width_profile=[width * 0.9, width, width * 0.92],
            alpha_profile=[rng.uniform(0.82, 0.92)] * 3,
            absolute_width=True, edge=rng.uniform(2.5, 6.0)), stage='line', layer='paint', note='')
        index += 1
    return fig, mask, relief, tone


def fin_marks(seed=505):
    """鳍与远侧的那一片：薄，所以几乎只由高度场的边缘决定。"""
    rng = random.Random(seed)
    fig = canvas('fins')
    for shape, density in ((FIN, 130), (DORSAL, 150)):
        mask = mask_of(shape)
        relief = height_of(mask, exponent=0.75)
        tone = shading(relief, tilt=0.6)
        rows, cols = np.nonzero(mask)
        for i in range(density):
            pick = rng.randrange(rows.size)
            y, x = int(rows[pick]), int(cols[pick])
            pigment = jitter(mix((108, 96, 96), (206, 196, 182), min(1.0, float(tone[y, x]))), 8.0, rng)
            length = rng.uniform(20.0, 56.0)
            fig.add_stroke(core.stroke_record(
                [(x - length * 0.5, y + rng.uniform(-6, 6)), (x, y),
                 (x + length * 0.5, y + rng.uniform(-6, 6))], 'brush', seed=900 + i,
                colour=hexed(pigment), soft=1.0, height=0.28, bristle=0.30,
                width_profile=[rng.uniform(7, 15)] * 3, alpha_profile=[0.72, 0.88, 0.72],
                absolute_width=True, edge=rng.uniform(2.5, 5.0)), stage='line', layer='paint', note='')
    return fig


def eye_marks():
    """一只眼：一个暗的圆、一圈亮环、一个白点。形体给不出的那一点，靠这三笔。"""
    fig = canvas('eye')
    rng = random.Random(77)
    cx, cy = EYE
    for i, (radius, colour, alpha) in enumerate(((16.0, '#2a2422', 0.96), (22.0, '#6e6258', 0.55))):
        ring = [(cx + radius * math.cos(a) - 3, cy + radius * math.sin(a)) for a in
                (2 * math.pi * k / 24 for k in range(25))]
        fig.add_stroke(core.stroke_record(ring, 'brush', seed=300 + i, colour=colour, soft=1.0,
                                          width_profile=[6.0] * len(ring), alpha_profile=[alpha] * len(ring),
                                          absolute_width=True, edge=3.0),
                       stage='line', layer='paint', note='')
    fig.add_stroke(core.stroke_record([(cx - 5, cy - 5), (cx - 1, cy - 7)], 'brush', seed=310,
                                      colour='#fff6e8', soft=1.0, width_profile=[6.0, 6.0],
                                      alpha_profile=[0.95, 0.95], absolute_width=True, edge=2.0),
                   stage='line', layer='paint', note='')
    return fig


def main():
    os.makedirs(OUT, exist_ok=True)
    picture = ground()
    body, mask, relief, tone = fish_marks()
    layer = r.render_marks([m.to_dict() for m in body.marks], W, H, sweep=True)
    rng = random.Random(404)
    for _ in range(16):
        y = rng.uniform(360.0, 620.0)
        x0 = rng.uniform(220.0, 760.0)
        points = [(x0 + k * 34.0, y + math.sin(k * 0.6) * 6.0) for k in range(6)]
        r.smudge(layer, points, radius=rng.uniform(22, 40), strength=rng.uniform(0.28, 0.48))
    picture = r.blend(picture, layer, 'normal', 1.0)
    for fig in (fin_marks(), eye_marks()):
        picture = r.blend(picture, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True),
                          'normal', 1.0)
    path = os.path.join(OUT, 'fish.png')
    r.save_png(r.light(picture, direction=LIGHT, strength=0.26, tilt=1.0), path, background=(18, 15, 14))
    project.save_project(body, os.path.join(OUT, 'pass-fish.json'))
    print('%s  %d marks' % (path, len(body.marks)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
