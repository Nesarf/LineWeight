"""几座山，水墨：**远近由墨的浓淡与厚度决定，不由轮廓决定。**

山水是水墨的主科，而它这一条正好压在这条线唯一会做错的地方上 —— 一座山没有轮廓。真正被画下来的只有山脊那
一条线，以及墨从脊往下走多远；山脚的边、山与山的交界、云的位置，都是**墨停下来**形成的。

所以这个文件里没有「山的多边形」。有的是：

* **一层铺开的墨**，alpha 从上往下渐淡 —— 那一层就是这一座山，而**它淡到零的地方就是这座山的底**。
* **沿脊的短笔**（皴），方向顺着坡。它给山石体积，而它短得不可能连成一条边。
* **留白**。云与水面不画：它们是纸，而纸已经在那里了。

远近是三座山，三档浓度，三个「往下多深」。**这是画面里唯一可数的东西，也是唯一说得清的部分**：为什么第三座
山淡、为什么它的底在两座山之间 —— 那是空气透视，不是构图偏好。
"""
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineweight import core, project      # noqa: E402
from lineweight import raster as r        # noqa: E402

W, H = 1400, 900
OUT = os.environ.get('LAND_OUT') or os.path.join(os.getcwd(), 'landscape')
PAPER = (234, 228, 214)
INK = (28, 24, 30)
#: 焦、浓、重、淡、清 —— 与 `paint_ink` 里同一套，同样借自常识而不是任何一篇引用。
INK_LEVELS = (0.88, 0.70, 0.50, 0.30, 0.14)

# **三层山，三层浓度，三个深度。** 远山只有脊下七十像素的墨，中山一百六十，近山三百 —— 而它们淡到零的地方，
# 读起来就是山脚。第三条与第一条的浓度差不到两档，可它们的「厚度」差四倍，这个比例才是远近的来源。
#
# **而两端要在画外。** 第一版的脊从 x=60 开始，于是山体多边形的左边沿一条斜线落下来，读成一个竖着的边 ——
# 一座山没有那样的边。两端延到画外，山就只是「这一块地里看得见的那部分」。
# **而三座山的走向要不一致。** 前两版的脊都是从左下到右上的一条缓波，三层叠起来是三条平行带。真实的山有各自的
# 走向：远山陡、主峰一柱；中山缓、拉得长；近山碎、峰谷都近。**远处的东西不是近处的缩小版。**
FAR = [(-140, 700), (60, 640), (200, 380), (300, 470), (420, 520), (540, 400), (640, 460),
       (780, 330), (880, 440), (1010, 500), (1150, 410), (1300, 470), (1540, 600)]
MID = [(-140, 720), (80, 590), (250, 490), (400, 560), (560, 450), (700, 530), (860, 460),
       (1010, 570), (1170, 500), (1330, 590), (1540, 640)]
# **而近山要留出水面。** 上一版的近山脊一路压到画底（y 900），于是水被它整片盖住 —— 一张山水画没有水就不是山水。
# 脊抬到五百上下、深度收到二百二，画底那一条才空出来，而空出来的部分是**纸** —— 水不画，它是没有被墨碰到的地方。
#
# **再加一处崖。** 一条只有缓波的脊是丘，不是山：山在某一处突然掉下去，而那一处是整座山最重的地方。断崖用三个
# 靠得很近的点给出（水平二十像素、垂直一百二十），因为平滑会把任何一处陡降磨圆 —— 给它三个点，磨完还是一条崖。
NEAR = [(-140, 800), (40, 700), (170, 560), (250, 620), (400, 690), (520, 540), (600, 580),
        (760, 650), (890, 530), (910, 660), (925, 770), (1010, 590), (1160, 690), (1290, 620),
        (1430, 720), (1540, 810)]


