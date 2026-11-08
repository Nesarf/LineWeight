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
    ladder = ((0.00, 0.22, (34, 9, 23)),
              (0.22, 0.46, (84, 14, 30)),
              (0.46, 0.70, (158, 26, 34)),
              (0.70, 0.88, (214, 62, 40)),
              (0.88, 1.01, (232, 104, 66)))
    body = ladder[-1][2]
    for low, high, colour in ladder:
        if diffuse < high:
            within = (diffuse - low) / (high - low)
            # **档与档之间是跳，档之内是走。** 一档色本身还是一段路：最冷最暗的一头往紫里偏，最暖最亮的
            # 一头往橙里偏。这段跨度必须大于「把颜色数成有限几格」时的步长 —— 否则一档里上千笔落进同一个
            # 格子，画面上就是一块平色。`tools/oil_survey.py` 量出来的最大块（六万两千像素）就在果子的
            # 亮面上，正是这一档：原来的跨度只有百分之五，比每笔之间的随机差还小。
            body = mix((colour[0] * 0.86, colour[1] * 0.93, colour[2] * 1.10),
                       (colour[0] * 1.16, colour[1] * 1.09, colour[2] * 0.97), within)
            break
    if rim > 0.0:
        body = mix(body, (104, 92, 120), min(0.16, rim * 0.22))
    return body


def ground(cx, cy, radius):
    """Primed canvas, then the room brushed over it.  The priming covers the whole picture, which is what a ground is.

    **But a ground is not a colour, it is a walk over the whole surface.** The first version laid thirty-four marks
    across a flat priming and left most of the picture untouched -- which measured as the second largest block in the
    whole painting, a flat region nobody had painted. A hand priming a panel works a grid over it in overlapping
    diagonal passes and varies the tone by where the light is, so the room is brighter towards the upper left and
    goes down into the corner; the coverage is dense enough that no part of the surface is bare.

    The marks carry a small `height`, so the wall has a tooth that `raster.light` can find. Without it the background
    has no relief at all and stays perfectly flat however its colour is varied.
    """
    layer = r.Layer(W, H)
    r.fill_polygon(layer, [(-20, -20), (W + 20, -20), (W + 20, H + 20), (-20, H + 20)], (46, 30, 24), 1.0)
    rng = random.Random(7)
    fig = project.Project(width=W, height=H, title='ground')
    marks = []
    rows, cols = 16, 13
    index = 0
    for row in range(rows):
        for col in range(cols):
            x = -90.0 + (W + 180.0) * (col + 0.5) / cols + rng.uniform(-42.0, 42.0)
            y = -90.0 + (H + 180.0) * (row + 0.5) / rows + rng.uniform(-34.0, 34.0)
            lit = max(0.0, min(1.0, 1.0 - 0.66 * (0.58 * x / W + 0.42 * y / H)))
            tone = jitter(mix((24, 16, 13), (136, 108, 80), lit ** 1.30), 15.0, rng)
            # 墙也不是一个棕色。阴影里的墙偏冷，受光的一侧偏暖，中间夹几笔灰绿 —— 与果身上那层异色笔同一个理由：
            # 同色相的深浅会被数颜色的小格子归并掉，只有换色相才能把一块大面切开。
            if rng.random() < 0.30:
                accent = ((74, 80, 94), (152, 130, 104), (96, 104, 88), (118, 96, 82))[rng.randrange(4)]
                tone = mix(tone, accent, rng.uniform(0.24, 0.56))
            length = rng.uniform(240.0, 500.0)
            angle = rng.uniform(-0.10, 0.10) + 0.05
            tx, ty = math.cos(angle), math.sin(angle)
            marks.append(core.stroke_record(
                [(x - tx * length * 0.5, y - ty * length * 0.5),
                 (x, y + rng.uniform(-7.0, 7.0)),
                 (x + tx * length * 0.5, y + ty * length * 0.5)],
                'brush', seed=index, colour=hexed(tone), soft=1.0,
                height=rng.uniform(0.015, 0.075),
                bristle=0.38, bristle_pitch=rng.uniform(2.6, 4.4),
                colour_profile=[[v * 0.90 for v in tone], list(tone), [v * 0.94 for v in tone]],
                width_profile=[rng.uniform(80.0, 150.0)] * 3,
                alpha_profile=[rng.uniform(0.34, 0.62)] * 3,
                absolute_width=True, edge=rng.uniform(9.0, 19.0)))
            index += 1
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


