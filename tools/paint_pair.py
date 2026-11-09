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
    dark, mid, light = (30, 28, 38), (76, 72, 62), (120, 112, 96)
    body = pa.mix(dark, mid, value / 0.55) if value <= 0.55 else pa.mix(mid, light, (value - 0.55) / 0.45)
    if value < 0.30:
        body = pa.mix(body, (44, 46, 74), (0.30 - value) * 0.60)
    if value > 0.78:
        body = pa.mix(body, (222, 206, 176), (value - 0.78) * 0.80)
    return body


def table_cloth(picture, seed=1201):
    """铺在桌面上的一块布：一个高度场，笔触沿等高度线走。

    **这个函数没有被调用，而这是三次试出来的结论。** 第一次铺满画面下半部：它成了第三个主体，画面散掉。
    第二次压暗一档：它自己看着像一块布了，而放进画面里仍然比两只果子亮 —— 与杯子那两次一模一样。
    第三次缩成前景的一条边：边缘的锯齿全露出来，读成泡沫。

    第三条是不成立的根，值得记住：**一块布的边是一条被剪断的线**（布的边是剪出来的、折出来的），
    而这里所有形状的边都是笔触的自然收尾。苹果用这个足够 —— 它是圆的，圆没有边只有轮廓；鱼用这个也够 ——
    鱼身是软的。布不够，而补它需要一条「先定轮廓、再在轮廓里落笔」的路，那是另一件事。

    形体模型本身是对的：这是 `paint_fish` 那套机器的第二次使用 —— 高度场给形体，梯度给明暗，笔触沿等值线走。
    鱼的高度场是「到轮廓的距离」，这里的高度场是几组正弦叠出来的褶。两者除了「怎么算高度」之外一个参数都不用改。
    """
    rng = random.Random(seed)
    grid_x, grid_y = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
    # **布只露一条边。** 上一版让它从 742 铺到底，占了画面下半的三分之一 —— 它不再是背景，而成了第三个
    # 主体，画面因此散掉。一块能读成「桌沿」的布边只需要露出一百五十像素。
    top_edge = 946.0 + 26.0 * np.sin(grid_x * 0.0060) + 14.0 * np.sin(grid_x * 0.0170 + 1.7)
    inside = ((grid_y > top_edge)
              & (grid_x > 54.0 + 26.0 * np.sin(grid_y * 0.0050))
              & (grid_x < 1064.0 - 30.0 * np.sin(grid_y * 0.0045 + 0.8)))
    # **褶的频率要低。** 第一版三个正弦取 0.013 / 0.021 / 0.0075，叠出来是高密度的碎纹 —— 一块铺开的布
    # 是有几道大褶、中间摊平的，不是揉皱的纸。频率减半之后，剩下的面积才开始读成「布」而不是「雪地」。
    fold = (0.55 * np.sin(grid_x * 0.0060 + grid_y * 0.0020)
            + 0.30 * np.sin(grid_y * 0.0090 - grid_x * 0.0030)
            + 0.20 * np.sin((grid_x + grid_y) * 0.0035))
    fold = (fold - fold.min()) / (fold.max() - fold.min())
    grad_y, grad_x = np.gradient(fold)
    nx = -grad_x * 620.0
    ny = -grad_y * 620.0
    norm = np.sqrt(nx * nx + ny * ny + 1.0)
    lambert = (nx * -0.50 + ny * -0.58 + 1.15) / (norm * math.sqrt(1.909))
    tone = np.clip(0.20 + 0.95 * lambert, 0.0, 1.0)
    rows, cols = np.nonzero(inside)
    fig = project.Project(width=W, height=H, title='table cloth')
    for i in range(900):
        pick = rng.randrange(rows.size)
        y, x = int(rows[pick]), int(cols[pick])
        gyp, gxp = float(grad_y[y, x]), float(grad_x[y, x])
        scale = math.hypot(gxp, gyp) or 1.0
        tx, ty = -gyp / scale, gxp / scale
        if tx < 0.0:
            tx, ty = -tx, -ty
        spin = rng.uniform(-0.25, 0.25)
        tx, ty = tx * math.cos(spin) - ty * math.sin(spin), tx * math.sin(spin) + ty * math.cos(spin)
        pigment = pa.jitter(linen_colour(float(tone[y, x])), 6.0, rng)
        length = rng.uniform(110.0, 240.0)
        width = rng.uniform(22.0, 42.0)
        bend = rng.uniform(-0.10, 0.10) * length
        fig.add_stroke(core.stroke_record(
            [(x - tx * length * 0.5 - ty * bend, y - ty * length * 0.5 + tx * bend),
             (x, y),
             (x + tx * length * 0.5 + ty * bend, y + ty * length * 0.5 - tx * bend)],
            'brush', seed=4000 + i, colour=pa.hexed(pigment), soft=0.8,
            height=width / 130.0 * rng.uniform(0.30, 0.60),
            bristle=0.36, bristle_pitch=rng.uniform(2.6, 4.2),
            colour_profile=[[c * s for c in pigment] for s in (0.95, 1.00, 0.97)],
            width_profile=[width * 0.90, width, width * 0.92],
            alpha_profile=[rng.uniform(0.72, 0.86)] * 3,
            absolute_width=True, edge=rng.uniform(1.8, 4.0)), stage='line', layer='paint', note='')
    # 半透明叠上去：底下桌面的暗色透出来一点，布就不至于像一块贴上去的板。
    return r.blend(picture, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True), 'normal', 0.90)


def main():
    os.makedirs(OUT, exist_ok=True)
    picture = pa.ground(*BACK)
    picture = wall(picture)
    # **桌布没有进这张画，三次都没站住。** `table_cloth` 保留在这里是因为那三次的错误各不相同，而它们都是
    # 以后会再犯的：铺满下半部（成了第三个主体，画面散）、压暗之后仍然比果子亮（主体被压）、缩成前景一条边
    # （边缘的锯齿全露出来，像泡沫）。第三条是不成立的根 —— 一块布的边是一条被剪断的线，而这里所有形状的边
    # 都是笔触的自然收尾；苹果用这个足够，布不够。
    # picture = table_cloth(picture)
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
