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

from lineweight import core, pigment, project    # noqa: E402
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
# **And the caudal peduncle did not narrow, which is the same kind of error as the pectoral.** The outline went from
# its widest point to the tail root losing only a third of its height -- a hundred and eleven against three hundred
# and two -- so it read as one oval mass with a fin stuck on the end rather than as a body that joins a tail. What a
# fish actually does is the thing this file cannot cite a number for; what it can say is that the narrowing was the
# one thing the outline was not doing at all. The four lower points at the left moved up and the upper ones down, and
# the tail fin's root moved with them, because it is attached to this outline and not to the old one.
BODY = [(168, 444), (238, 428), (326, 386), (430, 356), (556, 338), (700, 332), (826, 344),
        (930, 372), (1012, 414), (1064, 462), (1068, 508), (1030, 556), (944, 596),
        (846, 620), (726, 634), (594, 638), (468, 630), (356, 600), (272, 556), (200, 510), (162, 486)]
FIN = [(910, 546), (848, 596), (786, 646), (812, 664), (872, 620), (906, 578)]
TAIL = [(168, 446), (58, 430), (22, 462), (52, 496), (166, 484)]
DORSAL = [(470, 336), (520, 306), (588, 296), (660, 304), (700, 336), (586, 340)]
# **The dorsal fin's root is a line, not a point.** `fin_marks` radiates from a root for the pectoral and the tail, and
# that is right for them: a pectoral springs from one attachment and a tail fin from a short one. The dorsal springs
# from the whole length of the back, so radiating from its centre produced a fan of bristles, and the bristles were
# longer than the fin was tall. These two edges are the fin as a strip of membrane -- the root follows the back, the
# tip is the outer curve -- and a ray is a mark that spans between them.
DORSAL_ROOT = [(470, 336), (586, 340), (700, 336)]
DORSAL_TIP = [(470, 336), (520, 306), (588, 296), (660, 304), (700, 336)]
EYE = (1002, 452)

# **三段体色的着色力，不是三段明度。** 背脊那管深色是透明的，一点就压住整片；腹部的白是弱色，要加很多才推得
# 动同样的距离。等权的四行 `mix` 让暗部亮得太早、腹部白得太快，改成按这三个数加权之后，过渡带才落在形体真正
# 转过弯的地方（见 AESTHETIC-LIBRARY 4.72 与 `lineweight/pigment.py`）。
DEEP_STRENGTH = 0.82
MID_STRENGTH = 0.50
BACK_STRENGTH = 0.30


def mask_of(points):
    image = Image.new('L', (W, H), 0)
    ImageDraw.Draw(image).polygon(points, fill=255)
    return np.asarray(image) > 127