def body_marks(cx, cy, radius, seed=20261106, dim=1.0):
    """A few hundred strokes along the latitudes of the form, laid down dark to light.

    **The count was the thing that was wrong.** The first version laid two thousand six hundred short, wide marks over
    the fruit -- each with its own round head, its own soft edge, and its own colour -- and whatever was done to those
    colours afterwards, the surface read as fur, because that is what a pile of round-headed dabs is. A hand painting an
    apple makes thirty or forty strokes: long, narrow, following the turn of the sphere, each one a plane rather than a
    patch. Everything this file changed in the meantime (a wider ladder, broken colour, foreign hues, a finer edge) was
    a correction applied to the dabs, and no correction of that kind can fix a surface made of them.

    So a mark here is an **arc concentric with the fruit** -- a straight segment long enough to be a plane would leave
    the sphere -- and the whole set is sorted by how much light falls on it: darks first, lights last, which is the order
    a form is built in. Five tones carry it, and the boundary between two neighbouring tones is the turn.
    """
    rng = random.Random(seed)
    spots = []
    for _ in range(520):
        reach = radius * (rng.random() ** 0.5) * 0.94
        angle = rng.uniform(0.0, 2.0 * math.pi)
        ux = reach * math.cos(angle) / (radius * 1.06)
        uy = reach * math.sin(angle) / (radius * 0.95)
        inside = 1.0 - ux * ux - uy * uy
        if inside <= 0.0:
            continue
        uz = math.sqrt(inside)
        diffuse = max(0.0, ux * LIGHT[0] + uy * LIGHT[1] + uz * LIGHT[2])
        spots.append((diffuse, reach, angle, uz, ux, uy))
    spots.sort(key=lambda row: row[0])
    fig = project.Project(width=W, height=H, title='apple body')
    for index, (diffuse, reach, angle, uz, ux, uy) in enumerate(spots):
        rim = max(0.0, -uy * 0.8 + ux * 0.25) if uz < 0.55 else 0.0
        # **笔与笔之间不该是跳的。** 一路上都在给每一笔加随机偏移，好让它和邻居不一样 —— 而 `tools/oil_survey.py`
        # 新加的那一列说出了它的代价：大块内部的颜色标准差只有 1.1，七张油画是 3.6 到 7.9。偏移把每一笔推成
        # 一个孤立的色点，量化成有限几格时它们全落到格子边界上，格子内部反而笔笔相同。画家不给每一笔加偏移：
        # 一笔的颜色由它落在哪里决定，位置连续，颜色就连续。所以偏移收到很小，变化交给位置。
        pigment = jitter(apple_colour(diffuse, rim), 5.0, rng)
        # **同一支笔画第二个果子时要压暗。** 一张画里离得远的那一个，颜色整体要收一点 —— 它被前面的挡住一部分
        # 光，也被中间的空气隔了一层。默认 `1.0` 时算式不变，所以单只果子那张的像素与改动之前完全一样。
        if dim != 1.0:
            pigment = tuple(v * dim for v in pigment)
        # **弧心回到果子中心，而笔触要短。** 绕光轴的等照度线试过了：它们在投影上弯得厉害，一条二百五十像素
        # 的弧在半径四百处两端要向内收七十像素，整只苹果长成一朵莲座。绕果心、而且短，才是手能做到的那件事 ——
        # 一笔只占一段纬线，两端的弯曲小于笔宽，相邻两笔的界由湿颜料自己融掉。也试过给每一笔自己的曲率半径，
        # 结果每笔两端都翘出来，成了菊花；同心是对的，长的同心弧才是错的。
        if reach < radius * 0.36:
            # **正中那一块不能用绕圈的笔。** 半径越小弧越短，一圈一圈收拢，中心就多出一个漩涡芯 —— 而苹果
            # 正对着观者的地方是平的。画家在这里是一两笔斜着扫过去：方向随便，长度够，把中心盖住就算。
            spin = rng.uniform(0.0, math.pi)
            arm = rng.uniform(80.0, 170.0) * 0.5
            hx = cx + reach * math.cos(angle) * 1.06
            hy = cy + reach * math.sin(angle) * 0.95
            points = [(hx - math.cos(spin) * arm, hy - math.sin(spin) * arm * 0.9),
                      (hx, hy),
                      (hx + math.cos(spin) * arm, hy + math.sin(spin) * arm * 0.9)]
            width = rng.uniform(26.0, 46.0)
        else:
            half = min(0.85, rng.uniform(60.0, 120.0) / max(30.0, reach))
            points = []
            for step in range(5):
                turn = angle + (step / 4.0 - 0.5) * 2.0 * half
                sway = reach * (1.0 + 0.03 * math.sin(step * 1.7 + index))
                points.append((cx + sway * math.cos(turn) * 1.06, cy + sway * math.sin(turn) * 0.95))
            width = rng.uniform(20.0, 36.0)
        fig.add_stroke(core.stroke_record(
            points, 'brush', seed=index, colour=hexed(pigment), soft=0.7,
            height=width / 110.0 * rng.uniform(0.18, 0.38),
            bristle=0.32, bristle_pitch=rng.uniform(3.0, 5.0),
            colour_profile=[[c * s for c in pigment] for s in (0.96, 1.00, 1.03, 0.99, 0.95)],
            width_profile=[width] * 5,
            alpha_profile=[0.72, 0.82, 0.86, 0.82, 0.70],
            absolute_width=True, edge=rng.uniform(1.4, 2.8)), stage='line', layer='paint', note='')
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


