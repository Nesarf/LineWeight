"""Two apples in one picture: the first attempt here at a picture rather than a subject.

**Why this before more polish.** Every picture in `tools/` so far is one object on an empty field, and the measurement
that started this line said why that matters: seven oil still lifes read `p90` 149 to 606 and `within` 4.5 to 8.1,
while three single-object pictures of ours read `p90` 772 to 1640 and `within` 2.6 to 4.6. Part of that gap is not
brushwork at all -- **a still life is several things**, and each thing is its own colour region. One object cannot
produce that however well it is painted, and `AESTHETIC-LIBRARY.md` 4.58 spent a paragraph learning that the two
columns measure where the paint went, not how good it is.

So: a larger apple behind, a smaller one in front partly hiding it, one table they both sit on, and a contact shadow
where each meets it. **Nothing new is drawn.** `paint_apple.body_marks` takes a centre and a radius, so it is called
twice; the dip, stem and gloss passes are the same three again. The only new decisions are the arrangement and the
order of the passes -- which is the interesting part, because a picture is largely an order.
"""

import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lineweight import core, project          # noqa: E402
from lineweight import raster as r            # noqa: E402
import paint_apple as pa                      # noqa: E402

W, H = pa.W, pa.H
OUT = os.environ.get('PAIR_OUT') or os.path.join(os.getcwd(), 'pair')

# The larger one sits behind and to the right; the smaller one in front and to the left, so its silhouette cuts into
# the other's. That overlap is the thing a single-object picture cannot have.
BACK = (648.0, 512.0, 262.0)
FRONT = (428.0, 690.0, 186.0)
CUP = (186.0, 606.0, 56.0, 112.0)


def wet_drags(layer, cx, cy, radius, seed):
    """把已经铺上的颜料往笔走的方向拉开几笔 —— 苹果那张里同一个动作，只是这里每一只果子各来一遍。"""
    rng = random.Random(seed)
    for _ in range(8):
        start = rng.uniform(0.0, 2.0 * math.pi)
        reach = radius * rng.uniform(0.12, 0.70)
        points = []
        for k in range(6):
            angle = start + k * rng.uniform(0.11, 0.24)
            points.append((cx + reach * math.cos(angle) * 1.06, cy + reach * math.sin(angle) * 0.95))
        r.smudge(layer, points, radius=rng.uniform(24.0, 42.0), strength=rng.uniform(0.30, 0.55))


def apple_body(picture, cx, cy, radius, seed, dim=1.0, aspect=1.06, squash=0.95, lean=0.0):
    """一只果子的全部笔触：果身、湿拖、凹陷、梗、高光 —— 顺序就是遮挡的顺序。"""
    body = pa.body_marks(cx, cy, radius, seed, dim, aspect, squash, lean)
    layer = r.render_marks([m.to_dict() for m in body.marks], W, H, sweep=True)
    wet_drags(layer, cx, cy, radius, seed + 7)
    picture = r.blend(picture, layer, 'normal', 1.0)
    for extra in (pa.dip_marks(cx, cy, radius, seed + 1),
                  pa.stem_marks(cx, cy, radius, seed + 2),
                  pa.gloss_marks(cx, cy, radius, seed + 3)):
        picture = r.blend(picture,
                          r.render_marks([m.to_dict() for m in extra.marks], W, H, sweep=True), 'normal', 1.0)
    return picture


