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
#
# **And the pectoral was in the wrong place, which is a data error rather than a drawing one.** It sat at the far left
# end beside the tail, so the fish read as having two tail fins. A pectoral grows behind the gill cover, low on the
# flank, and sweeps back and down from there -- so its root moved to (902, 552) and its points run back and down from it.
BODY = [(168, 452), (238, 402), (326, 376), (430, 356), (556, 338), (700, 332), (826, 344),
        (930, 372), (1012, 414), (1064, 462), (1068, 508), (1030, 556), (944, 596),
        (846, 620), (726, 634), (594, 638), (468, 630), (356, 610), (272, 580), (200, 540), (162, 494)]
FIN = [(910, 546), (848, 596), (786, 646), (812, 664), (872, 620), (906, 578)]
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


def shading(relief, tilt=1.5):
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
    """银背、金侧、粉腹 —— 三段要有三种色相，不只是三档明度。

    **原来三段是同一个色相。** (34,38,48) / (172,162,150) / (208,204,190) 三个都是灰，只有深浅之分 —— 于是
    整条鱼是一块银灰，形体画得再准也只是一条灰色的鱼。真实的鱼体色是分带的：背脊偏青或偏褐，体侧银里透金，
    腹部泛粉。色相分开之后，同一条明度曲线读出来才是「一条鱼」，而不只是「一个亮的形体」。

    体侧那条虹彩带单独加：它在明度上不出众（正好在中调），所以按明度取色永远是灰的 —— 那是一处**只有色相
    能表达**的东西，而这一层以前根本不存在。
    """
    deep, mid, back = (44, 56, 60), (176, 158, 126), (238, 212, 188)
    body = mix(deep, mid, value / 0.55) if value <= 0.55 else mix(mid, back, (value - 0.55) / 0.55)
    # **过渡带要够宽才叫过渡。** 上一版虹彩只有 0.20 的强度和 0.10 的宽度，于是背与腹之间是一条直边 ——
    # 三段色相一分开，那条边界就露出来了。真实的鱼在明暗交界处有一条宽的、偏青的带，它既是色相也是过渡。
    iris = 0.38 * math.exp(-((value - 0.52) / 0.16) ** 2)
    body = mix(body, (116, 154, 148), iris)
    return jitter(body, 9.0, rng)


def canvas(title):
    return project.Project(width=W, height=H, title=title)


def ground():
    """背景刷满整张，与苹果那张同一个理由：二十几笔盖不住一块画布，剩下的地方就是一块没人碰过的空白。

    **`tools/oil_survey.py` 的 `within` 一列量的正是这件事** —— 这张鱼画到 2.4，是四张里最低的一张，而它最大
    的那块九万三千像素就在背景里。所以底色之上按网格铺一遍，越往右下越暗，笔触比原来短，因为一块画布是
    一层一层叠出来的，不是几条横杠扫过去的。
    """
    layer = r.Layer(W, H)
    r.fill_polygon(layer, [(-20, -20), (W + 20, -20), (W + 20, H + 20), (-20, H + 20)], (38, 34, 32), 1.0)
    rng = random.Random(11)
    fig = canvas('ground')
    rows, cols = 10, 16
    index = 0
    for row in range(rows):
        for col in range(cols):
            x = -80.0 + (W + 160.0) * (col + 0.5) / cols + rng.uniform(-40.0, 40.0)
            y = -80.0 + (H + 160.0) * (row + 0.5) / rows + rng.uniform(-30.0, 30.0)
            lit = max(0.0, min(1.0, 1.0 - 0.55 * (0.45 * x / W + 0.55 * y / H)))
            tone = jitter(mix((22, 19, 18), (86, 76, 66), lit ** 1.25), 12.0, rng)
            length = rng.uniform(240.0, 520.0)
            angle = rng.uniform(-0.30, 0.30)
            tx, ty = math.cos(angle), math.sin(angle)
            fig.add_stroke(core.stroke_record(
                [(x - tx * length * 0.5, y - ty * length * 0.5), (x, y + rng.uniform(-5, 5)),
                 (x + tx * length * 0.5, y + ty * length * 0.5)],
                'brush', seed=700 + index, colour=hexed(tone), soft=1.0,
                height=rng.uniform(0.012, 0.050),
                bristle=0.36, bristle_pitch=rng.uniform(2.8, 4.6),
                colour_profile=[[v * 0.93 for v in tone], list(tone), [v * 0.95 for v in tone]],
                width_profile=[rng.uniform(80.0, 160.0)] * 3,
                alpha_profile=[rng.uniform(0.30, 0.56)] * 3,
                absolute_width=True, edge=rng.uniform(6.0, 14.0)), stage='line', layer='paint', note='')
            index += 1
    return r.blend(layer, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True), 'normal', 1.0)