def drag_marks(cx, cy, radius, seed=913):
    """几条弧，把已经铺上的颜料往笔走的方向拉开。

    **湿画法不是一种混合模式，是一个动作。** 在还没干的底色上再落笔，笔毛会把下面的颜料带出去一小段，
    于是两笔之间的接触线是脏的、有方向的。这里在果身上挑几处，沿着果面的弧拖一次 ---- 不多，因为画家也只
    在需要让两块颜色接上时拖那么几笔；拖满整张就成了模糊。
    """
    rng = random.Random(seed)
    runs = []
    for _ in range(8):
        start = rng.uniform(0.0, 2.0 * math.pi)
        reach = radius * rng.uniform(0.12, 0.70)
        points = []
        for k in range(6):
            angle = start + k * rng.uniform(0.11, 0.24)
            points.append((cx + reach * math.cos(angle) * 1.06, cy + reach * math.sin(angle) * 0.95))
        runs.append((points, rng.uniform(24.0, 42.0), rng.uniform(0.30, 0.55)))
    return runs


def main():
    os.makedirs(OUT, exist_ok=True)
    cx, cy, radius = W * 0.50, H * 0.53, 232.0
    backdrop = ground(cx, cy, radius)
    picture = backdrop
    picture = r.blend(picture, table_shadow(cx, cy, radius), 'normal', 1.0)
    body_fig = body_marks(cx, cy, radius)
    body_layer = r.render_marks([m.to_dict() for m in body_fig.marks], W, H, sweep=True)
    for points, reach, strength in drag_marks(cx, cy, radius):
        r.smudge(body_layer, points, radius=reach, strength=strength)
    picture = r.blend(picture, body_layer, 'normal', 1.0)
    order = (body_fig, dip_marks(cx, cy, radius), stem_marks(cx, cy, radius), gloss_marks(cx, cy, radius))
    for fig in order[1:]:
        picture = r.blend(picture, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True),
                          'normal', 1.0)
    path = os.path.join(OUT, 'apple.png')
    r.save_png(r.light(picture, direction=(-0.50, -0.58, 1.15), strength=0.34, tilt=1.15), path,
               background=(22, 16, 13))
    project.save_project(body_fig, os.path.join(OUT, 'pass-body.json'))
    print('%s  %d marks in %d passes' % (path, sum(len(fig.marks) for fig in order), len(order) + 2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
