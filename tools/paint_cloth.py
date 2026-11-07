"""A hanging cloth: a folded surface, and the first picture here drawn from a counted list.

**Two things it tests, neither of which the apple could.** The apple was a sphere, and a sphere's shading is a dot
product with a normal; a fold's is not. Light across a fold depends on how near a point sits to the top of a ridge,
which is a *phase* across the ridge, and no normal is computed anywhere in this file. So this is the first check on
whether the five fields added for the apple -- `soft`, `colour_profile`, `height`, `smudge`, `bristle` -- belong to
painting or only to that one picture.

And it is the first place `learn/facts.json` reaches a drawing. A `pipe` fold is "fabric falling freely from a condensed
area, semicylindrical or semiconical"; a `half-lock` is "the inside of a bend in tubular cloth buckling". Six pipe folds
hang from a rod, and the cloth is caught up on the right where a half-lock forms. Those two sentences are countable and
named, and until this file they had never been in a picture.

The cloth is undyed linen, because colour cannot hide a wrong form and white exposes one.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineweight import core, project          # noqa: E402
from lineweight import raster as r            # noqa: E402

W, H = 1100, 1400
OUT = os.environ.get('CLOTH_OUT') or os.path.join(os.getcwd(), 'cloth')
FOLDS = 6.0
ROD_Y = 150.0


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def hexed(colour):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in colour)


def jitter(colour, amount, rng):
    return (colour[0] + rng.uniform(-amount, amount),
            colour[1] + rng.uniform(-amount * 0.9, amount * 0.9),
            colour[2] + rng.uniform(-amount * 0.85, amount * 0.85))


def edges(y):
    """布幅的左右边界：顶部收在挂杆上，向下散开，下摆略带弧。"""
    t = max(0.0, (y - ROD_Y) / (H - ROD_Y))
    left = 380.0 - 260.0 * t ** 0.85
    right = 720.0 + 270.0 * t ** 0.85
    sag = 34.0 * math.sin(math.pi * min(1.0, t * 1.4))
    return left, right + sag * 0.2


def fold_centre(index, y):
    """一条褶的中线在某个高度上的横坐标 —— 布垂下来的时候褶会扭。"""
    left, right = edges(y)
    t = max(0.0, (y - ROD_Y) / (H - ROD_Y))
    spread = left + (right - left) * (index + 0.5) / FOLDS
    sway = math.sin(t * 3.1 + index * 1.7) * (18.0 + 26.0 * t)
    return spread + sway


def shade(x, y):
    """相位给圆脊的受光，位置的左右给整幅的受光。两个都不是法线。"""
    left, right = edges(y)
    if x <= left or x >= right:
        return None
    reach = max(1.0, right - left)
    phase = ((x - left) / reach) * FOLDS % 1.0
    ridge = 0.5 + 0.5 * math.cos((phase - 0.5) * 2.0 * math.pi)
    across = 1.0 - (x - left) / reach
    half_lock = 0.0
    # half-lock：布在右侧被挽起，弯折内侧堆出一条横向的隆起
    catch = (H * 0.42, H * 0.52)
    if catch[0] < y < catch[1]:
        span = 1.0 - abs((y - (catch[0] + catch[1]) * 0.5) / ((catch[1] - catch[0]) * 0.5))
        if x > left + reach * 0.62:
            half_lock = max(0.0, span) * 0.55
    value = 0.20 + 0.58 * ridge * (0.50 + 0.50 * across) + 0.20 * across + half_lock * 0.5
    return min(1.0, value)


def cloth_colour(value):
    """米白的亚麻：受光处偏暖，背光处偏冷，中间调保持中性。"""
    dark, mid, light = (58, 54, 66), (176, 168, 152), (242, 234, 214)
    body = mix(dark, mid, value / 0.55) if value <= 0.55 else mix(mid, light, (value - 0.55) / 0.45)
    if value < 0.42:
        body = mix(body, (64, 66, 88), (0.42 - value) * 0.55)
    return body


def canvas(title):
    return project.Project(width=W, height=H, title=title)


def ground():
    layer = r.Layer(W, H)
    r.fill_polygon(layer, [(-20, -20), (W + 20, -20), (W + 20, H + 20), (-20, H + 20)], (44, 34, 30), 1.0)
    rng = random.Random(5)
    fig = canvas('ground')
    for i in range(30):
        y = rng.uniform(-80, H + 80)
        x0 = rng.uniform(-260, W * 0.7)
        length = rng.uniform(340, 800)
        tone = jitter(mix((36, 27, 24), (96, 78, 64), rng.random() ** 1.5), 7, rng)
        fig.add_stroke(core.stroke_record(
            [(x0, y), (x0 + length * 0.5, y - rng.uniform(6, 40)), (x0 + length, y - rng.uniform(0, 60))],
            'brush', seed=800 + i, colour=hexed(tone), soft=1.0,
            width_profile=[rng.uniform(140, 260)] * 3,
            alpha_profile=[rng.uniform(0.20, 0.44)] * 3,
            absolute_width=True, edge=22.0), stage='line', layer='paint', note='')
    return r.blend(layer, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True), 'normal', 1.0)


def rod():
    """挂杆与两端的固定 —— 布要从什么地方垂下来，得先有个地方。"""
    fig = canvas('rod')
    fig.add_stroke(core.stroke_record(
        [(140, ROD_Y - 12), (W * 0.5, ROD_Y - 28), (W - 140, ROD_Y - 8)], 'brush', seed=901,
        colour='#4a3a2c', soft=1.0, height=0.9,
        width_profile=[22.0] * 3, alpha_profile=[0.95] * 3, absolute_width=True, edge=4.0),
        stage='line', layer='paint', note='')
    return fig


def cloth_marks(seed=4211):
    """整块布面都要落笔，不是沿褶的中线画线。

    **第一版把「褶」当成了线**：只在每条褶的中线上撒点，于是画面成了六条并列的面条，缝隙里露着背景。
    褶不是线，是**面的起伏** —— 它改变的是每个点落在哪一侧、离脊顶多远，而布面上每一个点都有颜色。
    所以这里在布幅范围内均匀落点，笔触顺褶而下（褶是竖直的），明暗由 `shade` 当场算出来。
    """
    rng = random.Random(seed)
    fig = canvas('cloth body')
    index = 0
    y = ROD_Y
    while y < H - 16:
        left, right = edges(y)
        x = left + rng.uniform(-4.0, 4.0)
        while x < right:
            value = shade(x, y)
            if value is None:
                x += 11.0
                continue
            pigment = jitter(cloth_colour(value), 7.0, rng)
            length = rng.uniform(150.0, 330.0)
            drift = math.sin(y / 92.0) * rng.uniform(2.0, 8.0)
            points = [(x - drift * 0.5, y - length * 0.5),
                      (x, y),
                      (x + drift * 0.5, y + length * 0.5)]
            width = rng.uniform(22.0, 36.0)
            fig.add_stroke(core.stroke_record(
                points, 'brush', seed=index, colour=hexed(pigment), soft=1.0,
                colour_profile=[[v * 0.90 for v in pigment], list(pigment), [v * 0.86 for v in pigment]],
                height=width / 130.0 * rng.uniform(0.5, 1.0),
                bristle=0.42, bristle_pitch=rng.uniform(2.4, 3.6),
                width_profile=[width * 0.92, width, width * 0.94],
                alpha_profile=[rng.uniform(0.90, 0.96)] * 3,
                absolute_width=True, edge=rng.uniform(3.0, 7.0)), stage='line', layer='paint', note='')
            index += 1
            x += rng.uniform(9.0, 15.0)
        y += rng.uniform(15.0, 22.0)
    return fig


def valley_marks(seed=77):
    """褶与褶之间的缝：那里最暗，也最不该是干净的线。"""
    rng = random.Random(seed)
    fig = canvas('valleys')
    for step in range(int((H - ROD_Y) / 22)):
        y = ROD_Y + step * 22.0 + rng.uniform(-6.0, 6.0)
        for fold in range(int(FOLDS) + 1):
            x = fold_centre(max(0, fold - 0.5), y)
            value = shade(x, y)
            if value is None:
                continue
            tone = jitter(cloth_colour(max(0.0, value - 0.30)), 6.0, rng)
            fig.add_stroke(core.stroke_record(
                [(x, y - 22.0), (x + rng.uniform(-4, 4), y), (x, y + 22.0)], 'brush',
                seed=1200 + step * 9 + fold, colour=hexed(tone), soft=1.0, height=0.3,
                width_profile=[rng.uniform(7, 13)] * 3, alpha_profile=[0.35, 0.62, 0.35],
                absolute_width=True, edge=rng.uniform(4.0, 8.0)), stage='line', layer='paint', note='')
    return fig


def main():
    os.makedirs(OUT, exist_ok=True)
    picture = ground()
    picture = r.blend(picture, r.render_marks([m.to_dict() for m in rod().marks], W, H, sweep=True), 'normal', 1.0)
    body = cloth_marks()
    layer = r.render_marks([m.to_dict() for m in body.marks], W, H, sweep=True)
    rng = random.Random(313)
    for _ in range(28):
        fold = rng.uniform(0.0, FOLDS)
        y0 = rng.uniform(ROD_Y + 60, H - 120)
        points = [(fold_centre(fold * 0.98, y0 + k * 34.0), y0 + k * 34.0) for k in range(6)]
        r.smudge(layer, points, radius=rng.uniform(30, 52), strength=rng.uniform(0.35, 0.60))
    picture = r.blend(picture, layer, 'normal', 1.0)
    path = os.path.join(OUT, 'cloth.png')
    r.save_png(r.light(picture, direction=(-0.55, -0.40, 0.92), strength=0.30, tilt=1.1), path,
               background=(20, 16, 14))
    project.save_project(body, os.path.join(OUT, 'pass-cloth.json'))
    print('%s  %d marks' % (path, len(body.marks)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