def wall(picture):
    """一堵墙，一面临画。

    **这张画之前没有房间。** 两只果子浮在一片深色里 —— 没有地面，也没有后面。而一幅静物的背景几乎总是一个
    平面：一堵墙、一块背板。它不需要画得像墙，只要比桌面亮一点、并且有一条不太直的边，眼睛就会把它读成
    「后面」。边线用正弦加一点抖动，因为一条水平的直线会把画面切成两半。
    """
    layer = r.Layer(W, H)
    rng = random.Random(2024)
    edge = [(float(x), 250.0 + 18.0 * math.sin(x * 0.0048)) for x in range(-40, W + 80, 40)]
    r.fill_polygon(layer, [(-40.0, -40.0)] + edge + [(W + 40.0, -40.0)], (70, 64, 56), alpha=0.78)
    fig = project.Project(width=W, height=H, title='wall')
    # **横着刷，不竖着刷。** 第一版是七十笔竖刷，画面背后出现了一排等距的柱子 —— 而一堵墙没有柱子。
    # 横向的大笔互相盖住，边线就软了，也不会留下规律。
    for i in range(46):
        y = rng.uniform(200.0, 390.0)
        x0 = rng.uniform(-260.0, W * 0.7)
        length = rng.uniform(380.0, 820.0)
        tone = pa.jitter(pa.mix((54, 50, 44), (98, 90, 78), rng.random()), 11.0, rng)
        fig.add_stroke(core.stroke_record(
            [(x0, y + rng.uniform(-8, 8)),
             (x0 + length * 0.5, y - rng.uniform(0.0, 16.0)),
             (x0 + length, y + rng.uniform(-10.0, 10.0))],
            'brush', seed=3000 + i, colour=pa.hexed(tone), soft=1.0,
            width_profile=[rng.uniform(150.0, 280.0)] * 3,
            alpha_profile=[rng.uniform(0.30, 0.52)] * 3,
            absolute_width=True, edge=rng.uniform(14.0, 26.0)), stage='line', layer='paint', note='')
    return r.blend(r.blend(picture, layer, 'normal', 1.0),
                   r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True), 'normal', 1.0)


def cup_colour(value):
    """陶土：暗处偏冷偏紫，亮处偏暖偏黄 —— 与布那张同一个道理，两头的色相要分开。

    **三段要压暗两档。** 第一版最亮取到 (236,210,176)，而圆柱正对观者的那一面占了可见面积的大半，于是整只
    杯子是一块几乎白的糖 —— 陶土色一档都没出来。压到 (190,166,136) 之后它自己看着是一只陶杯了，而放进画面
    里，它比两只果子都亮，成了主体的竞争者。静物里次要的东西要比主体暗，这是构图而不是颜色的问题；
    再压到 (146,126,102)。
    """
    dark, mid, light = (26, 24, 30), (90, 74, 60), (146, 126, 102)
    body = pa.mix(dark, mid, value / 0.58) if value <= 0.58 else pa.mix(mid, light, (value - 0.58) / 0.42)
    if value < 0.34:
        body = pa.mix(body, (44, 42, 66), (0.34 - value) * 0.55)
    return body


