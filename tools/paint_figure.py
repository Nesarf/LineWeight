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

from lineweight import core, project, pigment  # noqa: E402
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
# **而第一版的宽度写窄了三分之一**：`FACE_H / FACE_W` 给出来是一比一点八，而真实的头（从颅顶到下巴）是一比一点
# 四。那个差在画面上不是「有点长」，是**读成一颗杏仁**。脸的宽度由颧骨定，不由额头定 —— 额头在上半部，而它连着
# 的不是一条直的边。
FACE = [
    (0.00, -1.00), (0.36, -0.98), (0.58, -0.88), (0.72, -0.66),
    (0.80, -0.34), (0.78, -0.08), (0.68, 0.18), (0.52, 0.42),
    (0.32, 0.60), (0.17, 0.71), (0.00, 0.76),
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


def face_marks(seed=70701):
    """脸上的笔：**沿等高线走，而「等高线」是到轮廓的距离。**

    第一版按椭圆环撒笔，画出来是一块棕色的方 —— 两个错都在同一处：环只走了上半圆（`sin` 只取正值），于是下颌
    一条笔也没有；而环的半径与轮廓的形状无关，于是笔铺到轮廓外面又被裁掉。

    **改成距离场之后两件事同时对了。** 脸的内部每一点有一个「离轮廓多远」，那个场的等高线就是脸自己的走向 ——
    额头是一圈，鼻梁是两条，下颌是另一圈。而笔画沿等高线的切线，也就是垂直于梯度。

    `depth` 反着用：轮廓上最暗，往里亮起来。**而它只是一层**，因为这一版先要确认「位置对」，再谈有几层光。
    """
    from scipy import ndimage

    rng = random.Random(seed)
    mask = mask_of(outline())
    depth = ndimage.distance_transform_edt(mask)
    depth = (depth / max(1.0, float(depth.max()))) ** 0.75
    # **脊上要磨一下。** 距离场在一个瘦长的形状里有一条中轴脊，梯度在那里不连续 —— 而笔的方向取自梯度，于是脸的正
    # 中央出现一块三角形，笔在那里互相交叉。**那不是噪声，是「一个函数在一条线上没有导数」画在纸上的样子。**
    # 模糊六像素换回一个连续的方向场，而代价只是最亮的那一条稍微塌一点。
    depth = ndimage.gaussian_filter(depth, 6.0)
    gy, gx = np.gradient(depth)
    fig = project.Project(width=W, height=H, title='figure face')
    for y in range(0, H, 8):
        for x in range(0, W, 8):
            if not mask[y, x] or rng.random() > 0.72:
                continue
            here = float(depth[y, x])
            dx, dy = float(gx[y, x]), float(gy[y, x])
            norm = math.hypot(dx, dy) or 1.0
            tx, ty = -dy / norm, dx / norm
            length = 18.0 + 30.0 * here
            tone = jitter(skin_colour(here), 5.0, rng)
            fig.add_stroke(core.stroke_record(
                [(x - tx * length * 0.5, y - ty * length * 0.5 + rng.uniform(-1.5, 1.5)),
                 (x + tx * length * 0.5, y + ty * length * 0.5 + rng.uniform(-1.5, 1.5))],
                'brush', seed=seed + x * 7 + y, colour=hexed(tone), soft=0.9,
                width_profile=[rng.uniform(9.0, 15.0)] * 2,
                alpha_profile=[rng.uniform(0.34, 0.52)] * 2,
                absolute_width=True, edge=rng.uniform(5.0, 9.0), height=0.3),
                stage='line', layer='face', note='')
    return fig, mask


def main():
    os.makedirs(OUT, exist_ok=True)
    place, stack = paint_export.stacker(W, H)
    picture = r.Layer(W, H)
    r.fill_polygon(picture, [(-20.0, -20.0), (W + 20.0, -20.0), (W + 20.0, H + 20.0), (-20.0, H + 20.0)],
                   (28, 24, 28), 1.0)
    picture = place(picture, 'ground', picture)
    face, mask = face_marks()
    picture = place(picture, 'face',
                    r.clip(r.render_marks([m.to_dict() for m in face.marks], W, H, sweep=True), soft_mask(mask)))
    path = os.path.join(OUT, 'figure.png')
    r.save_png(picture, path, background=(28, 24, 28))
    print('%s  %d marks' % (path, len(face.marks)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
