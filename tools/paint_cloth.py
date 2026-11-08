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
    """米白的亚麻：受光的一面偏暖偏黄，背光的一面偏冷偏蓝。

    **`within` 停在 2.4 的一半原因在这里。** 原来三段是 (58,54,66) / (176,168,152) / (242,234,214)，
    明度从暗到亮是有的，而色相几乎不动 —— 把画面数成十八色的时候整块布落进两三个亮格子，格子内部当然均匀。
    真实的亚麻布不是这样一个色相：背光那一片是蓝紫的，受光那一片带黄褐的暖，中间才是中性米白。
    所以两头都拉开，暗部再压一层蓝、亮部再点一层黄。
    """
    dark, mid, light = (44, 42, 62), (180, 166, 140), (250, 244, 226)
    body = mix(dark, mid, value / 0.55) if value <= 0.55 else mix(mid, light, (value - 0.55) / 0.45)
    if value < 0.42:
        body = mix(body, (52, 54, 92), (0.42 - value) * 0.50)
    if value > 0.72:
        body = mix(body, (252, 232, 186), (value - 0.72) * 0.60)
    return body


def canvas(title):
    return project.Project(width=W, height=H, title=title)


def ground():
    """背景刷满整张。三十笔盖不住一块画布 —— 那一个教训苹果和鱼各付了一次。

    `tools/oil_survey.py` 的 `within` 量的就是这件事：这张布 2.5，四张里第二低，而它最大的两块五万七和四万六
    都在背景里。底色之上按网格铺一遍，越往右下越暗，笔触短而宽，一层叠一层。
    """
    layer = r.Layer(W, H)
    r.fill_polygon(layer, [(-20, -20), (W + 20, -20), (W + 20, H + 20), (-20, H + 20)], (44, 34, 30), 1.0)
    rng = random.Random(5)
    fig = canvas('ground')
    rows, cols = 15, 12
    index = 0
    for row in range(rows):
        for col in range(cols):
            x = -80.0 + (W + 160.0) * (col + 0.5) / cols + rng.uniform(-40.0, 40.0)
            y = -80.0 + (H + 160.0) * (row + 0.5) / rows + rng.uniform(-36.0, 36.0)
            lit = max(0.0, min(1.0, 1.0 - 0.50 * (0.50 * x / W + 0.50 * y / H)))
            tone = jitter(mix((24, 18, 16), (104, 86, 70), lit ** 1.30), 12.0, rng)
            length = rng.uniform(260.0, 540.0)
            angle = rng.uniform(-0.30, 0.30)
            tx, ty = math.cos(angle), math.sin(angle)
            fig.add_stroke(core.stroke_record(
                [(x - tx * length * 0.5, y - ty * length * 0.5), (x, y + rng.uniform(-5, 5)),
                 (x + tx * length * 0.5, y + ty * length * 0.5)],
                'brush', seed=800 + index, colour=hexed(tone), soft=1.0,
                height=rng.uniform(0.012, 0.050),
                bristle=0.36, bristle_pitch=rng.uniform(2.8, 4.6),
                colour_profile=[[v * 0.93 for v in tone], list(tone), [v * 0.95 for v in tone]],
                width_profile=[rng.uniform(80.0, 160.0)] * 3,
                alpha_profile=[rng.uniform(0.30, 0.56)] * 3,
                absolute_width=True, edge=rng.uniform(6.0, 14.0)), stage='line', layer='paint', note='')
            index += 1
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
    """整块布面都要落笔，而落点要**随机**。

    **规则网格是这一版剩下的毛病。** 第一版把「褶」当成了线，只在褶的中线上撒点，画面成了六条并列的面条；
    改成整幅铺满之后仍然读成一层层的鳞 —— 因为行距与横向步长都是固定的，笔触排成整齐的行列，圆头一个叠
    一个，像鱼鳞。苹果那一版是随机撒点的，所以它的圆头被相邻的笔盖住、看不出排列。这里改成同样的做法：
    三千二百个随机点，每点沿竖直方向画一笔（褶是竖直的），明暗由 `shade` 当场算出来。
    """
    rng = random.Random(seed)
    fig = canvas('cloth body')
    spots = []
    guard = 0
    while len(spots) < 3200 and guard < 80000:
        guard += 1
        y = rng.uniform(ROD_Y - 12.0, H + 8.0)
        left, right = edges(y)
        x = rng.uniform(left - 8.0, right + 8.0)
        value = shade(x, y)
        if value is None:
            continue
        spots.append((x, y, value))
    index = 0
    for x, y, value in spots:
        # **长宽比三比一，与苹果那支笔一致。** 旧笔是一百五十到三百三十长、二十二到三十六宽，七到十二比一，
        # 排下来是一列一列竖条 —— 布读成了一把面条。褶是竖直的，方向本来就对，错的是笔画太细。
        pigment = jitter(cloth_colour(value), 5.0, rng)
        weave = 1.0 + 0.08 * math.sin(y * 0.011 + x * 0.004)
        pigment = tuple(v * weave for v in pigment)
        length = rng.uniform(80.0, 190.0)
        drift = math.sin(y / 92.0) * rng.uniform(2.0, 8.0)
        points = [(x - drift * 0.5, y - length * 0.5),
                  (x, y),
                  (x + drift * 0.5, y + length * 0.5)]
        width = rng.uniform(26.0, 48.0)
        fig.add_stroke(core.stroke_record(
            points, 'brush', seed=index, colour=hexed(pigment), soft=0.8,
            colour_profile=[[v * 0.95 for v in pigment], list(pigment), [v * 0.93 for v in pigment]],
            height=width / 130.0 * rng.uniform(0.35, 0.75),
            bristle=0.38, bristle_pitch=rng.uniform(2.6, 4.0),
            width_profile=[width * 0.90, width, width * 0.92],
            alpha_profile=[rng.uniform(0.72, 0.86)] * 3,
            absolute_width=True, edge=rng.uniform(1.8, 4.0)), stage='line', layer='paint', note='')
        index += 1
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