def cup(picture, cx, top, radius, height, seed=909):
    """一只杯子：圆柱，笔触沿母线走，明暗由法线算。

    **这是第一个既不是球、也不是「到轮廓的距离」能给的形体。** 圆柱的法线只随角度变、不随高度变，所以一支
    竖笔从口到底是一个颜色 —— 真实杯子上也正是这样：釉光是一条竖的，不是一块圆的。上面那两只果子用同心弧，
    因为球面的转是绕中心的；这里用竖笔，因为柱面的转是绕轴的。**同一个问题（「这一笔往哪个方向走」）在两个
    形体上有两个答案，而答案都不是调出来的，是形体的。**
    """
    rng = random.Random(seed)
    rim_b = 0.30 * radius
    # **口里先铺一层暗。** 杯子是开着的，从上往下看得到一个内壁；第一版没画，口沿那一圈白笔直接贴在杯身上，
    # 读成了一圈齿轮。内壁不需要细节，它只需要比口沿暗。
    mouth = r.Layer(W, H)
    r.fill_polygon(mouth, [(cx + radius * 0.97 * math.sin(a), top - rim_b * 0.97 * math.cos(a))
                           for a in (2.0 * math.pi * k / 48.0 for k in range(48))], (46, 38, 34), 0.92)
    picture = r.blend(picture, mouth, 'normal', 1.0)
    fig = project.Project(width=W, height=H, title='cup')
    light_x, light_z = -0.362, 0.832          # LIGHT 归一化之后的横、深两个分量
    for i in range(520):
        theta = rng.uniform(-math.pi * 0.5, math.pi * 0.5)
        face = math.cos(theta)
        if rng.random() > 0.22 + 0.78 * face:
            continue
        x = cx + radius * math.sin(theta)
        diffuse = max(0.0, light_x * math.sin(theta) + light_z * face)
        pigment = pa.jitter(cup_colour(diffuse), 5.0, rng)
        length = height * rng.uniform(0.82, 1.02)
        width = 9.0 + 30.0 * face
        mid = top + height * 0.5
        fig.add_stroke(core.stroke_record(
            [(x - 1.5, mid - length * 0.5), (x, mid), (x + 1.5, mid + length * 0.5)],
            'brush', seed=2000 + i, colour=pa.hexed(pigment), soft=0.7,
            height=width / 110.0 * rng.uniform(0.2, 0.4),
            bristle=0.32, bristle_pitch=rng.uniform(3.0, 5.0),
            colour_profile=[[c * s for c in pigment] for s in (0.96, 1.00, 1.03, 0.99, 0.95)],
            width_profile=[width] * 5,
            alpha_profile=[0.86, 0.94, 0.94, 0.94, 0.86],
            absolute_width=True, edge=rng.uniform(1.6, 3.0)), stage='line', layer='paint', note='')
    # 口沿：一圈短笔。它是这只杯子上唯一一条「横」的线，也是它读成圆的依据。笔要少、要细 —— 密了就成齿轮。
    for i in range(30):
        angle = 2.0 * math.pi * i / 30.0
        x = cx + radius * math.sin(angle)
        y = top - rim_b * math.cos(angle)
        pigment = pa.jitter(pa.mix((104, 86, 70), (172, 152, 128), 0.30 + 0.70 * max(0.0, math.cos(angle))),
                            4.0, rng)
        fig.add_stroke(core.stroke_record(
            [(x - radius * 0.11, y), (x, y - 2.0), (x + radius * 0.11, y)], 'brush', seed=2200 + i,
            colour=pa.hexed(pigment), soft=0.6, width_profile=[3.0, 4.0, 3.0],
            alpha_profile=[0.72, 0.86, 0.72], absolute_width=True, edge=1.4),
            stage='line', layer='paint', note='')
    return r.blend(picture, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True), 'normal', 1.0)


def linen_colour(value):
    """铺在桌上的亚麻：比挂着的那块暗一档，因为它躺着，受光的角度平。"""
    # **压暗一档，与杯子那两次是同一个教训。** 第一版取到 (206,196,172)，布成了画面最亮的东西 —— 主体被压
    # 到下面，画面上半是空的墙、下半是一块发光的布。铺在桌上的布是背景，它要比两只果子暗。
    dark, mid, light = (30, 28, 38), (62, 58, 52), (96, 90, 80)
    body = pa.mix(dark, mid, value / 0.55) if value <= 0.55 else pa.mix(mid, light, (value - 0.55) / 0.45)
    if value < 0.30:
        body = pa.mix(body, (44, 46, 74), (0.30 - value) * 0.60)
    if value > 0.78:
        body = pa.mix(body, (222, 206, 176), (value - 0.78) * 0.80)
    return body


