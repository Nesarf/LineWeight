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
#: The height of the form's centre line, and how much the whole outline is stretched about it.
BODY_MID = 485.0
STRETCH = 1.17


def tall(points):
    """Stretch a set of coordinates about the body's centre line.

    **The form was too flat, and that is a data change, not a drawing one.** At three hundred and six pixels of height to
    nine hundred of length the outline read as a flounder -- and a flounder is a real fish, but this subject is a carp or
    a bream, and those sit near two fifths. Stretching about the centre line moves the dorsal edge up and the ventral
    edge down in one operation, so every coordinate that was right relative to the centre line stays right.

    **Kept outside the data on purpose.** These numbers were adjusted by hand twice in earlier rounds; a third edit
    applied straight to the literal pairs would leave nothing recognisable and no way back. A transform says what
    happened to them.
    """
    return [(float(x), BODY_MID + (float(y) - BODY_MID) * STRETCH) for x, y in points]


BODY = tall([(168, 444), (238, 428), (326, 386), (430, 356), (556, 338), (700, 332), (826, 344),
             (930, 372), (1012, 414), (1064, 462), (1068, 508), (1030, 556), (944, 596),
             (846, 620), (726, 634), (594, 638), (468, 630), (356, 600), (272, 556), (200, 510), (162, 486)])
# **The pectoral was too far back, opened too narrow, and was the wrong shape.** A pectoral grows from just behind the
# gill cover low on the flank and fans back and down through most of a right angle. And when the head grew in 4.103 the
# cover moved back seventy pixels while the root stayed put -- so the fin ended up **in front of the cover it is
# supposed to grow from**, which is the mirror image of the first error and just as wrong. Root and outline moved
# together: a fin belongs behind the cover, not beside the eye.
FIN = tall([(846, 540), (750, 678), (723, 652), (701, 624), (685, 594), (674, 562)])
TAIL = tall([(168, 446), (58, 412), (12, 462), (52, 520), (166, 484)])
# **And the fin's root sat above the body's own edge, which is why it looked like it floated.** The dorsal polygon's
# lower points were at y 336 while the outline's upper edge passes through y 350 at that x -- fourteen pixels of gap
# that no drawing change could hide, and that `tall()` preserved because it moved both by the same factor. The two
# lower corners are pulled down into the body, so the fin grows out of it.
# **And its outer edge was nearly flat.** The four points across the top sat within eight pixels of one another, so the
# fin read as a trapezium with two diagonal sides rather than as a fin -- which is a curve rising out of the back at
# one end and falling back into it at the other. The middle three points moved up, the two corners stayed, and the
# middle is now ninety-two pixels above the root.
DORSAL = tall([(470, 364), (520, 300), (580, 286), (640, 292), (700, 352), (586, 340)])
# **The dorsal fin's root is a line, not a point.** `fin_marks` radiates from a root for the pectoral and the tail, and
# that is right for them: a pectoral springs from one attachment and a tail fin from a short one. The dorsal springs
# from the whole length of the back, so radiating from its centre produced a fan of bristles, and the bristles were
# longer than the fin was tall. These two edges are the fin as a strip of membrane -- the root follows the back, the
# tip is the outer curve -- and a ray is a mark that spans between them.
DORSAL_ROOT = tall([(470, 364), (586, 340), (700, 352)])
DORSAL_TIP = tall([(470, 364), (520, 300), (580, 286), (640, 292), (700, 352)])
FIN_ROOT = tall([(846, 540)])[0]
TAIL_ROOT = tall([(166, 466)])[0]
# **And the eye was in the wrong part of the head, and the head was too short.** At sixty-six pixels from a snout that
# is a hundred and thirty-three from the gill cover, the eye sat in the middle of a head that was itself only a seventh
# of the body -- while a fish's head runs a fifth to a quarter of it and its eye sits at a third to two fifths of that.
# Both numbers moved: the gill cover back seventy pixels, the eye forward, and the two now sit in the proportions the
# animal has instead of being crowded into the front eighth.
EYE = (993.0, 446.0)

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
    """侧视的扁平形体：**中央亮、四周边缘暗**。

    **上一版把梯度当法线，用的是 `raster.light` 那个式子，而它在这里是错的。** 那条式子量的是「表面往哪个方向
    转」，在苹果那样一个球上对得干净；鱼不是球，是一条侧扁的形状从侧面看过去 —— 我们看见的是一整块面，它的
    法线几乎全都朝着观察者。梯度指向中线的两侧，于是上半个面的法线朝左上、下半个面朝右下，朗伯项一正一负，
    结果就是上半米白、下半深青，中间一条波浪状的硬边。**那不是一条鱼的两面，那是两块拼起来的东西。**

    侧视的扁平体该按「到轮廓的距离」受光：离边缘越远，越靠近观察者，也越正对光源；靠近背缘、腹缘、头尾的
    地方转向背面。所以这里直接用 `relief`（到轮廓的距离归一化再开方，本来就存在），不再对它求梯度。

    `tilt` 留下来了，意思换了：它现在是「边缘压到多暗」。鳍用 0.6，因为一片鳍比鱼身薄，边缘没有那么快转过去。
    """
    return np.clip(1.0 - 0.41 * tilt * (1.0 - relief), 0.0, 1.35)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def hexed(colour):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in colour)