def ridge_curve(points, per=14, rounds=7):
    """一条圆润的山脊：**先按线性插值加密，再做几遍邻域平均。**

    一开始直接拿十一条折线当脊用，画出来是锯齿 —— 山脊没有尖角，它的每一个转折都是圆的。**而样条是错的工具**：
    它会穿过每一个原始点，于是每一点留下一个拐点，折线变成了「抖动的折线」。邻域平均反过来：它不保留任何一个
    原始点，只保留它们的走向。
    """
    dense = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        for k in range(per):
            t = k / float(per)
            dense.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    dense.append((float(points[-1][0]), float(points[-1][1])))
    xs = [p[0] for p in dense]
    ys = [p[1] for p in dense]
    for _ in range(rounds):
        ys = ([ys[0]] + [(ys[i - 1] + 2.0 * ys[i] + ys[i + 1]) / 4.0 for i in range(1, len(ys) - 1)]
              + [ys[-1]])
    return list(zip(xs, ys))


def wash(level):
    return tuple(PAPER[i] + (INK[i] - PAPER[i]) * level for i in range(3))


def smooth_run(values, width=17):
    """把一条沿 x 的序列抹平，边界用两端自身延拓。

    **这一步不是修饰，是那个竖条纹的解药。** `top_of` 是每列山脊的**像素下标**，而它是一个整数序列；对它求梯度，
    相邻两列的差只有零或一，但这个「零或一」本身就是一次跳变。拿这个跳变当 alpha 的系数，相邻列的墨量就一格一
    格地差 —— 画面上是一层竖直的细线，而它盖过山、草、水，看起来像渲染器的 bug。**它确实是：量化之后再求导，
    得到的是量化步的图案，不是坡。**
    """
    values = np.asarray(values, dtype=np.float64)
    if values.size < width:
        return values
    padded = np.concatenate([np.full(width, values[0]), values, np.full(width, values[-1])])
    kernel = np.ones(width) / float(width)
    return np.convolve(padded, kernel, mode='same')[width:width + values.size]


def ridge_layer(ridge, depth, level, seed, ceiling=0.74):
    """一次铺开的墨：**从脊往下淡到零，而「往下多深」是这一座山的远近。**

    「往下多深」不是画出来的 —— alpha 走到零，墨就没了，那里就是山脚。所以这一层不需要任何轮廓：它是一次渐变，
    不是一个形状。

    **山的多边形只用来问「哪一列从哪里开始」**，它不参与画面。这一句是整条水道与油画那条路的分界：油画那条
    路边是给定的，而这里边是 alpha 走到零的地方。

    `ceiling` 是一次的上限，不是山的总量 —— 一座山由几遍这样的墨叠起来（见 `mountain`）。
    """
    polygon = ridge + [(W + 60.0, H + 60.0), (-60.0, H + 60.0)]
    mask_layer = r.Layer(W, H)
    r.fill_polygon(mask_layer, polygon, (255, 255, 255), 1.0)
    solid = np.frombuffer(bytes(mask_layer.data), dtype=np.uint8).reshape(H, W, 4)[:, :, 3] > 127
    top_of = np.argmax(solid, axis=0)
    tone = wash(level)
    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rows = np.arange(H, dtype=np.float64)[:, None]
    # 从上往下淡：脊下零像素是满，`depth` 像素处是零。指数 0.8 让它开头更快、尾巴更长 —— 一块石头是上面重、
    # 下面拖着，而不是一条直线衰减。
    fall = np.clip(1.0 - (rows - top_of[None, :]) / max(1.0, float(depth)), 0.0, 1.0) ** 0.8
    # **每一遍的墨要沿 x 起伏，否则积墨只是一叠平行带。** 四遍同一条渐变只会把边加深四次；真实的一层墨是有的
    # 地方多、有的地方少，叠起来才斑驳 —— 而斑驳就是石头的量感。
    mottle = 0.70 + 0.30 * np.sin(np.arange(W, dtype=np.float64) * 0.011 + seed * 1.7)
    # **而墨还要按坡的朝向分阴阳，这是前几版最缺的一项。** 只按「从上往下」浓淡，画出来是一条带宽度的波 —— 因为
    # 真实的山不只有高度，还有**哪一侧朝着光**：上升的一坡留白，下降的一坡积墨，两坡的分界就是山脊。这一项加
    # 上去之后，同一座山的两边才不一样重，而那正是它能读成一个立体的东西而不是一条波的全部理由。
    #
    # **而它第一次修成了台地，因为 `clip` 会在峰顶跳。** 坡在峰的两侧符号相反，一 `clip` 就在峰顶从 1 跳到 0.1，
    # 于是每座山被切成浓的一半和淡的一半，接缝是一条竖直的边。换成 `tanh`：同一个判据，但没有边界 —— 阴阳是转过
    # 去的，不是分开的。
    slope = np.gradient(smooth_run(top_of))
    facing = 0.42 + 0.58 * (0.5 + 0.5 * np.tanh(-slope * 1.6))
    alpha = np.where(solid, fall, 0.0) * ceiling * mottle[None, :] * facing[None, :]
    rgba[:, :, 0] = int(round(tone[0]))
    rgba[:, :, 1] = int(round(tone[1]))
    rgba[:, :, 2] = int(round(tone[2]))
    rgba[:, :, 3] = (alpha * 255.0).astype(np.uint8)
    layer = r.Layer(W, H)
    layer.data[:] = rgba.tobytes()
    return layer, solid