def fish_marks(seed=8181):
    """在轮廓内撒点，笔触沿鱼身的长轴走 —— 而体色沿这条轴也有自己的起伏。

    **上一轮在苹果上学到的两条，这里各修一个毛病。** 一是笔触要顺着形体的转：鱼身的高度场是「到轮廓的距离」，
    等高度线沿长轴平行，所以笔触该长、该水平 —— 旧版是长度二十八到八十六的水平短笔，三千四百条，方向本来
    就对，只是碎。二是颜色：旧版只由高度场决定，而高度场沿长轴几乎不变，于是整条鱼身是一条水平的长条同色
    （九万像素的块，`within` 2.4 的一半原因在这里）。现在另加一层沿长轴的连续起伏 —— 不是每条笔给一个随机
    偏移（苹果那一轮证明那会把颜色推成孤立的色点，落进量化格子的边界，块内反而笔笔相同），而是随位置走的
    斑驳，体侧本来就有。
    """
    rng = random.Random(seed)
    mask = mask_of(BODY)
    relief = height_of(mask)
    tone = shading(relief)
    gy, gx = np.gradient(relief)
    fig = canvas('fish body')
    rows, cols = np.nonzero(mask)
    index = 0
    for _ in range(1800):
        pick = rng.randrange(rows.size)
        y, x = int(rows[pick]), int(cols[pick])
        value = float(tone[y, x])
        mottle = 1.0 + 0.10 * math.sin(x * 0.0105 + y * 0.0042) + 0.06 * math.sin(x * 0.031 - y * 0.016)
        pigment = fish_colour(value, rng)
        pigment = (pigment[0] * mottle, pigment[1] * mottle * 1.005, pigment[2] * mottle * 0.990)
        # **方向由形体给，不由画布给。** 高度场的梯度指向脊，垂直于它的是等高度线 —— 体侧那些「顺着转」的
        # 线。旧版全都水平，于是笔触排成一列一列的横条；而一条鱼的等高度线在头尾两端是弯的。
        gyp, gxp = float(gy[y, x]), float(gx[y, x])
        scale = math.hypot(gxp, gyp) or 1.0
        tx, ty = -gyp / scale, gxp / scale
        if tx < 0.0:
            tx, ty = -tx, -ty
        spin = rng.uniform(-0.20, 0.20)
        tx, ty = tx * math.cos(spin) - ty * math.sin(spin), tx * math.sin(spin) + ty * math.cos(spin)
        # **长宽比要和苹果的笔一致。** 一百到二百六十长、十六到三十四宽是六比一，读出来是条纹；
        # 苹果那一版是六十到一百二十长、二十到三十六宽，三比一，读出来是一片。同一种笔，形状决定它读成什么。
        # **笔触的尺寸由形体的局部厚度决定。** 一条一百八十像素的笔落在鱼头那样薄的地方，两端会伸出轮廓，
        # 把头盖成一团灰絮 —— 那是上一版眼睛被埋掉的直接原因。薄处短而窄，厚处才放开。
        thin = math.sqrt(max(0.0, relief[y, x]))
        length = rng.uniform(80.0, 180.0) * (0.40 + 0.60 * thin)
        width = rng.uniform(24.0, 44.0) * (0.55 + 0.45 * thin)
        bend = rng.uniform(-0.10, 0.10) * length
        points = [(x - tx * length * 0.5 - ty * bend, y - ty * length * 0.5 + tx * bend),
                  (x, y),
                  (x + tx * length * 0.5 + ty * bend, y + ty * length * 0.5 - tx * bend)]
        fig.add_stroke(core.stroke_record(
            points, 'brush', seed=index, colour=hexed(pigment), soft=0.8,
            colour_profile=[[v * 0.94 for v in pigment], list(pigment), [v * 0.92 for v in pigment]],
            height=width / 140.0 * rng.uniform(0.4, 0.8),
            bristle=0.34, bristle_pitch=rng.uniform(2.6, 4.0),
            width_profile=[width * 0.88, width, width * 0.90],
            alpha_profile=[rng.uniform(0.70, 0.84)] * 3,
            absolute_width=True, edge=rng.uniform(1.6, 3.4)), stage='line', layer='paint', note='')
        index += 1
    return fig, mask, relief, tone