def jitter(colour, amount, rng):
    return (colour[0] + rng.uniform(-amount, amount),
            colour[1] + rng.uniform(-amount * 0.9, amount * 0.9),
            colour[2] + rng.uniform(-amount * 0.8, amount * 0.8))


def fish_colour(across, rng, amount=9.0):
    """背、侧、腹三段 —— 三段按**从背到腹的位置**分，不按明度分。

    **这个函数的参数原来是明度，那是错的，而错法很具体。** 明度由梯度算出来，于是它和「上半亮、下半暗」是同一件
    事；拿它去取色，等于说「背就是亮的那半边、腹就是暗的那半边」。真实的鱼反过来：背脊最深（青或褐），体侧
    银里透金（三段的中间），腹部最浅（白里透粉）。**「上暗下亮」既是一个色带，也是一个方向 —— 而它和光照不是
    一回事。** 上一版把两件事压进同一个变量，于是无论怎么调那条曲线，读出来都是两块拼起来的东西。

    所以参数换成 `across`：零是背脊，一是腹缘。色带由它决定，光由调用它的地方另外乘上去。

    **三段之间不是等权插值。** 背是透明的深色，一点就能压住整片；腹是白的，弱，要加很多才推得动。等权插值等于
    假设两管颜料一样强，于是暗部亮得太早、腹部白得太快（4.72 节，`lineweight/pigment.py`）。
    """
    ridge, flank, belly = (86, 100, 96), (188, 168, 134), (238, 216, 196)
    # **两段之间不再插一段纯色。** 上一版在 0.46 与 0.68 之间放了一段不加别的金，理由是「一段色带要有宽度」——
    # 而它画出来是一条贴在身上的横带，因为那一段的边界是两条直的等值线。真实的体侧是一整片，只是从背到腹一直
    # 在变；所以让两条曲线在 0.52 处接上，中间不留平台。
    if across <= 0.52:
        body = pigment.mix_by_strength(ridge, flank, across / 0.52, DEEP_STRENGTH, MID_STRENGTH)
    else:
        body = pigment.mix_by_strength(flank, belly, (across - 0.52) / 0.48, MID_STRENGTH, BACK_STRENGTH)
    # **虹彩带在侧线上，不在体侧正中。** 上一版把它放在 `across` 零点五二，而那正好是体侧面积最大的一条 —— 于是
    # 整条鱼被染成青绿，读成一块褪了色的肥皂。它该窄，而且该靠着侧线（零点三四）那一带 —— 而第一版放到那里时
    # 还没收窄，整片交界的绿把「银金」又盖掉了一次。
    iris = 0.14 * math.exp(-((across - 0.32) / 0.075) ** 2)
    body = mix(body, (116, 154, 148), iris)
    # **而腹侧的反射光偏暖，因为反射它的是桌子。** 提亮由 `body_light` 做，色相由这里做 —— 两件事分开，因为一
    # 处是光的量，一处是光的颜色；把它们塞进一个式子，暗部就会变成"亮一点的青"而不是"暖过来的青"。
    bounce = 0.26 * math.exp(-((across - 0.94) / 0.20) ** 2)
    body = mix(body, (196, 166, 130), bounce)
    return jitter(body, amount, rng)


def body_light(relief_value, across):
    """体侧一处的亮度：**中央亮，再加一个顺着高度的弱渐变，再加一点来自桌面的反光。**

    两处调用（体身的笔、鳞、侧线）必须共用一个式子 —— 上一次它们各自带一份系数，改一处另外两处就留在旧值上，
    而那个漂走是看不出来的：鳞片只差十分之一，没有人会在画上认出来。

    **而暗部不塌，是因为有第二个光源。** 一条躺在桌上的鱼，腹侧收到的不是直射光，是桌面反射回来的 —— 所以它比
    "没有光"亮，而且偏暖。这一条和 `light` 那种带方向的灯不是一回事：**环境光没有方向，而它有一个位置（桌面）。**
    第一版的暗部是一片死青，那不是颜色选错，是少了一个光源。
    """
    base = 0.36 + 0.62 * max(0.0, float(relief_value)) ** 1.15 + 0.20 * (0.5 - across)
    bounce = 0.24 * max(0.0, 0.66 - base) / 0.66
    return base + bounce


