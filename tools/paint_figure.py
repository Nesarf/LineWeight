"""一个人的半身像：**三停五眼先立，然后才是颜色。**

前七张画都是题材：果子、布、鱼、山。人和它们差得最远的地方不在细节多少，在**判据是一组比值**。一个苹果画歪了
还是苹果；一张脸差百分之五就是另一个人。所以这个文件的第一件事不是找颜色，是把那组比值写下来：

```
三停   发际到眉、眉到鼻底、鼻底到下巴，三段等长
五眼   脸的宽度是五只眼睛；两眼之间正好一只眼睛
中线   眼在中线上，而中线的位置由脸的高决定，不由头的包围盒决定
```

**它们是可以被指着量的**，所以它们像 `learn/facts.json` 里那些条目，而不像 `oil_survey` 的列。这一版只用它们做
形；颜色是另一件事，四个人（皮肤、头发、唇、眼）各自一两档。

**而这一版刻意只画到肩。** 半身像把脸放到画面的三分之一宽，而全身像会把脸压到十五分之一 —— 在 1400×900 上那是
九十像素宽的一张脸，五官只能靠三笔，而三笔画不出「一个人」。**先把手能做到的程度做满，再谈构图。**
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                          # noqa: E402

from lineweight import core, project, pigment, standards  # noqa: E402
from lineweight import raster as r             # noqa: E402

import paint_export                            # noqa: E402

OUT = os.environ.get('FIGURE_OUT') or os.path.join(os.getcwd(), 'figure')
W, H = 1400, 900

CX, CY = 700.0, 430.0        # 脸的中心，而不是头的中心 —— 下颌比额头长，所以中心略低
FACE_W = 250.0               # 半宽，也就是「五眼」里两只半眼睛的宽度
FACE_H = 252.0               # 半高

# **脸的轮廓：额头宽、颧骨最宽、下颌收、下巴圆。** 一个椭圆在这里读成鸡蛋，而人不是鸡蛋 —— 差别全在下颌那一段：
# 从颧骨到下巴要收掉四成，且最后那一段是**慢**的（下巴不是尖的）。
#
# **而「慢」是一个斜率，可以写下来。** 上一版最后一段从 (0.17, 0.71) 直接落到中线，斜率 0.73；上一段是 0.73 的
# 一半都不到，于是下巴收成一个尖角，读成锥子。在两点之间插一个点之后，最后三段的斜率依次是 0.73、0.41、0.15 ——
# **一路变平**，那才是下巴：它不是一条边，是一段圆弧的最后半格。这就是「圆钝」在坐标里的样子。
#
# **而第一版的宽度写窄了三分之一**：`FACE_H / FACE_W` 给出来是一比一点八，而真实的头（从颅顶到下巴）是一比一点
# 四。那个差在画面上不是「有点长」，是**读成一颗杏仁**。脸的宽度由颧骨定，不由额头定 —— 额头在上半部，而它连着
# 的不是一条直的边。
FACE = [
    (0.00, -1.00), (0.36, -0.98), (0.58, -0.88), (0.72, -0.66),
    (0.80, -0.34), (0.78, -0.08), (0.68, 0.18), (0.52, 0.42),
    (0.32, 0.60), (0.17, 0.71), (0.075, 0.749), (0.00, 0.76),
]

SKIN_DARK = (152, 104, 84)
SKIN_MID = (204, 148, 122)
SKIN_LIGHT = (238, 196, 166)
HAIR_DARK = (30, 26, 30)
HAIR_MID = (62, 52, 58)
LIP = (168, 96, 92)
IRIS = (52, 44, 42)


def hexed(colour):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(c)))) for c in colour[:3])


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def jitter(colour, amount, rng):
    return tuple(max(0.0, min(255.0, c + rng.uniform(-amount, amount))) for c in colour)


def outline(steps=0):
    """脸的闭合轮廓。右半列出来，左半是它的镜像 —— **一个对称的东西只该写一半。**"""
    right = [(CX + x * FACE_W, CY + y * FACE_H) for x, y in FACE]
    left = [(CX - x * FACE_W, CY + y * FACE_H) for x, y in reversed(FACE[:-1])]
    return right + left


def mask_of(points):
    layer = r.Layer(W, H)
    r.fill_polygon(layer, points, (255, 255, 255), 1.0)
    data = np.frombuffer(bytes(layer.data), dtype=np.uint8).reshape(H, W, 4)
    return data[:, :, 3] > 127


def top_bottom(mask):
    rows = np.where(mask.any(axis=1))[0]
    return int(rows[0]), int(rows[-1])


def soft_mask(mask, blur=3.0):
    """把布尔掩膜变成一张软边蒙版。**边要软，因为脸没有一条硬轮廓** —— 而硬轮廓是「剪下来的形状」的样子。"""
    from scipy import ndimage

    alpha = np.where(mask, 255.0, 0.0)
    alpha = ndimage.gaussian_filter(alpha, blur)
    array = np.zeros((H, W, 4), dtype=np.uint8)
    array[:, :, :3] = 255
    array[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    layer = r.Layer(W, H)
    layer.data = bytearray(array.tobytes())
    return layer


def skin_colour(depth):
    """`depth` 是从脸的边缘往里走的量：0 在边上、1 在中间。

    **而脸不是球，所以明暗不是余弦。** 额头与鼻梁是两个高点，眼下与颊下是两个低点 —— 但这一版只用一个「中间亮、
    边缘暗」的场，因为再加一层之前，先要确认脸上的位置对。
    """
    if depth < 0.5:
        return mix(SKIN_DARK, SKIN_MID, depth / 0.5)
    return mix(SKIN_MID, SKIN_LIGHT, (depth - 0.5) / 0.5)


def eye_marks(centre, width, height, seed=71000):
    """一只眼：**上睑一道弧、下睑一道更平的弧、虹膜一圈、瞳孔一点、高光一点。**

    **宽度不由这里定。** 「五眼」说脸宽分成五份、一份是一只眼，所以这一只眼的宽度是 `2 * FACE_W * 0.80 / 5` ——
    它从脸上算出来，而这样改了脸宽之后眼睛会跟着改。**一个附属物的尺寸该由它所属的东西给。**

    而高度是宽度的一半多一点：眼睛不是圆的，它的开口是一条缝，而**那条缝的形状比眼珠更像一个人**。所以上睑的弧
    比下睑弯得多 —— 上面挂在眶骨上，下面只搭在脸颊上。
    """
    cx, cy = centre
    fig = project.Project(width=W, height=H, title='figure eyes')
    half = width * 0.5
    # **眼角要闭合，而闭合靠的是末段的方向，不是端点的位置。** 计划里写的是「上睑两端向内收五到八像素」，
    # 照着做了之后放大看：两条弧不再在端点相遇，外眼角张开一个小口，上睑的线头与下睑的线头错开成一个小叉 ——
    # 比原来的尾巴更难看。
    #
    # 真正的毛病在倒数第二个点：它在外侧三分之一处、高过端点，于是末段从眼睛内侧斜穿到下睑线上，与下睑交叉，
    # 交点之外那一小截就是「撇出去的线头」。把两个控制点都挪到一半处（0.52），末段的角度就缓到与下睑汇入同一点，
    # 眼角是一个尖，不是两条线的交叉。
    #
    # **这一条是计划被证据改掉的记录。** 端点收进是「照着一张图看不出来、放到三倍才看出来」的那类改动。
    # **上睑**：内眼角略低、中间拱起、外眼角略高。三个点足够 —— 而四个点会让它变成一条两边对称的拱。
    upper = [(cx - half, cy + height * 0.04), (cx - half * 0.52, cy - height * 0.50),
             (cx + half * 0.52, cy - height * 0.46), (cx + half, cy + height * 0.04)]
    fig.add_stroke(core.stroke_record(
        upper, 'brush', seed=seed, colour=hexed((38, 30, 32)), soft=0.35,
        width_profile=[2.4, 4.4, 4.0, 2.0], alpha_profile=[0.62, 0.86, 0.84, 0.58],
        absolute_width=True, edge=1.1), stage='line', layer='eye', note='')
    # 下睑：更平、更淡。**它不该和上睑一样重** —— 上睑有睫毛与褶，下睑没有。
    lower = [(cx - half, cy + height * 0.04), (cx - half * 0.24, cy + height * 0.40),
             (cx + half * 0.30, cy + height * 0.36), (cx + half, cy - height * 0.02)]
    fig.add_stroke(core.stroke_record(
        lower, 'brush', seed=seed + 1, colour=hexed((92, 66, 60)), soft=0.5,
        width_profile=[1.6, 2.6, 2.4, 1.4], alpha_profile=[0.30, 0.46, 0.44, 0.28],
        absolute_width=True, edge=1.4), stage='line', layer='eye', note='')
    # 虹膜：一个圆，而上缘被上睑压掉一点 —— **这一点是「眼珠在眶里」的全部证据**。
    #
    # **而四个点画不出圆。** 第一版给了上下左右四点，Catmull-Rom 过这四个点给的是一个圆角方 —— 而虹膜是这张脸上
    # 唯一一个真正的圆，它方了，眼睛就变成了一对扣子。十六个点之后它才圆。
    # **而它的半径不能大于眼裂。** 第一版给了眼高的零点七二，虹膜于是从眼睑外面绕了一圈 —— 读成一只戴圆环的
    # 眼睛。真实的虹膜直径大约等于眼裂高度，所以半径是高度的五成半。
    iris_r = height * 0.55
    ring = [(cx + iris_r * math.cos(a), cy + iris_r * math.sin(a))
            for a in (2.0 * math.pi * k / 16.0 for k in range(16))]
    ring.append(ring[0])
    fig.add_stroke(core.stroke_record(
        ring, 'brush', seed=seed + 2, colour=hexed(IRIS), soft=0.3,
        width_profile=[3.0] * len(ring), alpha_profile=[0.86] * len(ring),
        absolute_width=True, edge=1.0), stage='line', layer='eye', note='')
    # 瞳孔：比虹膜更浓，而它只占虹膜的六成。**而它也是十六个点** —— 圆这件事在一个直径二三十像素的东西上一样
    # 成立，而四个点画出来的瞳孔是一颗方的扣子。
    pupil_r = iris_r * 0.58
    pupil = [(cx + pupil_r * math.cos(a), cy + pupil_r * math.sin(a))
             for a in (2.0 * math.pi * k / 16.0 for k in range(16))]
    pupil.append(pupil[0])
    fig.add_stroke(core.stroke_record(
        pupil, 'brush', seed=seed + 3, colour=hexed((18, 14, 16)), soft=0.2,
        width_profile=[4.0] * len(pupil), alpha_profile=[0.94] * len(pupil),
        absolute_width=True, edge=1.0), stage='line', layer='eye', note='')
    # 高光：一点白，**位置在瞳孔的上外角** —— 光从左上过来，所以两只眼的高光在同一侧。而它是一点，不是一道：
    # 一道白条读成反光板，一点才读成湿润的眼球。
    fig.add_stroke(core.stroke_record(
        [(cx + iris_r * 0.30, cy - iris_r * 0.34), (cx + iris_r * 0.38, cy - iris_r * 0.30)],
        'brush', seed=seed + 4, colour='#f4ece2', soft=0.2,
        width_profile=[2.4, 2.0], alpha_profile=[0.90, 0.84], absolute_width=True, edge=0.9),
        stage='line', layer='eye', note='')
    return fig


def face_marks(seed=70701):
    """脸上的笔：**沿等高线走，而「等高线」是到轮廓的距离。**

    第一版按椭圆环撒笔，画出来是一块棕色的方 —— 两个错都在同一处：环只走了上半圆（`sin` 只取正值），于是下颌
    一条笔也没有；而环的半径与轮廓的形状无关，于是笔铺到轮廓外面又被裁掉。

    **改成距离场之后两件事同时对了。** 脸的内部每一点有一个「离轮廓多远」，那个场的等高线就是脸自己的走向 ——
    额头是一圈，鼻梁是两条，下颌是另一圈。而笔画沿等高线的切线，也就是垂直于梯度。

    `depth` 反着用：轮廓上最暗，往里亮起来。**而它只是一层**，因为这一版先要确认「位置对」，再谈有几层光。

    **而短笔铺满会画成年轮。** 第一版是八像素一格、每笔十八到四十八像素长、十个像素宽，于是脸的等高线变成
    一圈一圈的同心环，中央还有一条由中轴脊形成的三角 —— 读成一块木头。**那不是噪声，是「沿等高线撒短笔」这
    个方法的形态**：等高线是环，短笔跟着环，而人的皮肤上没有环。

    板绘里的皮肤是**低对比的大块**：笔很大、很淡，笔触几乎看不见，光靠一层薄薄的变化。所以这里把笔放大到
    四十至一百像素、透明度降到零点一五到零点二五、间隔拉到十八像素 —— **笔数少一个数量级，而脸变成一层皮，
    不再是一件木器。** 中轴脊的模糊因此也可以小一点，因为一支大笔不会沿着那条线排。
    """
    from scipy import ndimage

    rng = random.Random(seed)
    mask = mask_of(outline())
    depth = ndimage.distance_transform_edt(mask)
    depth = (depth / max(1.0, float(depth.max()))) ** 0.75
    # **脊上要磨一下。** 距离场在一个瘦长的形状里有一条中轴脊，梯度在那里不连续 —— 而笔的方向取自梯度，于是脸的正
    # 中央出现一块三角形，笔在那里互相交叉。**那不是噪声，是「一个函数在一条线上没有导数」画在纸上的样子。**
    depth = ndimage.gaussian_filter(depth, 9.0)
    gy, gx = np.gradient(depth)
    fig = project.Project(width=W, height=H, title='figure face')
    for y in range(0, H, 18):
        for x in range(0, W, 18):
            if not mask[y, x] or rng.random() > 0.62:
                continue
            here = float(depth[y, x])
            dx, dy = float(gx[y, x]), float(gy[y, x])
            norm = math.hypot(dx, dy) or 1.0
            tx, ty = -dy / norm, dx / norm
            length = 44.0 + 76.0 * here
            tone = jitter(skin_colour(here), 4.0, rng)
            fig.add_stroke(core.stroke_record(
                [(x - tx * length * 0.5, y - ty * length * 0.5 + rng.uniform(-4.0, 4.0)),
                 (x + tx * length * 0.5, y + ty * length * 0.5 + rng.uniform(-4.0, 4.0))],
                'brush', seed=seed + x * 7 + y, colour=hexed(tone), soft=1.1,
                width_profile=[rng.uniform(26.0, 46.0)] * 2,
                alpha_profile=[rng.uniform(0.14, 0.26)] * 2,
                absolute_width=True, edge=rng.uniform(14.0, 24.0), height=0.3),
                stage='line', layer='face', note='')
    return fig, mask


def brow_marks(centre, width, height, y, seed=72000):
    """一条眉：**内侧厚、眉峰靠外、眉尾薄。**

    **眉的高度不由眼睛推，由三停给。** 上一版用眼裂高当尺度来定眉眼间距（先三倍、再四点六倍），两次都是在两个
    猜出来的数之间换 —— 换个尺度就换一条眉，而没有哪一档是有依据的。按三停，眉在「发际到鼻底」这两停的交界上，
    眼睛略低于这条线；所以高度归 `standards.face` 的 `brow_y`，这里只管这一条眉自己怎么弯。

    而长相仍由眼睛给：眉的长短跟着眼走，因为「一个人眉毛有多长」这件事，看的是眼睛。
    """
    cx, cy = centre
    half = width * 0.5
    points = [
        (cx - half, y + height * 0.40),
        (cx - half * 0.30, y - height * 0.26),
        (cx + half * 0.24, y - height * 0.18),
        (cx + half, y + height * 0.66),
    ]
    fig = project.Project(width=W, height=H, title='figure brow')
    fig.add_stroke(core.stroke_record(
        points, 'brush', seed=seed, colour=hexed(HAIR_MID), soft=0.55,
        width_profile=[4.4, 5.8, 4.2, 1.5], alpha_profile=[0.52, 0.70, 0.60, 0.30],
        absolute_width=True, edge=1.7), stage='line', layer='brow', note='')
    return fig


def grown_outline(grow=1.14, lift=64.0):
    """脸轮廓放大一点、上提一点：**那是头发的厚度。**

    头发不是贴在头骨上的一层漆，它自己有厚度，所以「头」在画面上比「脸」大一圈。`lift` 单独给，因为颅顶那一段
    的厚度与两侧不同 —— 一个均匀放大的轮廓会把头压成鸡蛋。
    """
    return [(CX + (x - CX) * grow, CY + (y - CY) * grow - lift) for x, y in outline()]


def colour_layer(alpha, colour, blur=6.0, bottom=None, span=(80.0, 400.0)):
    """一块纯色，形状由一张 0..1 的遮罩给。**软边是给定的**，因为头发的边缘不是刀切的。

    接受数组而不是布尔掩膜，是因为头发下缘要渐隐：一条水平的硬边在太阳穴那里读成帽檐。

    `bottom` 给出第二个颜色时，按行从上到下混过去 —— **一块均匀的深色读成帽子，读成头发的是那一层渐变。**
    头发的受光在颅顶、最暗在发梢与耳侧，这个上下差就是体积；没有它，发团的形状再对也是一个剪影。
    """
    from scipy import ndimage

    smooth = ndimage.gaussian_filter(np.clip(alpha, 0.0, 1.0) * 255.0, blur)
    base = r.Layer(W, H)
    r.fill_polygon(base, [(-20.0, -20.0), (W + 20.0, -20.0), (W + 20.0, H + 20.0), (-20.0, H + 20.0)],
                   colour, 1.0)
    array = np.zeros((H, W, 4), dtype=np.uint8)
    array[:, :, :3] = 255
    array[:, :, 3] = np.clip(smooth, 0, 255).astype(np.uint8)
    mask = r.Layer(W, H)
    mask.data = bytearray(array.tobytes())
    layer = r.clip(base, mask)
    if bottom is None:
        return layer
    top, low = float(span[0]), float(span[1])
    rows = np.arange(H, dtype=float)[:, None]
    weight = alpha * np.clip((rows - top) / max(1.0, low - top), 0.0, 1.0)
    return r.blend(layer, colour_layer(weight, bottom, blur))


def hairline_at(x, middle=-0.52, edge=-0.10, reach=0.92):
    """发际线在每一列上的高度（半高单位）：中段在 `middle`，到鬓角落向 `edge`。

    **它是逐列的，不是一条弧。** 两次用二次曲线连两个端点，端点都落在颧骨上、中点只低十五像素 —— 画出来是一条
    水平横线，读成「一条刘海边」。发际线的真实形状是中段平缓、接近太阳穴时急转直下：所以这里用 |x| 的一点六次
    幂插值，中段几乎不动，最后两成宽度里落掉七成高度。

    写成函数而不是一个多边形，因为**它在画面上本来就是「这一列头发到哪里为止」**。多边形说不出这句话：它的
    每条边都要在两头之间取直，而发际线不是一条边，是一列一列的边界。
    """
    t = np.minimum(1.0, np.abs(np.asarray(x, dtype=float) - CX) / (FACE_W * reach))
    return middle + (edge - middle) * (t ** 1.6)


def hair_roots(mask, limit, spacing):
    """脸的轮廓上、颧骨以上那一圈点，沿周长每隔 `spacing` 取一个。

    **发根住在轮廓上，不是撒在环带里。** 上一版把笔撒在「距脸零到一百一十二像素」的环带中，每一笔都是一条独立
    的两厘米短线，方向取自距离场的切向 —— 那是绒，不是头发。头发与绒的分别不在粗细，在**每根都有一个起点，而
    所有起点都在头皮上**。

    「沿周长等距」在像素网格上只能近似：轮廓是八连通的锯齿，所以这里按极角排序，再要求相邻两点至少隔
    `spacing` 像素。近似的代价是间距有一两个像素的抖动，而那正好是发根该有的样子。
    """
    from scipy import ndimage

    edge = mask & ~ndimage.binary_erosion(mask)
    ys, xs = np.nonzero(edge)
    keep = ys < limit
    ys, xs = ys[keep], xs[keep]
    order = np.argsort(np.arctan2(ys - CY, xs - CX))
    picked = []
    for index in order:
        point = (float(xs[index]), float(ys[index]))
        if not picked or math.hypot(point[0] - picked[-1][0], point[1] - picked[-1][1]) >= spacing:
            picked.append(point)
    return picked


def hair_marks(mask, seed=73000, depth=112.0, spacing=2.6, per_bundle=7):
    """**头发是一束一束，每束从发根出发：方向由头皮给，弧线由重力给。**

    一条发丝的生成方式是**积分一个方向**，而不是在两个点之间连一条线：

    ```
    方向 = 上一步的方向（七成） + 向下（重力） + 切向（流向，束内共用） + 一点噪声
    ```

    三个分量各自对应一件真事。**七成**是惯性，所以发丝是弯的而不是折的；**向下**让每条发丝最终都垂下来，哪怕它
    从颅顶出发时是朝上的；**切向**让同一束里的几根朝同一个方向流，束与束之间方向不同 —— 那才是「一束一束」，
    而不是「一丛一丛」的绒。

    发根沿脸轮廓密排（`spacing` 二点六像素，这一圈周长约一千五百像素，于是六百根左右）。根部彼此重叠成一团深色，
    往外逐渐分离成丝：**密与疏的分布由发根的位置给，不需要再铺一层底色。**

    **长度不由「离脸多远」给，由这一次抖动给。** 上一版让外缘的笔更长，那是为了让环带不显得空；现在发丝本身
    就是长度，一条长丝自然穿过环带，而「外缘更长」这个规则会让所有发丝在同一个半径上收尾 —— 那是剪过的头发。
    """
    from scipy import ndimage

    rng = random.Random(seed)
    outside = ndimage.distance_transform_edt(~mask)
    limit = CY + FACE_H * 0.62
    # **外缘的梯度比脸内部更乱**，因为那里没有第二侧的约束；磨得重一点，否则发丝在颅顶会朝四面八方走。
    field = ndimage.gaussian_filter(outside, 9.0)
    gy, gx = np.gradient(field)

    roots = hair_roots(mask, limit, spacing)
    # **一束一次抽样。** 束内的发丝共用一个切向与一个长度尺度，束间不同；`gap` 让每七束留一道缝，缝不是空的，
    # 只是那一束缺了几根 —— 头发分成束，靠的正是这种不均匀。
    bundles = {}
    for index in range(len(roots)):
        key = index // per_bundle
        if key not in bundles:
            local = random.Random(seed + key * 977)
            bundles[key] = (local.uniform(-0.85, 0.85), local.uniform(0.80, 1.25),
                            local.random() < 0.18)

    fig = project.Project(width=W, height=H, title='figure hair')
    for index, (rx, ry) in enumerate(roots):
        curl, scale, gap = bundles[index // per_bundle]
        if gap and index % per_bundle == 0:
            continue
        dx, dy = float(gx[int(ry), int(rx)]), float(gy[int(ry), int(rx)])
        norm = math.hypot(dx, dy) or 1.0
        nx, ny = dx / norm, dy / norm
        tx, ty = -ny, nx
        # **下缘要渐薄，不能是一条横线。** 截断的边界是水平的 —— 上一版在那里留下了锯齿一样的硬边，读成「一顶
        # 帽子」。头发收尾靠的是发丝越来越少、越来越淡，不是刀切。
        fade = 1.0 if ry < limit - 60.0 else max(0.0, (limit - ry) / 60.0)
        if fade <= 0.05:
            continue
        steps = 6 + int(3 * rng.random())
        length = (78.0 + 74.0 * rng.random()) * scale
        seg = length / steps
        # 起点沿法向错开一两像素：六百根发丝里若有几十根从同一个像素出发，根部会读出几个钉子。
        x, y = rx + nx * rng.uniform(0.0, 2.5), ry + ny * rng.uniform(0.0, 2.5)
        dirx, diry = nx, ny
        points = [(x, y)]
        for _ in range(steps):
            dirx = dirx * 0.70 + tx * curl * 0.12 + rng.uniform(-0.05, 0.05)
            diry = diry * 0.70 + 0.52 + ty * curl * 0.12 + rng.uniform(-0.05, 0.05)
            length_now = math.hypot(dirx, diry) or 1.0
            dirx, diry = dirx / length_now, diry / length_now
            x, y = x + dirx * seg, y + diry * seg
            points.append((x, y))
        width = rng.uniform(6.0, 10.5)
        widths = [width * (1.0 - 0.70 * step / steps) for step in range(steps + 1)]
        # **黑发的层次靠反光，不靠「更浅的头发」。** 一束头发里真正被看见的是几根反光的丝，它们的颜色不是把
        # 发色往灰里调，而是往偏红的高光走，并且要淡 —— 浓的高光读成挑染。所以三成是亮丝、七成是本色丝，
        # 亮丝再薄一层。上一版所有发丝都在深色区间里，画在深色发团上等于没有画。
        if rng.random() < 0.32:
            tone = mix(HAIR_MID, (136, 118, 128), rng.uniform(0.25, 0.80))
            alpha = rng.uniform(0.30, 0.62) * fade
        else:
            tone = mix(HAIR_DARK, HAIR_MID, rng.uniform(0.15, 0.85))
            alpha = rng.uniform(0.42, 0.80) * fade
        fig.add_stroke(core.stroke_record(
            points, 'brush', seed=seed + index * 31, colour=hexed(tone), soft=0.7,
            width_profile=widths, alpha_profile=[alpha] * len(points),
            absolute_width=True, edge=rng.uniform(2.6, 5.0), height=0.4),
            stage='line', layer='hair', note='')
    return fig


def nose_marks(nose_y, brow_y, seed=74000):
    """**鼻子的全部信息是两条边、一个底、一点亮。**

    它不由轮廓算，因为它不在轮廓上 —— 它是脸**内部**的第一个东西。而它的两个端点现在都由三停给：鼻梁从眉线起，
    鼻底落在第二停的末尾。上一版写的是脸的零点三三半高，那是照着眼睛的位置调的；三停给零点二九，差十六像素 ——
    差得不多，但那是「猜的」与「算的」的分别，而猜出来的那一版没有人能说它错在哪里。

    而**宽度来自脸，不来自眼**：鼻翼大约是脸宽的四分之一，这条比「鼻子是眼睛的多少倍」稳，因为它不随眼睛
    的大小改。
    """
    fig = project.Project(width=W, height=H, title='figure nose')
    top = CY + brow_y
    tip = CY + nose_y
    half = FACE_W * 0.13
    # 鼻梁右侧的影：光从左上过来，所以影子在右下，且它是一条宽带，不是一个轮廓。
    fig.add_stroke(core.stroke_record(
        [(CX + half * 0.40, top), (CX + half * 0.80, CY + FACE_H * 0.16), (CX + half, tip - 7.0)],
        'brush', seed=seed, colour=hexed(mix(SKIN_DARK, SKIN_MID, 0.45)), soft=1.0,
        width_profile=[7.0, 10.0, 6.0], alpha_profile=[0.20, 0.30, 0.26],
        absolute_width=True, edge=11.0), stage='line', layer='nose', note='')
    # **鼻底是这张脸上最暗的一条短弧。** 它比任何一条睑线都短，而它决定了「这个人有没有鼻子」。
    fig.add_stroke(core.stroke_record(
        [(CX - half, tip), (CX, tip + 6.0), (CX + half, tip)],
        'brush', seed=seed + 1, colour=hexed(mix(SKIN_DARK, SKIN_MID, 0.20)), soft=0.8,
        width_profile=[5.0, 7.0, 5.0], alpha_profile=[0.40, 0.54, 0.40],
        absolute_width=True, edge=3.0), stage='line', layer='nose', note='')
    # 鼻头的一点亮，位置在鼻梁的影子对面。
    fig.add_stroke(core.stroke_record(
        [(CX - 6.0, tip - 13.0), (CX + 2.0, tip - 10.0)],
        'brush', seed=seed + 2, colour=hexed(SKIN_LIGHT), soft=1.2,
        width_profile=[10.0, 8.0], alpha_profile=[0.26, 0.20],
        absolute_width=True, edge=10.0), stage='line', layer='nose', note='')
    return fig


def mouth_marks(mouth_y, seed=75000):
    """**口缝是一条线，嘴唇是它上下两层很淡的色。**

    嘴的宽是脸的零点四倍 —— 比鼻翼宽，比两眼的内角窄一点，而这条比例是「一张脸放松着」的样子。第一版没有嘴，
    于是下半张脸是一整片肤色，读成面具。

    **高度由三停的第三段给**：鼻底到下巴这一段里，口裂落在上三分之一（`standards.face` 的 `mouth_third`）。上一版
    写在脸的零点五二半高处，比三停给的位置低十八像素 —— 而那一版是照「下巴到鼻底看着差不多一半」摆的。三停
    给的不是中点：第三段里嘴偏上，下巴那一段留白更多，这也是「安静」与「面无表情」的分别。

    颜色不是红：`LIP` 是这张脸上的第三个颜料，而它比皮肤**暗且偏紫**，不是加亮度。嘴唇的红是它自己的颜色，不是
    脸颊的颜色调亮。
    """
    fig = project.Project(width=W, height=H, title='figure mouth')
    y = CY + mouth_y
    half = FACE_W * 0.20
    fig.add_stroke(core.stroke_record(
        [(CX - half, y - 4.0), (CX - half * 0.34, y + 4.0),
         (CX + half * 0.34, y + 4.0), (CX + half, y - 4.0)],
        'brush', seed=seed, colour=hexed(mix(LIP, (58, 28, 30), 0.45)), soft=0.6,
        width_profile=[2.0, 4.4, 4.4, 2.0], alpha_profile=[0.34, 0.62, 0.62, 0.34],
        absolute_width=True, edge=2.2), stage='line', layer='mouth', note='')
    fig.add_stroke(core.stroke_record(
        [(CX - half * 0.60, y + 14.0), (CX, y + 20.0), (CX + half * 0.60, y + 14.0)],
        'brush', seed=seed + 1, colour=hexed(mix(LIP, SKIN_LIGHT, 0.30)), soft=1.1,
        width_profile=[6.0, 9.0, 6.0], alpha_profile=[0.28, 0.40, 0.28],
        absolute_width=True, edge=6.0), stage='line', layer='mouth', note='')
    return fig


def collect(drawings, fills=(), title='figure'):
    """**「改某一笔」需要的是一份工程，不是一张图。**

    每个 `*_marks` 各自返回一个 `Project`，因为它们各自是一次独立的构图：眉算一次、眼算一次、头发一次。而一张
    画最终是一份工程 —— `--marks` 要在它上面把四千多笔列出来，`--revise` 要能改其中一条。PSD 里的像素没有
    身份，工程里的笔有，而这个库的产品是后者。

    **`Mark.geometry` 已经是一份 `stroke_record` 的形状**，因为 `add_stroke` 的白名单当初就是从那里取的；所以
    这里要补的只有 `colour`，它在 `appearance` 里，因为「没有颜色」意味着「角色决定」。

    **`fills` 先于所有笔加进去，而且必须如此。** `render_marks` 按顺序合成，而背景与脸的底色是最下面那两层。
    这两个东西本来是 `fill_polygon` 画进像素的，而像素不进工程 —— 于是从工程渲染出来的图少了它们：背景成了
    纸色，脸成了透光的，与 `main` 直接画的那一张不是同一张画。**一份「工程就是这张画」的工程，缺一层就是缺
    一层。**
    """
    merged = project.Project(width=W, height=H, title=title)
    for fill in fills:
        merged.add_fill(core.Region(points=[list(p) for p in fill['points']], d=fill.get('d', '')),
                        stage=fill.get('stage', 'colour'), colour=fill['colour'],
                        layer=fill.get('layer', ''), note=fill.get('note', ''))
    for drawing in drawings:
        for mark in drawing.marks:
            # **`as_record()` 是第三处副本的替代。** 从 `geometry` 抄回一份记录曾经在 `render_marks` 与这里各写
            # 一遍，而记录的形状由 `geometry` 定，所以重建该归它自己。
            merged.add_stroke(mark.as_record(), stage=mark.stage, layer=mark.layer,
                              note=(mark.provenance or {}).get('note', ''))
    return merged


def main():
    os.makedirs(OUT, exist_ok=True)
    place, stack = paint_export.stacker(W, H)
    picture = r.Layer(W, H)
    r.fill_polygon(picture, [(-20.0, -20.0), (W + 20.0, -20.0), (W + 20.0, H + 20.0), (-20.0, H + 20.0)],
                   (28, 24, 28), 1.0)
    picture = place(picture, 'ground', picture)
    face, mask = face_marks()
    # **底色先铺，再叠明暗。** 板绘的皮肤是两层：一层不透明的肤色，一层很淡的起伏。这一版之前只有后者，于是
    # 背景从笔缝里透上来，脸读成一块暗斑 —— 那不是颜色选错，是少了一层。两层之后笔才是在**画**，不是在
    # 猜底下有多深。
    skin = r.Layer(W, H)
    r.fill_polygon(skin, outline(), SKIN_MID, 1.0)
    picture = place(picture, 'face',
                    r.clip(r.blend(skin, r.render_marks([m.to_dict() for m in face.marks], W, H, sweep=True)),
                           soft_mask(mask)))
    # **那组比值现在住在库里**（`standards.face`），因为判据比画法更可复用：换一张脸这组数还成立，而这支笔
    # 不成立。库里也写着哪三个数是书上的、哪几个是这个库试出来的 —— 混在一起的那一天，就没有人知道哪个能改。
    #
    # **而它现在算在最前面**，因为三停不只管眼睛：眉、鼻底、嘴三处高度都从它取。判据进了库之后，用它的地方就该
    # 只剩「传下去」这一个动作，否则库里的数改了而这支笔没改，那种不一致是看不见的。
    ratios = standards.face(FACE_W, FACE_H)
    # **鼻与嘴画在脸上，头发之上或之下都不影响** —— 头发只到脸的轮廓附近，而这两样在脸的中线上。
    nose = nose_marks(ratios['nose_y'], ratios['brow_y'])
    mouth = mouth_marks(ratios['mouth_y'])
    for name, drawing in (('nose', nose), ('mouth', mouth)):
        picture = place(picture, name,
                        r.render_marks([m.to_dict() for m in drawing.marks], W, H, sweep=True))
    # **头发画在脸之上，而且分两层：体积在下，发丝在上。** 鬓与刘海压在额头与颊上，而那是头发与脸唯一的接触
    # 方式；若它在脸之下，两侧会是一条被裁干净的边，读成「戴了个头套」。
    #
    # **两层是这一轮试出来的。** 只有密集短笔的那一版有体积没方向；只有发根长丝的那一版有方向没体积，画出来是
    # 秃的。两次各缺一半，因为它们本来是同一件事的两半。
    hair = hair_marks(mask, spacing=1.9)
    # **发团是两块拼起来的：发际线以上那一片，加脸外那一圈厚度。** 一块多边形说不出这两件事 —— 它的内边界在
    # 额头是发际线、在太阳穴是脸的轮廓，而一条边画不出两种意思，于是它会在太阳穴横着盖住半张脸（试过一次，
    # 画出来像戴了个黑头套）。分开之后每一块只说一件事，下缘再各自渐隐。
    rows = np.arange(H)[:, None]
    columns = np.arange(W, dtype=float)[None, :]
    head = mask_of(grown_outline())
    above = np.where(head, 1.0, 0.0) * (rows < CY + FACE_H * hairline_at(columns))
    rim = np.where(head & ~mask, 1.0, 0.0) * np.clip((CY + FACE_H * 0.50 - rows) / 70.0, 0.0, 1.0)
    picture = place(picture, 'hair base',
                   colour_layer(np.maximum(above, rim), (46, 38, 45), bottom=(24, 20, 24),
                                span=(70.0, 430.0)))
    picture = place(picture, 'hair', r.render_marks([m.to_dict() for m in hair.marks], W, H, sweep=True))
    eye_w = ratios['eye_width']
    eye_h = ratios['eye_height']
    eyes_y = CY + ratios['eye_dy']
    brow_line = CY + ratios['brow_y']
    brows, eyes = [], []
    for name, sign in (('left', -1.0), ('right', 1.0)):
        centre = (CX + sign * eye_w, eyes_y)
        brow = brow_marks(centre, eye_w, eye_h, brow_line, seed=72000 + (19 if sign > 0 else 0))
        brows.append(brow)
        picture = place(picture, 'brow %s' % name,
                        r.render_marks([m.to_dict() for m in brow.marks], W, H, sweep=True))
        eye = eye_marks(centre, eye_w, eye_h, seed=71000 + (17 if sign > 0 else 0))
        eyes.append(eye)
        picture = place(picture, 'eye %s' % name,
                        r.render_marks([m.to_dict() for m in eye.marks], W, H, sweep=True))
    path = os.path.join(OUT, 'figure.png')
    r.save_png(picture, path, background=(28, 24, 28))
    # **同一份 stack 去两个地方，因为它就是这张画的结构。** 这张脸一直只写 PNG，而它的图层从画的时候就分好
    # 了 —— 一份 PNG 只能看，一份分层 PSD 才能拿去 SAI 里关掉头发看看剩下什么，而后者才是这个库的产品。
    psd_path, layers = paint_export.export(stack, OUT, 'figure')
    # **而工程文件是第三种出口，也是「能改某一笔」唯一的一种。** PSD 里只有像素：层名对、透明度对、顺序对，
    # 而一支笔与它旁边那一支在里面没有分别。工程文件里每一笔有一个 id。
    drawing = collect(
        [face, nose, mouth, hair] + brows + eyes,
        fills=[
            {'points': [(-20.0, -20.0), (W + 20.0, -20.0), (W + 20.0, H + 20.0), (-20.0, H + 20.0)],
             'colour': hexed((28, 24, 28)), 'layer': 'ground', 'note': 'the ground'},
            {'points': outline(), 'colour': hexed(SKIN_MID), 'layer': 'face', 'note': 'the base coat'},
        ])
    project_path = os.path.join(OUT, 'figure.json')
    project.save_project(drawing, project_path)
    print('%s  face %d marks, hair %d marks' % (path, len(face.marks), len(hair.marks)))
    print('%s  %d layers' % (psd_path, layers))
    print('%s  %d marks, addressable by id' % (project_path, len(drawing.marks)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