def mountain(ridge, depth, level, seed, passes=4):
    """一座山是**几遍积墨**叠起来的，不是一次渐变。

    第一版每座山只有一层，画出来是三条半透明的波带 —— 而真实的山水是积墨：一层干了再上一层，后一遍的脊比前一遍
    低一点、淡一点，于是石头的量感是叠出来的。四遍、每遍的脊下移十六个百分点、浓度递减一成：**同一种墨在没有
    变浓的情况下变成了石头**，因为它叠了四次而每次都在不同的地方。
    """
    picture = r.Layer(W, H)
    solid = None
    for step in range(max(1, passes)):
        shifted = [(x, y + depth * 0.16 * step) for x, y in ridge]
        layer, solid = ridge_layer(shifted, depth * (1.0 - 0.14 * step),
                                   level * (1.0 - 0.10 * step), seed + step)
        picture = r.blend(picture, layer, 'normal', 1.0)
    return picture, solid


def cun_marks(ridge, solid, level, groups, seed):
    """皴：**成组**的短笔，方向顺着坡。

    第一版是沿脊均匀撒点、每一笔朝法线落下去 —— 画出来是一层草，因为「均匀」正好是岩石没有的性质。真实的皴法
    （披麻、斧劈）都是**一组一组**的：几笔到十几笔起于相近的地方、朝同一个坡向、间距只差几个像素，组与组之间
    留空。**一个坡面是一组笔，不是一片噪声。**

    而每组的起点落在脊上、往下走不同长度：组内平行，组间无关 —— 这两件事同时成立，石头才读得出来。
    """
    rng = random.Random(seed)
    top_of = np.argmax(solid, axis=0)
    fig = project.Project(width=W, height=H, title='cun')
    colour = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in wash(level))
    index = 0
    for _ in range(groups):
        anchor = rng.uniform(ridge[1][0], ridge[-1][0])
        lean = rng.uniform(-0.42, 0.42)
        reach = rng.uniform(38.0, 110.0)
        count = rng.randint(5, 11)
        gap = rng.uniform(4.0, 9.0)
        for i in range(count):
            column = int(round(anchor + i * gap + rng.uniform(-1.2, 1.2)))
            if not (0 <= column < W) or not solid[:, column].any():
                continue
            y = min(H - 3.0, float(top_of[column]) + rng.uniform(3.0, 26.0))
            row = int(y)
            if not solid[row, column]:
                continue
            left = float(top_of[max(0, column - 6)])
            right = float(top_of[min(W - 1, column + 6)])
            slope = (right - left) / 12.0
            ux, uy = -slope, 1.0
            norm = math.hypot(ux, uy)
            ux, uy = ux / norm, uy / norm
            ux, uy = (ux * math.cos(lean) - uy * math.sin(lean),
                      ux * math.sin(lean) + uy * math.cos(lean))
            length = reach * rng.uniform(0.55, 1.05)
            fig.add_stroke(core.stroke_record(
                [(column, y), (column + ux * length * 0.5, y + uy * length * 0.5),
                 (column + ux * length, y + uy * length)], 'brush', seed=3000 + index,
                colour=colour, soft=0.7, edge=rng.uniform(1.8, 4.4),
                bristle=0.46, bristle_pitch=rng.uniform(2.4, 4.2),
                width_profile=[rng.uniform(2.4, 4.6), rng.uniform(3.8, 7.0), rng.uniform(1.2, 2.8)],
                alpha_profile=[0.26, 0.50, 0.12], absolute_width=True),
                stage='line', layer='paint', note='')
            index += 1
    return fig