def soft_mask_layer(mask, blur=2.2):
    """布尔掩膜 → 一张软边的遮罩图层，给 `r.clip` 用。

    **为什么要软。** `clip` 是一句话：乘 alpha。而硬裁会在边界上把厚度从「有」砍到「零」，`light` 找到那道悬崖，
    沿边画一条亮线 —— 4.64 那一节就是这么发现的。两像素的高斯把那条崖变成一道缓坡，裁出来的边于是是一条线，
    不是一道台阶。

    **而体身本来就需要裁。** 每一个笔触都是圆头的，笔伸出轮廓的地方就露出一个圆弧 —— 扁平形体的边缘攒上一圈
    圆包，读成毛边。相邻的苹果没有这个问题：球形的轮廓靠笔自己停下来就能长出来，一条扁鱼不行。
    """
    soft = np.clip(ndimage.gaussian_filter(mask.astype(np.float64), blur), 0.0, 1.0)
    layer = r.Layer(W, H)
    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rgba[:, :, 0:3] = 255
    rgba[:, :, 3] = (soft * 255.0).astype(np.uint8)
    layer.data[:] = rgba.tobytes()
    return layer


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

    **而体色第一次不再由明度决定。** 上一版 `fish_colour` 收的参数是明度，而明度是梯度算出来的，于是「背深
    腹浅」被压进了「上亮下暗」里 —— 两个相反的读法共用一个变量，怎么调那条曲线都不对。现在色带由 `across`
    （从背到腹的位置）给，光只乘一个跟着 `relief` 走的因子。两者的分工写在 `fish_colour` 的 docstring 里。
    """
    rng = random.Random(seed)
    mask = mask_of(BODY)
    # **`exponent 0.85` 而不是 0.52。** 开方的效果是让「到轮廓的距离」在中部迅速顶到接近一 —— 一张图画下来，
    # 体侧有一大片 `relief` 几乎不变的区域，于是 `body_light` 在那里给出一块平的高原，读成一块发光的肥皂。
    # 0.85 接近线性，体侧才有坡度；代价是 `thin`（笔长的缩放）整体略变，而那是小事。
    relief = height_of(mask, exponent=0.85)
    gy, gx = np.gradient(relief)
    # 每一列从哪里到哪里 —— 体色要按「从背到腹的位置」取，而那个比例必须由当地的体高来算，不能用整条鱼的中线。
    top_of = np.argmax(mask, axis=0)
    bot_of = H - 1 - np.argmax(mask[::-1, :], axis=0)
    fig = canvas('fish body')
    rows, cols = np.nonzero(mask)
    index = 0
    for _ in range(1800):
        pick = rng.randrange(rows.size)
        y, x = int(rows[pick]), int(cols[pick])
        span = max(1.0, float(bot_of[x] - top_of[x]))
        across = max(0.0, min(1.0, (y - float(top_of[x])) / span))
        # **斑驳要够大，因为光是平的。** 中段那一片 `relief` 几乎不变（扁平形体的距离场本来如此），任何单调函数
        # 都会在那片地方给出一条等值的带 —— 而画出来就是一条贴在身上的黄布。真实鱼体侧本来有明暗斑块，所以
        # 这里不是再加一层装饰，是用位置把它打断。
        mottle = (1.0 + 0.14 * math.sin(x * 0.0105 + y * 0.0042) + 0.09 * math.sin(x * 0.031 - y * 0.016)
                  + 0.06 * math.sin(x * 0.0061 - y * 0.023))
        pigment = fish_colour(across, rng)
        # **光只做调制，不再决定色带。** 侧视的扁平体，中央正对观察者也正对光源，四周转向背面 —— 所以亮度跟着
        # `relief` 走，而「背深腹浅」跟着 `across` 走。两件事分开之后，一条鱼才可能上半深、中间银、下半浅。
        #
        # **而光要两项，不只一项。** 只给一项的时候体侧是一整块平的高原 —— `relief` 是「到轮廓的距离」，扁平
        # 形体的中部本来就是一整片接近一的平台，于是中央亮在整片体侧上处处相同，读成一块发光的肥皂。侧面的
        # 曲面还随高度转：靠近背的那一侧朝上（受光），靠近腹的那一侧朝下（背光）。所以再叠一个很弱的上下项 —
        # — 而它要和色带顶着来，因为背是深色的保护色却在受光，腹是浅色的却在背光，真实的鱼正是这个拉锯。
        # `relief ** 1.5` 把平台压出坡度，否则加什么都是平的。
        lit = body_light(relief[y, x], across)
        pigment = (pigment[0] * mottle * lit, pigment[1] * mottle * lit * 1.004,
                   pigment[2] * mottle * lit * 0.996)
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
    return fig, mask, relief


def ray_reach(mask, x0, y0, dx, dy, limit=420.0, step=2.0):
    """从一点沿一个方向走，返回还在掩膜内的最远距离 —— 鳍条要走到它自己的边缘，所以得先知道边缘在哪里。"""
    travelled = 0.0
    while travelled < limit:
        x = int(round(x0 + dx * travelled))
        y = int(round(y0 + dy * travelled))
        if not (0 <= x < W and 0 <= y < H) or not mask[y, x]:
            return travelled
        travelled += step
    return limit


def fin_film():
    """三片鳍的膜：**一片鳍是有底的，而底不是笔触堆出来的。**

    上一版用几条很宽的径向笔当膜，alpha 只有零点一几 —— 放大四倍看，背鳍是一排悬在深色背脊上的细线，下面什么也
    没有。原因是那些笔各自的宽度是「这一条能走多远」的一个比例，而一片鳍的高度沿长轴一直在变，任何一条恒定宽度
    的笔都对不上它自己的边界。

    所以膜改成一个**填出来的形状**，再裁到软边（硬裁的边会在 `light` 下变成一条亮线，4.64 那一节）。鳍条压在它
    上面，于是「条」与「膜」是两层，而不是一层笔触兼做两件事。

    **而颜色第一次是错的，错法是无声的。** 第一版的膜是 (46,44,48)、alpha 零点六，而背景是 (38,34,32) —— 混合
    之后是 (44,41,42)，和它要盖住的那片地方几乎相同。**膜确实画了，只是看不见。** 一片鳍在水里比背后的暗处亮，
    因为它是半透明的、透过来的是光，所以它该比背景亮一档，而不是比背脊暗一档。
    """
    film = r.Layer(W, H)
    # **背鳍的膜要比别的两片亮一档。** 它立在水里，两侧都是暗的，透过来的是光；胸鳍贴着身体，尾鳍在后面。
    # 上一版三片同一个亮度，于是背鳍的外缘和背景融成一片，鳍没有边。
    for shape, level in ((DORSAL, 0.55), (FIN, 0.26), (TAIL, 0.28)):
        patch = r.Layer(W, H)
        tone = (82, 86, 90) if shape is DORSAL else (72, 76, 80)
        r.fill_polygon(patch, [tuple(p) for p in shape], tone, level)
        film = r.blend(film, r.clip(patch, soft_mask_layer(mask_of(shape), blur=3.0)), 'normal', 1.0)
    return film


def fin_marks(seed=505):
    """鳍：**一片膜，上面是一排从根一直走到边缘的鳍条。**

    **上一版错在「撒点」这件事本身。** 它在形状内随机取点，每一笔朝背向根的方向画三十到九十像素的一段 —— 于是
    三个鳍都成了「放射的短笔」：尾鳍一簇白毛、胸鳍一片羽毛。而一片鱼鳍不是那样长的：它是十几根**贯穿**的鳍条，
    从根出发、一路走到边缘，中间不断；鳍条的末端往往还伸出膜外一点点。

    撒点给不出「贯穿」，因为每一笔都不知道边缘在哪里。所以这里改成**按角度排**：从根出发扫一圈角度，每个角度
    一条，先用 `ray_reach` 问出这一条能走多远，笔就画那么长。**数量由角度间隔决定，长度由形状决定** —— 和鳞那
    一条是同一个道理，排出来的结构与撒出来的笔触不是一回事。

    **膜还要先铺。** 只有条的时候，一片鳍读成一排悬着的线；鳍本来是有底的，条是压在底上的。
    """
    rng = random.Random(seed)
    fig = canvas('fins')
    for shape, root, span, density in ((FIN, FIN_ROOT, (2.15, 2.95), 14),
                                       (TAIL, TAIL_ROOT, (2.70, 3.64), 15)):
        mask = mask_of(shape)
        relief = height_of(mask, exponent=0.75)
        tone = shading(relief, tilt=0.6)
        # 膜：沿径向的几条宽笔，低 alpha，叠起来把这一片压下去。
        for i in range(6):
            fraction = (i + 0.5) / 6.0
            theta = span[0] + (span[1] - span[0]) * fraction
            dx, dy = math.cos(theta), math.sin(theta)
            reach = ray_reach(mask, root[0], root[1], dx, dy)
            if reach < 10.0:
                continue
            hx, hy = root[0] + dx * reach * 0.5, root[1] + dy * reach * 0.5
            fig.add_stroke(core.stroke_record(
                [(root[0] + dx * reach * 0.06, root[1] + dy * reach * 0.06), (hx, hy),
                 (root[0] + dx * reach * 0.94, root[1] + dy * reach * 0.94)], 'brush', seed=800 + i,
                colour='#2e2a2c', soft=0.9, height=0.12,
                width_profile=[reach * 0.30, reach * 0.36, reach * 0.30],
                alpha_profile=[0.10, 0.15, 0.10],
                absolute_width=True, edge=7.0), stage='line', layer='paint', note='')
        # 鳍条：每个角度一条，从根走到边缘，长度由 `ray_reach` 给。
        for i in range(density):
            theta = span[0] + (span[1] - span[0]) * (i + 0.4 * rng.random()) / density
            dx, dy = math.cos(theta), math.sin(theta)
            reach = ray_reach(mask, root[0], root[1], dx, dy)
            if reach < 14.0:
                continue
            start = reach * rng.uniform(0.02, 0.10)
            end = reach * rng.uniform(0.92, 1.01)
            mid_x, mid_y = root[0] + dx * (start + end) * 0.5, root[1] + dy * (start + end) * 0.5
            mx, my = int(round(mid_x)), int(round(mid_y))
            thin = math.sqrt(max(0.0, float(relief[my, mx]))) if 0 <= mx < W and 0 <= my < H else 0.4
            pigment = jitter(mix((48, 48, 52), (92, 96, 100), min(1.0, float(tone[my, mx]))), 6.0, rng)
            alpha = 0.28 + 0.52 * thin
            fig.add_stroke(core.stroke_record(
                [(root[0] + dx * start, root[1] + dy * start), (mid_x, mid_y),
                 (root[0] + dx * end, root[1] + dy * end)], 'brush', seed=900 + i,
                colour=hexed(pigment), soft=0.5, height=0.14, bristle=0.20,
                width_profile=[rng.uniform(3.2, 4.6), rng.uniform(4.2, 6.2), rng.uniform(2.4, 3.8)],
                alpha_profile=[alpha * 0.72, alpha, alpha * 0.60],
                absolute_width=True, edge=rng.uniform(1.2, 2.2)), stage='line', layer='paint', note='')
    # **背鳍：根是一条线，鳍条跨在这条线与外缘之间。** 上一版给它一个「根点」、让笔从那里向四面八方辐射，于是
    # 它读成一把毛刷；而 34–90 长的笔落在一片只有四十几像素高的膜上，两端都伸出轮廓。鳍条的长度不是常数，它
    # 就是这一处的鳍高，所以每一笔自己算。
    mask = mask_of(DORSAL)
    relief = height_of(mask, exponent=0.75)
    tone = shading(relief, tilt=0.6)
    # **旧的膜笔删掉了。** 那七条宽横笔是上一版的膜，而膜现在由 `fin_film` 填一次 —— 两套一起留着，膜就是两层
    # 不均匀的半透明叠在一起，比任何一层都脏。**加了一层新机制之后，要回头找旧的那一层**，否则它不会报错，只会
    # 让新的一层看起来不对。
    for i in range(32):
        x0 = rng.uniform(478.0, 692.0)
        y_root = along(DORSAL_ROOT, x0)
        y_tip = along(DORSAL_TIP, x0)
        fin_height = y_root - y_tip
        if fin_height < 7.0:
            continue
        lean = (x0 - 586.0) / 118.0 * 0.12
        tip_x = x0 + lean * fin_height
        # **一根鳍条跨在根与尖之间，所以它的中心是中点，不是随机位置。** 上一版随机取一点当中心、再按鳍高画长度，
        # 取到靠近根的时候，笔就向上伸出一整片，读成一根伸出膜外的针。
        cx = (x0 + tip_x) * 0.5
        cy = (y_root + y_tip) * 0.5
        column, row = int(round(cx)), int(round(cy))
        if not (0 <= row < H and 0 <= column < W) or not mask[row, column]:
            continue
        thin = math.sqrt(max(0.0, float(relief[row, column])))
        pigment = jitter(mix((52, 48, 50), (96, 90, 86), min(1.0, float(tone[row, column]))), 6.0, rng)
        length = fin_height * rng.uniform(0.94, 1.06)
        ux, uy = x0 - tip_x, y_root - y_tip
        norm = math.hypot(ux, uy) or 1.0
        ux, uy = ux / norm, uy / norm
        alpha = 0.30 + 0.55 * thin
        fig.add_stroke(core.stroke_record(
            [(cx - ux * length * 0.5, cy - uy * length * 0.5), (cx, cy),
             (cx + ux * length * 0.5, cy + uy * length * 0.5)], 'brush', seed=1100 + i,
            colour=hexed(pigment), soft=0.8, height=0.18, bristle=0.26,
            width_profile=[rng.uniform(2.2, 3.2)] * 3,
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
    # **鳃盖的位置一开始放错了，而那是解剖而不是画法。** 它落在眼睛后面不到三十像素处，于是一个头读成
    # 「一只眼贴着一道弧」。真实的鱼吻端到眼睛约占头长的三分之一，眼睛到鳃盖再占三分之一 —— 所以鳃盖要退到
    # 眼睛后方六十像素左右，两者才各占一段，头才是一个头而不是一个点。
    fig.add_stroke(core.stroke_record(
        tall([(870, 404), (850, 452), (856, 508), (880, 554)]), 'brush', seed=610,
        colour='#161c1e', soft=0.25,
        width_profile=[6.0, 13.0, 13.0, 5.0], alpha_profile=[0.10, 0.50, 0.48, 0.12],
        absolute_width=True, edge=2.0), stage='line', layer='paint', note='')
    fig.add_stroke(core.stroke_record(
        tall([(884, 410), (864, 456), (870, 504), (892, 546)]), 'brush', seed=611,
        colour='#ded4bc', soft=0.25,
        width_profile=[4.0, 9.0, 9.0, 4.0], alpha_profile=[0.08, 0.34, 0.32, 0.09],
        absolute_width=True, edge=2.4), stage='line', layer='paint', note='')
    # 嘴：暗缝在上唇下面，亮边在上唇上面。**第一版太小了** —— 三笔加起来不到二十像素长、最宽五像素，落在
    # 一条一千四百像素宽的画上就是吻端的一个污点，而嘴是让人读出「这一头是头」的第二个东西。
    fig.add_stroke(core.stroke_record(
        tall([(1038, 494), (1052, 499), (1064, 507)]), 'brush', seed=620,
        colour='#111114', soft=0.2,
        width_profile=[6.0, 9.0, 6.0], alpha_profile=[0.55, 0.82, 0.60],
        absolute_width=True, edge=1.2), stage='line', layer='paint', note='')
    fig.add_stroke(core.stroke_record(
        tall([(1036, 488), (1051, 493), (1062, 501)]), 'brush', seed=621,
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
    # 高光：一点，斜的，不落在正中。**它要比上一版小** —— 五乘四落在二十二像素的瞳上，把瞳盖掉了一半，而高光
    # 是一点反射，不是瞳里的第二只眼。
    fig.add_stroke(core.stroke_record(
        [(cx - 5.0, cy + 0.0), (cx - 2.2, cy - 2.6)], 'brush', seed=330,
        colour='#fff8ec', soft=0.7, width_profile=[3.4, 2.8],
        alpha_profile=[0.88, 0.80], absolute_width=True, edge=1.4),
        stage='line', layer='paint', note='')
    return fig


def side_structure(mask, relief, seed=4040):
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
    while x < 866.0:
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
        # **每列的行数要抖，而这是「格子」真正的来源。** 上一版把每一列按体高等分成同一个行数，于是相邻两列的
        # 行永远对齐 —— 加多少随机偏移都只是把它们一起挪一点，接缝还是横平竖直。真的鳞序里相邻两列可以差一片，
        # 于是整片体侧是一道错开的斜缝。
        rows = max(2, int(round(span / (step * 0.94))) + rng.choice((-1, 0, 1)))
        for j in range(rows):
            # **行位置按比例抖，不按像素。** 尾柄只有几十像素高，绝对的三像素偏移在那里等于半片鳞；而头侧体高
            # 三百像素，三像素什么也不是。同一个偏移量在两处不是一回事。
            y = top + span * (j + 0.5 + rng.uniform(-0.16, 0.16)) / rows
            # 而且要有缺片 —— 真的鳞会缺、会挤、会有大半片被前一片压住。
            if rng.random() < 0.15:
                continue
            y_use = y + rng.uniform(-1.2, 1.2)
            x_use = x + 0.55 * (y - (top + bot) * 0.5) + rng.uniform(-2.4, 2.4)
            column_use = int(round(x_use))
            row_use = int(round(y_use))
            if not (0 <= column_use < W and 0 <= row_use < H) or not mask[row_use, column_use]:
                continue
            # **侧线穿过鳞片，所以那一带上不长鳞。** 侧线的孔本来就是在鳞上开的洞；把鳞铺满之后再用一条线去
            # 盖，盖不住 —— 六百多片 alpha 零点四的弧比它亮。留一条空带，侧线才有地方存在。
            line_y = (top + bot) * 0.5 - 0.16 * span
            if abs(y_use - line_y) < span * 0.055:
                continue
            value = float(relief[row_use, column_use])
            # **可见度跟着形体走，不再跟着明度走。** 上一版以一个明度为中心的钟形当判据，而那个明度来自「上半亮
            # 下半暗」的读法；那个读法一倒，这条件也就没有依据了。体侧的鳞在中段最清楚 —— 那里正对观察者，一片
            # 瓦的上缘能被看见；靠近背缘、腹缘、头尾的地方透视压缩，鳞挤成一条线，看不见。
            visible = 0.20 + 0.80 * min(1.0, value * 1.45)
            across = max(0.0, min(1.0, (y_use - top) / max(1.0, span)))
            pigment = fish_colour(across, rng, amount=4.0)
            lit = body_light(value, across)
            pigment = tuple(c * lit for c in pigment)
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
            # **鳞的对比要低。** 上一版的弧比底亮了百分之二十八，而且 alpha 到零点五，于是整条体侧是一片竖起
            # 的毛 —— 真的鳞只在斜光下露出一点边，颜色几乎和它所在的那块皮一样。鳞是纹理，不是内容。
            alpha = 0.28 * visible * rng.uniform(0.62, 1.18)
            fig.add_stroke(core.stroke_record(
                points, 'brush', seed=1400 + index, colour=hexed(pigment), soft=0.7,
                colour_profile=[[min(255.0, c * 1.10 + 4.0) for c in pigment], list(pigment),
                                [c * 0.90 for c in pigment]],
                bristle=0.14, bristle_pitch=3.2,
                width_profile=[rng.uniform(3.5, 4.6), rng.uniform(4.4, 5.8), rng.uniform(2.6, 3.8)],
                alpha_profile=[alpha * 0.66, alpha, alpha * 0.80],
                absolute_width=True, edge=1.2), stage='line', layer='paint', note='')
            index += 1
        # **列距也要抖。** 均匀推进就是等距网格的第一根柱子；真实的一列与下一列从来不是同一个间距。
        x += step * rng.uniform(0.82, 1.18)
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
                base = fish_colour(0.34, rng, amount=3.0)
                base = tuple(c * body_light(relief[int(line_y), column], 0.34) for c in base)
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


#: The near edge of the table, and how it wanders. **It sits just under the fish's lowest point**, because a fish
#: drawn from the side is lying down: a table twenty-six pixels below its belly leaves it floating in front of the
#: table rather than on it, and no shadow fixes that.
TABLE_EDGE = 674.0


def table_edge(x):
    """桌面的前缘 —— 一条不是直线的线。一条完美的直线在这一整张画里是唯一一处「机器画的」痕迹。"""
    return TABLE_EDGE + 9.0 * math.sin(x * 0.0042 + 0.6) + 4.0 * math.sin(x * 0.011 - 1.3)


def surface(seed=3300):
    """桌面：**一条鱼要有一个可以放着的地方。**

    画到这一轮为止，这条鱼浮在一片深褐里 —— 它是从空气里长出来的。桌面做的只有三件事：给鱼一条明确的地平线、
    让它的接触阴影有地方落、把背景从「一片深」拆成「后墙与桌面」。而三者之中只有第二件是画法问题，前两件是
    构图问题 —— 一条鱼浮着的时候，观者不知道它多大。
    """
    rng = random.Random(seed)
    layer = r.Layer(W, H)
    edge = [(float(x), table_edge(float(x))) for x in range(-40, W + 60, 9)]
    # **桌面的底色要比背景亮一档，否则看不见那条前缘。** 第一版是 (48,38,32)，而后墙的笔在 (22,19,18) 到
    # (86,76,66) 之间 —— 两者一混合，桌面就是背景上的一块补丁，「鱼放在桌上」这件事没有发生。一张桌子的上表面
    # 是朝上的，它比身后的墙受光，这是它能被看见的全部理由。**而第一次修过了头**：暖亮的木头把冷调的鱼压住，
    # 于是桌面成了主体。压回到比背景亮一档，不多。
    r.fill_polygon(layer, edge + [(W + 60.0, H + 40.0), (-40.0, H + 40.0)], (58, 48, 40), 1.0)
    fig = canvas('table grain')
    for i in range(120):
        x = rng.uniform(-80.0, W + 80.0)
        y = rng.uniform(TABLE_EDGE - 8.0, H + 40.0)
        # 越靠近观者越暗 —— 一盏在桌上方的灯照不到桌沿以外。
        near = max(0.0, min(1.0, (y - TABLE_EDGE) / 240.0))
        tone = mix((80, 66, 52), (40, 32, 26), near * rng.uniform(0.45, 1.0))
        length = rng.uniform(140.0, 420.0)
        fig.add_stroke(core.stroke_record(
            [(x - length * 0.5, y), (x, y + rng.uniform(-3.0, 3.0)),
             (x + length * 0.5, y + rng.uniform(-2.0, 2.0))],
            'brush', seed=3300 + i, colour=hexed(jitter(tone, 7.0, rng)), soft=0.9,
            height=rng.uniform(0.008, 0.020), bristle=0.30, bristle_pitch=rng.uniform(3.4, 5.2),
            width_profile=[rng.uniform(26.0, 64.0)] * 3,
            alpha_profile=[rng.uniform(0.34, 0.66)] * 3,
            absolute_width=True, edge=rng.uniform(7.0, 15.0)), stage='line', layer='paint', note='')
    return r.blend(layer, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True), 'normal', 1.0)


def contact_shadow(mask, seed=3500):
    """鱼压出来的影：**它让鱼落在桌上，而不是飘在桌前。**

    影的位置不是「鱼下面」这么简单 —— 它要从鱼的下缘开始，越往下越淡，而且只出现在下缘以下。所以这一层必须问
    掩膜「这一列的底在哪里」，而不是问一个固定的 y。**一条沿体轴的均匀暗带会读成另一条鱼**，那正是 `paint_pair`
    在 4.61 记过的错。
    """
    rng = random.Random(seed)
    bot_of = H - 1 - np.argmax(mask[::-1, :], axis=0)
    fig = canvas('contact shadow')
    for i in range(80):
        column = int(rng.uniform(200.0, 1040.0))
        if not (0 <= column < W) or not mask[:, column].any():
            continue
        bottom = float(bot_of[column])
        reach = rng.uniform(14.0, 44.0)
        depth = rng.uniform(2.0, reach)
        y = bottom + depth
        fade = max(0.0, 1.0 - depth / reach)
        alpha = 0.55 * fade * fade
        if alpha < 0.015:
            continue
        span = rng.uniform(26.0, 58.0)
        fig.add_stroke(core.stroke_record(
            [(column - span, y), (column, y + rng.uniform(-3.0, 3.0)), (column + span, y)],
            'brush', seed=3500 + i, colour='#1a1411', soft=0.9,
            width_profile=[rng.uniform(20.0, 40.0)] * 3,
            alpha_profile=[alpha * 0.55, alpha, alpha * 0.55],
            absolute_width=True, edge=rng.uniform(6.0, 13.0)), stage='line', layer='paint', note='')
    return fig


def main():
    os.makedirs(OUT, exist_ok=True)
    picture = ground()
    picture = r.blend(picture, surface(), 'normal', 1.0)
    body, mask, relief = fish_marks()
    # **影先于鱼。** 影落在桌面上，鱼落在影上 —— 反过来写，鱼的下缘会被自己的影盖住一圈，读成一条更暗的边。
    picture = r.blend(picture, r.render_marks([m.to_dict() for m in contact_shadow(mask).marks], W, H,
                                              sweep=True), 'normal', 1.0)
    layer = r.render_marks([m.to_dict() for m in body.marks], W, H, sweep=True)
    rng = random.Random(404)
    for _ in range(16):
        y = rng.uniform(360.0, 620.0)
        x0 = rng.uniform(220.0, 760.0)
        points = [(x0 + k * 34.0, y + math.sin(k * 0.6) * 6.0) for k in range(6)]
        r.smudge(layer, points, radius=rng.uniform(22, 40), strength=rng.uniform(0.28, 0.48))
    picture = r.blend(picture, r.clip(layer, soft_mask_layer(mask)), 'normal', 1.0)
    # **第二层落在湿拖之后。** 鳞与侧线是这个形体上的构造，被 `smudge` 拖过一遍就又是一片没有方向的糊；而第一
    # 层要的正是那点糊 —— 两层先后不是排版问题，是它们各自该受什么处理。
    scales = side_structure(mask, relief)
    picture = r.blend(picture, r.render_marks([m.to_dict() for m in scales.marks], W, H, sweep=True),
                      'normal', 1.0)
    picture = r.blend(picture, fin_film(), 'normal', 1.0)
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