def along(points, x):
    """在一条 x 单调的折线上按 x 取 y —— 背鳍就是以两条这样的线给出的。"""
    if x <= points[0][0]:
        return float(points[0][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return float(y0) + float(y1 - y0) * (x - x0) / float(x1 - x0)
    return float(points[-1][1])


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


def fish_colour(value, rng, amount=9.0):
    """银背、金侧、粉腹 —— 三段要有三种色相，不只是三档明度。

    **原来三段是同一个色相。** (34,38,48) / (172,162,150) / (208,204,190) 三个都是灰，只有深浅之分 —— 于是
    整条鱼是一块银灰，形体画得再准也只是一条灰色的鱼。真实的鱼体色是分带的：背脊偏青或偏褐，体侧银里透金，
    腹部泛粉。色相分开之后，同一条明度曲线读出来才是「一条鱼」，而不只是「一个亮的形体」。

    体侧那条虹彩带单独加：它在明度上不出众（正好在中调），所以按明度取色永远是灰的 —— 那是一处**只有色相
    能表达**的东西，而这一层以前根本不存在。

    **三段之间原来按「舀了多少」插值，那是错的。** 背是透明的深色，一点就能压住整片；腹是白的，弱，要加很
    多才推得动。等权插值等于假设两管颜料一样强，于是暗部亮得太早、腹部白得太快。现在按着色力走（4.72 那一
    节，`lineweight/pigment.py`）：深这一端强、腹这一端弱，过渡带于是落在它们各自真实的位置上。
    """
    deep, mid, back = (44, 56, 60), (176, 158, 126), (238, 212, 188)
    if value <= 0.55:
        body = pigment.mix_by_strength(deep, mid, value / 0.55, DEEP_STRENGTH, MID_STRENGTH)
    else:
        body = pigment.mix_by_strength(mid, back, (value - 0.55) / 0.55, MID_STRENGTH, BACK_STRENGTH)
    # **过渡带要够宽才叫过渡。** 上一版虹彩只有 0.20 的强度和 0.10 的宽度，于是背与腹之间是一条直边 ——
    # 三段色相一分开，那条边界就露出来了。真实的鱼在明暗交界处有一条宽的、偏青的带，它既是色相也是过渡。
    iris = 0.38 * math.exp(-((value - 0.52) / 0.16) ** 2)
    body = mix(body, (116, 154, 148), iris)
    return jitter(body, amount, rng)


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
    # 贴着身体的那条边长出来的，所以中心取在根上，每一条只朝一个方向去。胸鳍与尾鳍的根不在同一侧，各给一个。
    # **而笔触要按形状的尺寸缩放。** 尾鳍只有一百五十乘七十，给它的鳍条却和背鳍一样长，于是每一条都伸出轮廓
    # 之外，散成一把刺。它自己的尺寸是它自己的事 —— 背鳍按同一个道理拆出去了，见下面的注释。
    for shape, density, root, reach in ((FIN, 150, (910.0, 546.0), 0.72),
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
    # **背鳍：根是一条线，鳍条跨在这条线与外缘之间。** 上一版给它一个「根点」、让笔从那里向四面八方辐射，于是
    # 它读成一把毛刷；而 34–90 长的笔落在一片只有四十几像素高的膜上，两端都伸出轮廓。鳍条的长度不是常数，它
    # 就是这一处的鳍高，所以每一笔自己算。
    mask = mask_of(DORSAL)
    relief = height_of(mask, exponent=0.75)
    tone = shading(relief, tilt=0.6)
    # **膜先于条。** 上一版只有鳍条，于是一片鱼鳍读成一排悬着的竖线 —— 鳍本来是有底的，条是压在底上的。先横
    # 着铺几条盖住整片，条才有东西可以落。
    for i in range(7):
        across = (i + 0.5) / 7.0
        stations = []
        for k in range(5):
            x0 = 474.0 + 220.0 * k / 4.0
            y_root = along(DORSAL_ROOT, x0)
            y_tip = along(DORSAL_TIP, x0)
            stations.append((x0, y_tip + (y_root - y_tip) * across))
        fig.add_stroke(core.stroke_record(
            stations, 'brush', seed=1080 + i, colour='#332f30', soft=1.0, height=0.10,
            width_profile=[22.0, 26.0, 21.0], alpha_profile=[0.12, 0.17, 0.12],
            absolute_width=True, edge=9.0), stage='line', layer='paint', note='')
    for i in range(150):
        x0 = rng.uniform(478.0, 692.0)
        y_root = along(DORSAL_ROOT, x0)
        y_tip = along(DORSAL_TIP, x0)
        fin_height = y_root - y_tip
        if fin_height < 7.0:
            continue
        lean = (x0 - 586.0) / 118.0 * 0.12
        tip_x = x0 + lean * fin_height
        s = rng.uniform(0.0, 1.0)
        cx = tip_x + (x0 - tip_x) * s
        cy = y_tip + fin_height * s
        column, row = int(round(cx)), int(round(cy))
        if not (0 <= row < H and 0 <= column < W) or not mask[row, column]:
            continue
        thin = math.sqrt(max(0.0, float(relief[row, column])))
        pigment = jitter(mix((58, 54, 56), (146, 138, 130), min(1.0, float(tone[row, column]))), 7.0, rng)
        length = fin_height * rng.uniform(0.72, 1.06)
        ux, uy = x0 - tip_x, y_root - y_tip
        norm = math.hypot(ux, uy) or 1.0
        ux, uy = ux / norm, uy / norm
        alpha = 0.13 + 0.48 * thin
        fig.add_stroke(core.stroke_record(
            [(cx - ux * length * 0.5, cy - uy * length * 0.5), (cx, cy),
             (cx + ux * length * 0.5, cy + uy * length * 0.5)], 'brush', seed=1100 + i,
            colour=hexed(pigment), soft=0.8, height=0.18, bristle=0.26,
            width_profile=[rng.uniform(3.4, 7.4)] * 3,
            alpha_profile=[alpha * 0.78, alpha, alpha * 0.72],
            absolute_width=True, edge=rng.uniform(1.8, 3.4)), stage='line', layer='paint', note='')
    return fig


def head_marks(seed=610):
    """头上的两个结构：**一道鳃盖，一张嘴。**

    在这两笔之前，这条鱼唯一能读成「头」的地方是那只眼，而眼睛是贴在轮廓最前端的一小块暗 —— 于是整条形状读
    成一块扁的卵形，眼睛只是旁边的一个斑点。真实的鱼头有两个明确的分界：**鳃盖**把头和身体分开（它的后缘是
    一条从背侧下来、弯向尾部的弧，前面软、后面硬），**嘴**把吻端收住（口裂是一条短而深的横缝，上唇压在下唇
    上，所以缝的上方有一条受光的边）。

    两样都是明暗，不是轮廓线：鳃盖的后缘是一道暗，紧挨着它前方是一道亮；嘴是一条暗缝加一条亮边。这也是为什
    么它们各自只有两笔 —— 一条明、一条暗，笔画多了就变成描边，而描边正是这张图一直在躲的东西。
    """
    fig = canvas('head')
    # 鳃盖后缘：从背侧下来，弯向尾部。**暗的那一笔要落在尾侧，不是头侧** —— 盖片投在身体上的影在它后面，
    # 而盖片自己的边缘受光。第一版把亮笔放在暗笔的头侧，于是两笔中间夹着的正好是那条该硬的后缘；而它落在体侧
    # 的暗部里，一道暗线在暗部读成一串点。暗部要靠「亮」来说结构。
    #
    # **而 `soft` 在细笔上会把笔变成一串珠子，这一条是放大五倍才看清的。** 笔是按 dab 铺的，相邻两个 dab 的
    # 间距是直径的七成，梯形横截面重叠三成刚好填满；`soft` 把横截面换成钟形，边缘的权重掉到近乎零，那三成的
    # 重叠就不够了 —— 于是一条六到十一像素宽的笔在画面上是一排分开的圆。`soft` 是给宽笔用的，细笔不该有。
    fig.add_stroke(core.stroke_record(
        [(978, 404), (958, 452), (964, 508), (988, 554)], 'brush', seed=610,
        colour='#161c1e', soft=0.25,
        width_profile=[7.0, 13.0, 13.0, 6.0], alpha_profile=[0.34, 0.58, 0.56, 0.30],
        absolute_width=True, edge=2.0), stage='line', layer='paint', note='')
    fig.add_stroke(core.stroke_record(
        [(992, 410), (972, 456), (978, 504), (1000, 546)], 'brush', seed=611,
        colour='#ded4bc', soft=0.25,
        width_profile=[5.0, 9.0, 9.0, 5.0], alpha_profile=[0.24, 0.44, 0.42, 0.22],
        absolute_width=True, edge=2.4), stage='line', layer='paint', note='')
    # 嘴：暗缝在上唇下面，亮边在上唇上面。**第一版太小了** —— 三笔加起来不到二十像素长、最宽五像素，落在
    # 一条一千四百像素宽的画上就是吻端的一个污点，而嘴是让人读出「这一头是头」的第二个东西。
    fig.add_stroke(core.stroke_record(
        [(1038, 494), (1052, 499), (1064, 507)], 'brush', seed=620,
        colour='#111114', soft=0.2,
        width_profile=[6.0, 9.0, 6.0], alpha_profile=[0.55, 0.82, 0.60],
        absolute_width=True, edge=1.2), stage='line', layer='paint', note='')
    fig.add_stroke(core.stroke_record(
        [(1036, 488), (1051, 493), (1062, 501)], 'brush', seed=621,
        colour='#e0d8c4', soft=0.25,
        width_profile=[3.2, 5.0, 3.6], alpha_profile=[0.22, 0.40, 0.26],
        absolute_width=True, edge=2.0), stage='line', layer='paint', note='')
    return fig


def eye_marks(seed=77):
    """一只眼：**四笔，不是四十笔。**

    第一版是两个同心圆加一个白点 —— 二十四段折线、宽度处处相同、颜色处处相同，放大看就是三个几何图元叠在
    一起，那是路径不是笔。第二版走到另一个极端：眼窝十六笔、虹膜十四笔、瞳八笔，每一笔都是一小段 ——
    放大看是一团乱笔，眼睛读不出来了。

    **眼睛是一个小尺度的东西，它只有四笔**：上眼睑一条弧（它压在眼球上缘，让眼睛被盖住而不是贴上去）、
    瞳一个不圆的黑、虹膜一条半月形的亮、高光一点。笔的形状由它自己的宽度剖面与那条弧决定 ——
    把一笔拆成三十笔不会让它更像手画的，只会让它更小、更碎。

    这一条与 4.63 的轮廓路是同一件事的两面：那条路给了硬的边（布需要），这里要的正好相反 ——
    圆不能有边，只能有笔；而「笔」是一笔，不是一堆笔画出来的边。
    """
    rng = random.Random(seed)
    fig = canvas('eye')
    cx, cy = EYE
    # 上眼睑：一条压下来的弧。它要比瞳高，压上去就成了两个洞。
    fig.add_stroke(core.stroke_record(
        [(cx - 22.0, cy - 5.0), (cx - 5.0, cy - 17.0), (cx + 14.0, cy - 14.0), (cx + 21.0, cy - 5.0)],
        'brush', seed=300, colour='#2a2426', soft=0.9,
        width_profile=[7.0, 13.0, 12.0, 6.0], alpha_profile=[0.55, 0.90, 0.86, 0.50],
        absolute_width=True, edge=2.4), stage='line', layer='paint', note='')
    # 瞳：一个不圆的黑，一笔。它要比上眼睑低几像素，否则两条暗笔连成一个钩。
    fig.add_stroke(core.stroke_record(
        [(cx - 9.5, cy + 2.5), (cx - 4.0, cy - 5.0), (cx + 4.5, cy - 4.0), (cx + 9.0, cy + 5.0)],
        'brush', seed=310, colour='#17131a', soft=0.8,
        width_profile=[7.0, 14.0, 14.0, 7.0], alpha_profile=[0.80, 0.96, 0.96, 0.78],
        absolute_width=True, edge=1.8), stage='line', layer='paint', note='')
    # 虹膜：瞳的右下一条半月形的亮。
    fig.add_stroke(core.stroke_record(
        [(cx + 2.0, cy + 11.0), (cx + 8.0, cy + 7.0), (cx + 11.0, cy + 1.0)], 'brush', seed=320,
        colour=hexed(jitter((188, 176, 156), 6.0, rng)), soft=0.8,
        width_profile=[3.0, 6.0, 3.0], alpha_profile=[0.35, 0.72, 0.30],
        absolute_width=True, edge=1.6), stage='line', layer='paint', note='')
    # 高光：一点，斜的，不落在正中。
    fig.add_stroke(core.stroke_record(
        [(cx - 5.0, cy + 0.0), (cx - 1.5, cy - 3.0)], 'brush', seed=330,
        colour='#fff8ec', soft=0.7, width_profile=[5.0, 4.0],
        alpha_profile=[0.94, 0.86], absolute_width=True, edge=1.4),
        stage='line', layer='paint', note='')
    return fig


def side_structure(mask, relief, tone, seed=4040):
    """体侧的第二层：**一排鳞，一条侧线 —— 第一层说这一片有多亮，第二层说这一片是什么做的。**

    第一层的一千八百笔是按密度撒的，`smudge` 再把它们拖成一片；那片东西的明度是对的，但它没有构造 —— 一条
    鱼和一块石头的区别不在明度上。这一层只做两件事，而两件都不是「再撒一些笔」：

    **鳞是排出来的，不是撒出来的。** 沿体轴的列、从背到腹的行，列距本身就是鳞片的大小，所以头端最大、尾柄最
    小 —— 一个撒点的循环写不出这件事，因为撒点没有「相邻的两片」这个概念。列还要斜着错开，真实的鳞序是斜行
    的瓦片，不是方格。

    **可见度由光决定，不由位置决定。** 鳞片在明暗交界带最清楚，因为斜掠的光让每一片的边缘都投了影；受光面
    上它们是平的，暗面里它们沉进阴影。所以 alpha 跟着 `tone` 走一个以交界值为中心的钟形 —— 同一条鱼上，有
    些地方二百片鳞都看得见，有些地方一片都看不见。**这不是「少画几笔」，是那个位置的鳞本来就不显。**

    **每片鳞是一笔，笔里有明暗。** 起笔在受光的上缘，收笔在压暗的下缘，`colour_profile` 三档一次给完。把一片
    鳞拆成「轮廓 + 填充」会得到一个色块，而一笔带明暗的弧读起来才是瓦片。

    侧线是体侧唯一一条横穿整个身体的结构线，它不是一个色调问题：一排小孔，多数反光、少数是暗的，沿体轴从鳃
    盖一直走到尾柄。
    """
    rng = random.Random(seed)
    top_of = np.argmax(mask, axis=0)
    bot_of = H - 1 - np.argmax(mask[::-1, :], axis=0)
    gy, gx = np.gradient(relief)
    fig = canvas('scales')
    index = 0
    x = 240.0
    while x < 934.0:
        column = int(round(x))
        if not mask[:, column].any():
            x += 12.0
            continue
        top = float(top_of[column])
        bot = float(bot_of[column])
        span = bot - top
        # **列距就是鳞片的大小。** 尾柄上的鳞小，头侧的鳞大，所以同一个循环在两端给出两种尺寸 —— 一条鱼身上
        # 本来就没有两片一样大的鳞，而「一样大」是上一版所有笔触共同的毛病。
        step = 14.0 + 8.0 * (x - 240.0) / 694.0
        rows = max(2, int(round(span / (step * 0.94))))
        for j in range(rows):
            y = top + span * (j + 0.5) / rows
            # **每一片的位置都要抖，而且要有缺片。** 严格的行列加一个线性剪切，读出来是一张格子布；鳞片恰恰是
            # 最不该归整的东西 —— 真的鳞会缺、会挤、会有大半片被前一片压住。
            if rng.random() < 0.13:
                continue
            y_use = y + rng.uniform(-1.7, 1.7)
            x_use = x + 0.40 * (y - (top + bot) * 0.5) + rng.uniform(-1.7, 1.7)
            column_use = int(round(x_use))
            row_use = int(round(y_use))
            if not (0 <= column_use < W and 0 <= row_use < H) or not mask[row_use, column_use]:
                continue
            # **侧线穿过鳞片，所以那一带上不长鳞。** 侧线的孔本来就是在鳞上开的洞；把鳞铺满之后再用一条线去
            # 盖，盖不住 —— 六百多片 alpha 零点四的弧比它亮。留一条空带，侧线才有地方存在。
            line_y = (top + bot) * 0.5 - 0.16 * span
            if abs(y_use - line_y) < span * 0.055:
                continue
            value = float(tone[row_use, column_use])
            # **可见度不能只以一个明度为中心。** 第一版是 `exp(-((v-0.52)/0.30)^2)`，于是鳞只长在 0.52 那条等值
            # 线附近 —— 而这条鱼的中线明度是零点九五、腹缘是零点二，那条线只在上缘一小块出现过，整片体侧于是
            # 一片空白。真实的情况是：鳞在体侧到处都有，受光面与暗面只是「弱」，交界带才是「强」。所以给一个
            # 底、在交界带加一个峰，而不是拿钟形当唯一的判据。
            visible = 0.18 + 0.82 * math.exp(-((value - 0.52) / 0.24) ** 2)
            pigment = fish_colour(value, rng, amount=4.0)
            gyp, gxp = float(gy[row_use, column_use]), float(gx[row_use, column_use])
            scale_g = math.hypot(gxp, gyp) or 1.0
            # 沿体轴的是切线，横跨体轴的是法线 —— 一片鳞横着铺，它的上缘是一条横跨的弧。
            tx, ty = -gyp / scale_g, gxp / scale_g
            if tx < 0.0:
                tx, ty = -tx, -ty
            nx, ny = -ty, tx
            # **鳞是一片瓦的上缘，不是一片填充。** 上一版把每片画成一条宽笔，六百多片连起来是一层均匀的壳，
            # 读成格子布；真的鳞在画面上只留下它自己的边缘 —— 上缘受光，下缘被后一片压住。所以笔是细的弧。
            # **而弧要真的弯。** 弯度原来是一个固定的 0.22 倍列距，落在十几像素的弧长上几乎是直线，于是六百
            # 条短划线读成一片被雨淋过的墙。弯度该跟着弧长走：一段瓦片的上缘，弧高大约是它自己的一半。
            length = step * rng.uniform(0.86, 1.22)
            bend = length * rng.uniform(0.34, 0.54)
            points = [(x_use - nx * length * 0.5 + tx * bend, y_use - ny * length * 0.5 + ty * bend),
                      (x_use + tx * bend, y_use + ty * bend),
                      (x_use + nx * length * 0.5 + tx * bend * 0.72,
                       y_use + ny * length * 0.5 + ty * bend * 0.72)]
            alpha = 0.40 * visible * rng.uniform(0.72, 1.12)
            fig.add_stroke(core.stroke_record(
                points, 'brush', seed=1400 + index, colour=hexed(pigment), soft=0.7,
                colour_profile=[[min(255.0, c * 1.18 + 8.0) for c in pigment], list(pigment),
                                [c * 0.78 for c in pigment]],
                bristle=0.14, bristle_pitch=3.2,
                width_profile=[rng.uniform(2.0, 2.8), rng.uniform(3.0, 4.0), rng.uniform(1.7, 2.6)],
                alpha_profile=[alpha * 0.66, alpha, alpha * 0.80],
                absolute_width=True, edge=1.2), stage='line', layer='paint', note='')
            index += 1
        x += step
    # 侧线：一排孔，**多数是暗的**，偶尔一个反光。
    #
    # 第一版把它做成了一条亮线：颜色 `1.26x + 12` 在银色的体侧上直接顶到白，间距又只有六到九像素、每笔七像素
    # 长，于是它连成了一条虚线 —— 而它正好落在明暗交界上，读出来是一道拼缝。真实的侧线是一排小孔，孔自己带阴
    # 影，所以主体比周围暗，只有少数被光正对着的孔发亮；孔与孔之间是断开的，位置也不在一条直线上。
    dash = 0
    line_x = 928.0
    while line_x > 244.0:
        column = int(round(line_x))
        if mask[:, column].any():
            top = float(top_of[column])
            bot = float(bot_of[column])
            line_y = (top + bot) * 0.5 - 0.16 * (bot - top)
            if mask[int(line_y), column]:
                value = float(tone[int(line_y), column])
                base = fish_colour(value, rng, amount=3.0)
                if dash % 4 == 3:
                    pore = [min(255.0, c * 1.14 + 6.0) for c in base]
                    alpha = 0.26
                else:
                    pore = [c * 0.72 for c in base]
                    alpha = 0.34
                wobble = rng.uniform(-2.4, 2.4)
                fig.add_stroke(core.stroke_record(
                    [(line_x + 3.2, line_y + wobble - 1.0), (line_x, line_y + wobble),
                     (line_x - 2.6, line_y + wobble + 1.2)],
                    'brush', seed=1700 + dash, colour=hexed(pore), soft=0.7,
                    width_profile=[1.9, 2.6, 1.6], alpha_profile=[alpha * 0.7, alpha, alpha * 0.5],
                    absolute_width=True, edge=1.2), stage='line', layer='paint', note='')
        dash += 1
        line_x -= 13.0 - 4.0 * (928.0 - line_x) / 684.0
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
    # **第二层落在湿拖之后。** 鳞与侧线是这个形体上的构造，被 `smudge` 拖过一遍就又是一片没有方向的糊；而第一
    # 层要的正是那点糊 —— 两层先后不是排版问题，是它们各自该受什么处理。
    scales = side_structure(mask, relief, tone)
    picture = r.blend(picture, r.render_marks([m.to_dict() for m in scales.marks], W, H, sweep=True),
                      'normal', 1.0)
    for fig in (fin_marks(), head_marks(), eye_marks()):
        picture = r.blend(picture, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True),
                          'normal', 1.0)
    path = os.path.join(OUT, 'fish.png')
    # **`light` 是最后一道，也是唯一一道会自己造出结构的地方。** 它按 relief 打光，而 relief 是每一笔的高度
    # 叠出来的 —— 笔尖是圆的，叠出来的地形就是一串圆丘，打光把圆丘变成亮暗相间的一节一节。灯开着的时候，
    # 这些节看起来像笔没铺连续；关掉灯再画一张，就能分出哪些节是笔的、哪些是地形被照出来的。
    # `FISH_NO_LIGHT=1` 只是给这件事留一个可以重复的对照，不是另一种渲染模式。
    lit = r.light(picture, direction=LIGHT, strength=0.26, tilt=1.0) \
        if not os.environ.get('FISH_NO_LIGHT') else picture
    r.save_png(lit, path, background=(18, 15, 14))
    project.save_project(body, os.path.join(OUT, 'pass-fish.json'))
    project.save_project(scales, os.path.join(OUT, 'pass-fish-scales.json'))
    print('%s  %d marks  +%d scales' % (path, len(body.marks), len(scales.marks)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