def table_cloth(picture, seed=1201):
    """铺在桌面上的一块布：**先定轮廓，再在轮廓里落笔。**

    这是这条线上第一次这么做。前面每一个形体都是反过来的 —— 撒点、落笔，让边由笔触自己长出来。苹果可以
    （圆没有边只有轮廓），鱼可以（鱼身软、轮廓本来起伏），布不行：布的边是剪出来、折出来的一条线，一堆圆头
    笔触凑不出直线。三次尝试都栽在这里（4.62 节）：铺满下半部成了第三个主体、压暗之后仍比果子亮、缩成一条
    边则把锯齿全露出来读成泡沫。

    现在的做法把这个顺序倒过来：先算出布的上边缘（一条慢正弦加一条更细的），用它和画面的下边围成一个多边形，
    把撒在下半部的所有笔触 `r.clip` 到这个多边形里 —— 边因此是一条**确定的线**。再沿那条边画一圈窄笔，那是布
    的折边：它有厚度、比布面暗一点，而它同时把裁剪留下的锯齿盖住。

    形体模型没有变，仍是 `paint_fish` 那套：高度场给形体，梯度给明暗，笔触沿等值线走。鱼的高度场是「到轮廓
    的距离」，这里的高度场是几组正弦叠出来的褶。改进的只有「边从哪来」这一件事。
    """
    rng = random.Random(seed)
    # **边线要先密，才能直。** 第一版每二十像素取一个点，`fill_polygon` 的边因此是一串折线，轮廓笔沿它走
    # 出来是一圈荷叶边。点距降到八像素之后，折线短到看不见。
    edge = [(float(x), 730.0 + 30.0 * math.sin(x * 0.0055) + 15.0 * math.sin(x * 0.0140 + 2.1))
            for x in range(-60, W + 80, 8)]
    polygon = edge + [(float(W + 60), float(H + 60)), (-60.0, float(H + 60))]
    mask = r.Layer(W, H)
    r.fill_polygon(mask, polygon, (255, 255, 255), 1.0)
    grid_x, grid_y = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
    # **褶的频率要低。** 第一版三个正弦取 0.013 / 0.021 / 0.0075，叠出来是高密度的碎纹 —— 一块铺开的布
    # 是有几道大褶、中间摊平的，不是揉皱的纸。
    fold = (0.55 * np.sin(grid_x * 0.0060 + grid_y * 0.0020)
            + 0.30 * np.sin(grid_y * 0.0090 - grid_x * 0.0030)
            + 0.20 * np.sin((grid_x + grid_y) * 0.0035))
    # **布的边会堆起来。** 一块布从桌面上翻上来的时候，靠近边的那一带积着一道隆起 —— 这不是装饰，是布的形状
    # 本身；少了它，布读成一张贴在桌上的纸。而褶的明暗也跟着调到能看见：梯度乘数从 620 到 900，
    # 因为压暗之后的色阶窄了，同样的起伏在暗色上显得更小。
    top_line = 730.0 + 30.0 * np.sin(grid_x * 0.0055) + 15.0 * np.sin(grid_x * 0.0140 + 2.1)
    fold = fold + 0.85 * np.exp(-((grid_y - top_line) / 54.0) ** 2)
    fold = (fold - fold.min()) / (fold.max() - fold.min())
    grad_y, grad_x = np.gradient(fold)
    nx = -grad_x * 900.0
    ny = -grad_y * 900.0
    norm = np.sqrt(nx * nx + ny * ny + 1.0)
    lambert = (nx * -0.50 + ny * -0.58 + 1.15) / (norm * math.sqrt(1.909))
    tone = np.clip(0.20 + 0.95 * lambert, 0.0, 1.0)
    fig = project.Project(width=W, height=H, title='table cloth')
    for i in range(1500):
        x = rng.uniform(-50.0, W + 50.0)
        y = rng.uniform(660.0, H + 50.0)
        iy = int(min(H - 1, max(0, round(y))))
        ix = int(min(W - 1, max(0, round(x))))
        gyp, gxp = float(grad_y[iy, ix]), float(grad_x[iy, ix])
        scale = math.hypot(gxp, gyp) or 1.0
        tx, ty = -gyp / scale, gxp / scale
        if tx < 0.0:
            tx, ty = -tx, -ty
        spin = rng.uniform(-0.25, 0.25)
        tx, ty = tx * math.cos(spin) - ty * math.sin(spin), tx * math.sin(spin) + ty * math.cos(spin)
        pigment = pa.jitter(linen_colour(float(tone[iy, ix])), 6.0, rng)
        length = rng.uniform(110.0, 240.0)
        width = rng.uniform(22.0, 42.0)
        bend = rng.uniform(-0.10, 0.10) * length
        fig.add_stroke(core.stroke_record(
            [(x - tx * length * 0.5 - ty * bend, y - ty * length * 0.5 + tx * bend),
             (x, y),
             (x + tx * length * 0.5 + ty * bend, y + ty * length * 0.5 - tx * bend)],
            'brush', seed=4000 + i, colour=pa.hexed(pigment), soft=0.8,
            # **被裁的图层不该带厚度。** `clip` 把 relief 一起裁了（否则厚度留在形状外），可是硬裁本身在边界
            # 上留一道悬崖：里边有值、外边是零，而 `light` 读的就是梯度 —— 于是那条边被画成一道亮线，比轮廓笔
            # 亮得多。布的凹凸已经由高度场的明暗给足了，这一层不需要再加厚度。
            bristle=0.36, bristle_pitch=rng.uniform(2.6, 4.2),
            colour_profile=[[c * s for c in pigment] for s in (0.95, 1.00, 0.97)],
            width_profile=[width * 0.90, width, width * 0.92],
            alpha_profile=[rng.uniform(0.72, 0.86)] * 3,
            absolute_width=True, edge=rng.uniform(1.8, 4.0)), stage='line', layer='paint', note='')
    picture = r.blend(picture, r.clip(r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True), mask),
                      'normal', 1.0)
    # **折边是布上唯一一条硬线，而它同时盖住裁剪的锯齿。** 一条布边有厚度，所以它比布面暗一档、宽九个像素。
    rim = project.Project(width=W, height=H, title='cloth rim')
    for i in range(len(edge) - 1):
        x0, y0 = edge[i]
        x1, y1 = edge[i + 1]
        # **折边要比布面暗，不是比布面亮。** 第一版取 (54,50,44) 到 (104,96,82)，而上限比布面最亮的 96 还高
        # —— 于是在布的暗处那一圈读成一条白线。折边是背着光的那一褶，它在色的暗端。
        tone_here = pa.jitter(pa.mix((36, 33, 30), (74, 68, 60), rng.random()), 5.0, rng)
        rim.add_stroke(core.stroke_record(
            [(x0, y0), ((x0 + x1) * 0.5, (y0 + y1) * 0.5 + 3.0), (x1, y1)], 'brush', seed=5000 + i,
            colour=pa.hexed(tone_here), soft=0.6, width_profile=[6.0, 8.0, 6.0],
            alpha_profile=[0.88, 0.96, 0.88], absolute_width=True, edge=1.6),
            stage='line', layer='paint', note='')
    return r.blend(picture, r.render_marks([m.to_dict() for m in rim.marks], W, H, sweep=True), 'normal', 1.0)