def trees_on_ridge(ridge, solid, level, count, seed):
    """山顶的树：**几十粒墨，而它们让山读成山。**

    一条光脊的石头没有尺度 —— 观者不知道该拿什么去比。树给了它：人都知道一棵树多大，所以一粒墨落在脊上，那一
    整片就变成了几十米。**这是整个画面里最经济的一笔**，因为它同时交代了远近、坡向，和「这片山有人走过」。

    每棵树是一小簇三到六笔：中间一笔高而直（干），旁边几笔短而斜（枝）。它们比皴浓，也比皴小 —— 皴说石头，树说
    尺度，而两者的浓度差就是这两件事的区别。
    """
    rng = random.Random(seed)
    top_of = np.argmax(solid, axis=0)
    fig = project.Project(width=W, height=H, title='trees')
    colour = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in wash(min(0.92, level + 0.34)))
    index = 0
    planted = 0
    while planted < count:
        # **树是一丛一丛的，不是均匀撒的。** 种子落在母树旁边，风把它送出去是一段一段的 —— 所以山脊上的树有疏有
        # 密，密的地方两三棵并排，疏的地方一整段没有。均匀撒出来的是「一片苗」，而苗不是林。
        anchor = rng.uniform(ridge[1][0], ridge[-1][0])
        for k in range(rng.randint(2, 6)):
            column = int(round(anchor + k * rng.uniform(6.0, 13.0)))
            planted += 1
            if not (0 <= column < W) or not solid[:, column].any():
                continue
            base = float(top_of[column]) + rng.uniform(0.0, 6.0)
            height = rng.uniform(9.0, 22.0)
            if rng.random() < 0.42:
                continue
            fig.add_stroke(core.stroke_record(
                [(column, base), (column + rng.uniform(-1.5, 1.5), base - height * 0.55),
                 (column + rng.uniform(-3.0, 3.0), base - height)], 'brush', seed=4000 + index,
                colour=colour, soft=0.6, edge=1.4, bristle=0.30, bristle_pitch=2.2,
                width_profile=[3.0, 2.2, 1.0], alpha_profile=[0.72, 0.62, 0.34],
                absolute_width=True), stage='line', layer='paint', note='')
            index += 1
            # **枝要短而细，否则一棵树会读成一个人。** 第一版的斜笔有五到九像素、宽二点二，两笔一分就是「人」字 ——
            # 而真实的远树在画面上只是主干旁的两三道细痕，比主干短一半以上。枝越像枝，树越像树；枝越清楚，树越
            # 像符号。
            for _ in range(rng.randint(1, 2)):
                side = rng.choice((-1.0, 1.0))
                fig.add_stroke(core.stroke_record(
                    [(column + side * 1.0, base - height * 0.30),
                     (column + side * rng.uniform(2.0, 4.5), base - height * rng.uniform(0.42, 0.74))],
                    'brush', seed=4000 + index, colour=colour, soft=0.6, edge=1.2,
                    width_profile=[1.6, 0.6], alpha_profile=[0.48, 0.20], absolute_width=True),
                    stage='line', layer='paint', note='')
                index += 1
    return fig