def fin_marks(seed=505):
    """鳍与远侧的那一片：**鳞条从根向外辐射，而鳍尖要透。**

    上一版的鳍读成一块白絮：笔触水平、颜色又取到了浅的那一头，落在形状上既没有方向也没有根。鳍的构造是从
    根部伸出去的一排细条，所以每一笔沿「这一点背离鳍心」的方向走，颜色也压暗一档 —— 鳍比身体薄，背面没有
    那么多光。

    **半透明不需要新机制，`alpha_profile` 早就够了。** 4.57 节说这要一个「不透明度跟局部厚度走」的东西，
    而厚度在这里本来就有数：`relief` 是到轮廓的距离归一化再开方，鳍尖上是零、根上接近一。所以 alpha 直接
    跟着它走 —— 鳍尖 0.22（背面的水和背景透得过来），鳍根 0.88。一条鳍的根连在身体上，那里不该透。
    """
    rng = random.Random(seed)
    fig = canvas('fins')
    # **辐射中心是根，不是质心。** 质心落在形状中央，笔触从那里朝四面八方散开 —— 读成一朵花。鳍条是从
    # 贴着身体的那条边长出来的，所以中心取在根上，每一条只朝一个方向去。三个鳍的根不在同一侧，所以各给一个。
    # **而笔触要按形状的尺寸缩放。** 尾鳍只有一百五十乘七十，给它的鳍条却和背鳍一样长，于是每一条都伸出轮廓
    # 之外，散成一把刺。它自己的尺寸是它自己的事。
    for shape, density, root, reach in ((FIN, 150, (910.0, 546.0), 0.72),
                                        (DORSAL, 170, (586.0, 338.0), 1.00),
                                        (TAIL, 200, (167.0, 474.0), 0.58)):
        mask = mask_of(shape)
        relief = height_of(mask, exponent=0.75)
        tone = shading(relief, tilt=0.6)
        rows, cols = np.nonzero(mask)
        cx0, cy0 = root
        for i in range(density):
            pick = rng.randrange(rows.size)
            y, x = int(rows[pick]), int(cols[pick])
            thin = math.sqrt(max(0.0, float(relief[y, x])))
            pigment = jitter(mix((58, 54, 56), (146, 138, 130), min(1.0, float(tone[y, x]))), 7.0, rng)
            dx, dy = x - cx0, y - cy0
            scale = math.hypot(dx, dy) or 1.0
            ux, uy = dx / scale, dy / scale
            spin = rng.uniform(-0.28, 0.28)
            ux, uy = ux * math.cos(spin) - uy * math.sin(spin), ux * math.sin(spin) + uy * math.cos(spin)
            # 鳍条要比上一版长：短笔从根部散开只是毛，长的才读成条。
            length = rng.uniform(34.0, 90.0) * (0.55 + 0.45 * thin) * reach
            alpha = 0.22 + 0.66 * thin
            fig.add_stroke(core.stroke_record(
                [(x - ux * length * 0.5, y - uy * length * 0.5), (x, y),
                 (x + ux * length * 0.5, y + uy * length * 0.5)], 'brush', seed=900 + i,
                colour=hexed(pigment), soft=0.8, height=0.20, bristle=0.30,
                width_profile=[rng.uniform(5, 11)] * 3, alpha_profile=[alpha * 0.82, alpha, alpha * 0.82],
                absolute_width=True, edge=rng.uniform(2.0, 4.2)), stage='line', layer='paint', note='')
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