def main():
    os.makedirs(OUT, exist_ok=True)
    picture = pa.ground(*BACK)
    picture = wall(picture)
    # **桌布回来了，而它回来靠的是「先定轮廓」。** 前三次都栽在「边由笔触自己长出来」这件事上 —— 布的边是
    # 剪出来的一条线，一堆圆头笔触凑不出直线。现在先算出那条边缘、把笔触裁进去、再沿边画一圈折边。
    picture = table_cloth(picture)
    # **两道阴影都要在两只果子之前。** 第一版按「一只果子一整套」来排：后一只的地面阴影、后一只的果身、
    # 前一只的地面阴影、前一只的果身 —— 于是前一只的阴影压在后一只的果身上，后面那只被绕了一圈黑环，
    # 前面那只像在发光。阴影落在桌面上，两只果子都在桌面上方，所以阴影必须全部排在果身之前。
    picture = r.blend(picture, pa.table_shadow(*BACK), 'normal', 1.0)
    picture = r.blend(picture, pa.table_shadow(*FRONT), 'normal', 1.0)
    # **第三样东西，才能量出桌面有多大。** 两只果子只给了「前和后」，没有给「左和右」也没有给尺度；
    # 一只小杯子在左边，桌面的宽度就有了参照，而它的投影把桌面从「一片暗」变成「一块地」。
    picture = r.blend(picture, pa.table_shadow(CUP[0], CUP[1] + CUP[3] - 26.0, CUP[2] * 1.05), 'normal', 1.0)
    picture = cup(picture, *CUP)
    # **两个果子要有两个形。** 后面那只更圆、略朝右歪；前面那只更扁、朝左歪。椭圆率与剪切都由
    # `body_marks` 的三个新参数给，而它们默认就是原来写死的那两个数。
    picture = apple_body(picture, *BACK, 20261106, 0.84, 1.02, 0.99, 0.035)
    picture = apple_body(picture, *FRONT, 771103, 1.0, 1.10, 0.90, -0.060)
    path = os.path.join(OUT, 'pair.png')
    r.save_png(r.light(picture, direction=(-0.50, -0.58, 1.15), strength=0.34, tilt=1.15), path,
               background=(22, 16, 13))
    print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