def water_marks(seed=3100):
    """水：**几笔横向的淡墨，而它们的间距比它们的长度大。** 水不是画出来的，是留白加上几条暗示。"""
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='water')
    for i in range(22):
        y = rng.uniform(760.0, 880.0)
        x = rng.uniform(-40.0, W + 40.0)
        length = rng.uniform(90.0, 260.0)
        fig.add_stroke(core.stroke_record(
            [(x - length * 0.5, y), (x, y + rng.uniform(-2.0, 2.0)), (x + length * 0.5, y)],
            'brush', seed=3100 + i, colour='#%02x%02x%02x' % tuple(
                max(0, min(255, int(round(v)))) for v in wash(INK_LEVELS[3])),
            soft=0.9, edge=8.0, bristle=0.30, bristle_pitch=rng.uniform(4.0, 7.0),
            width_profile=[6.0, 9.0, 5.0],
            alpha_profile=[0.10, 0.22, 0.08], absolute_width=True), stage='line', layer='paint', note='')
    return fig


def main():
    os.makedirs(OUT, exist_ok=True)
    picture = r.Layer(W, H)
    r.fill_polygon(picture, [(-20.0, -20.0), (W + 20.0, -20.0), (W + 20.0, H + 20.0), (-20.0, H + 20.0)],
                   PAPER, 1.0)
    marks = 0
    rough = r.PAPERS['rough']
    # **远山不皴。** 「遠山無皴，遠水無波，遠人無目 —— 非無也，如無耳」（郭熙《林泉高致》）。三句说的是同一件事：
    # 远处的细节不是「没画」，是画了也读不出来。所以远山那一档的组数是零，而不是小一点 —— 这不是省笔，是那条
    # 判据本身：**远处的形体要被减去它显示不出来的东西。**
    for ridge, depth, level, groups in ((FAR, 70.0, INK_LEVELS[4], 0),
                                        (MID, 160.0, INK_LEVELS[3], 34),
                                        (NEAR, 220.0, INK_LEVELS[2], 56)):
        smooth = ridge_curve(ridge)
        layer, solid = mountain(smooth, depth, level, seed=len(ridge))
        picture = r.blend(picture, layer, 'normal', 1.0)
        fig = cun_marks(smooth, solid, level, groups, seed=len(ridge) * 7)
        picture = r.blend(picture, r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True,
                                                  paper=rough), 'normal', 1.0)
        marks += len(fig.marks)
        # **树按远近分大小与数量**：远山的树少而小（几粒），近山的多而大 —— 而这两组数不是风格，是尺度：
        # 同一种树在两座山上要长得一样大，只有它的墨要跟着山淡。
        trees = trees_on_ridge(smooth, solid, level, 10 if depth < 100 else (26 if depth < 200 else 70),
                               seed=int(len(ridge) * 13))
        picture = r.blend(picture, r.render_marks([m.to_dict() for m in trees.marks], W, H, sweep=True,
                                                  paper=rough), 'normal', 1.0)
        marks += len(trees.marks)
    water = water_marks()
    picture = r.blend(picture, r.render_marks([m.to_dict() for m in water.marks], W, H, sweep=True,
                                              paper=rough), 'normal', 1.0)
    marks += len(water.marks)
    path = os.path.join(OUT, 'landscape.png')
    r.save_png(picture, path, background=PAPER)
    print('%s  %d marks' % (path, marks))
    return 0


if __name__ == '__main__':
    sys.exit(main())
