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
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineweight import core, project, psd   # noqa: E402
from lineweight import raster as r          # noqa: E402

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
# **而三组的「体势」要真的不同，这是并排之后才看出来的。** 原文对形状有明确的话：高远「其勢突兀」、深远「意重疊」、
# 平远「意沖融而縹縹緲緲」。而"体势"在一条脊线上就是它的**转折方式** —— 突兀是直上直下、重疊是一层压一层、沖融是
# 缓缓起伏没有一处抢眼。上一版的平远峰距只有一百五到一百八，与高远一样密，只是矮一点 —— 于是三张并排是同一套波。
#
# 所以平远这一组换成**长而缓**：峰距三百到四百，落差八十上下，一屏里只有五六个点。**沖融不是"没有起伏"，是起伏
# 走得远** —— 而同一条脊上，走得远和走得急是两件事。
FAR = [(-140, 556), (210, 486), (600, 528), (980, 460), (1300, 512), (1540, 484)]
MID = [(-140, 646), (250, 566), (660, 612), (1040, 540), (1340, 596), (1540, 574)]
# **而近山要留出水面。** 上一版的近山脊一路压到画底（y 900），于是水被它整片盖住 —— 一张山水画没有水就不是山水。
# 脊抬到六百八上下、深度收到一百五，画底那一条才空出来，而空出来的部分是**纸** —— 水不画，它是没有被墨碰到的地方。
#
# **而崖没有了。** 沖融的意思正是「没有一处抢眼」，而断崖是全画面最抢眼的一处 —— 两句话不能同时成立。**同一套代码，
# 高远那一组留崖、平远这一组不留，而这不是取舍，是那个词的定义。**
NEAR = [(-140, 776), (200, 700), (560, 744), (940, 672), (1260, 730), (1540, 706)]

# **高远的那一套。** 郭熙：「自山下而仰山顛，謂之高遠……高遠之色清明……高遠之勢突兀。」所以这三层是**尖峰加深谷**，
# 一层比一层陡、一层比一层高，而底部只留一条窄窄的水 —— 观者站在山脚，抬头。
#
# **而峰要有主次。** 同一篇：「大山堂堂為眾山之主，所以分布以次岡阜林壑……其象若大君赫然當陽而百辟奔走朝會，
# 無偃蹇背卻之勢也。」一座主峰、几座次峰，次峰低于它、朝向它、且**不背向**它。第一版是五个等高等距的等腰三角
# 形 —— 那不是山，那是一排；而「主次」这件事实在是最好落实的：把高度按到主峰的距离递减，再把峰距打乱。
#
# 主峰在近山的 x=700。三层各有各的峰，且**不落在同一列** —— 三层的峰要对齐，观者就知道它们是三层，而不是一片。
GAO_FAR = [(-140, 700), (90, 640), (220, 300), (300, 470), (430, 250), (520, 440),
           (620, 400), (760, 210), (880, 430), (1010, 300), (1120, 500), (1250, 260),
           (1360, 470), (1540, 700)]
GAO_MID = [(-140, 820), (60, 780), (170, 420), (250, 600), (390, 320), (490, 520),
           (620, 340), (740, 560), (860, 400), (980, 620), (1100, 360), (1220, 580),
           (1350, 700), (1540, 820)]
GAO_NEAR = [(-140, 880), (70, 830), (160, 620), (230, 760), (330, 500), (410, 700),
            (500, 560), (570, 500), (660, 200), (740, 240), (810, 470), (880, 520),
            (960, 590), (1050, 720), (1160, 520), (1240, 700), (1360, 790), (1540, 880)]


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


def ridge_layer(ridge, depth, level, seed, ceiling=0.88, waterfall=None):
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
    facing = 0.55 + 0.45 * (0.5 + 0.5 * np.tanh(-slope * 1.6))
    alpha = np.where(solid, fall, 0.0) * ceiling * mottle[None, :] * facing[None, :]
    # **瀑布是一条没有被墨碰到的竖缝。** 没骨的做法里水不画 —— 画的是它两侧的石头。所以这里不是「加一条白的
    # 水」，是从山体里**减去**一条：alpha 在那一列上降到零，纸自己露出来。**加法做出来的水是一条贴在石头上的白
    # 带，减法做出来的水是石头让开的地方。**
    if waterfall:
        centre, half = waterfall[0], waterfall[1]
        gaps = waterfall[2] if len(waterfall) > 2 else ()
        # **只算它影响得到的那几列。** 上一版把 `cut` 算成整幅 H×W 的浮点数组，而 `mountain` 每层跑四遍、每层都
        # 算一次 —— 瀑布只影响窄窄一条，却让整张画的计算量翻了二十倍（十七秒变成五十秒）。而画面一个像素都不变：
        # `cut` 在 `reach` 之外本来是零，乘上去等于不乘。**一个局部的东西要只算它局部的代价。**
        reach = int(half * 1.7) + 3
        low = max(0, int(centre) - reach)
        high = min(W, int(centre) + reach + 1)
        if high > low:
            columns = np.arange(low, high, dtype=np.float64)
            # **上窄下宽**：水往下散，所以缝在底部更宽。用一个沿 y 的系数做不到（alpha 是二维的），所以缝的宽度
            # 按这一列到中心的距离算，而**下半部取更松的幂** —— 那是「散开」在一条竖直缝上的写法。
            rows_below = np.clip((rows - 380.0) / 420.0, 0.0, 1.0)
            width = half * (0.45 + 0.85 * rows_below)
            cut = np.clip(1.0 - np.abs(columns[None, :] - centre) / width, 0.0, 1.0) ** 0.7
            # **「溪谷斷續以分淺深」—— 断的地方是浅滩，续的地方是深潭。** 一条从头连到尾的缝是**一道沟**，而一条
            # 断断续续的缝才是水 —— 因为它说明底下的石头有高有低，而水在低处积着、在高处流过去。所以 `gaps` 里
            # 那几段 y 区间不挖：缝在那里断开，纸上的墨连着，读成水下面的石头。
            for low_y, high_y in gaps:
                cut[max(0, int(low_y)):max(0, int(high_y)), :] = 0.0
            alpha[:, low:high] *= (1.0 - cut)
    rgba[:, :, 0] = int(round(tone[0]))
    rgba[:, :, 1] = int(round(tone[1]))
    rgba[:, :, 2] = int(round(tone[2]))
    rgba[:, :, 3] = (alpha * 255.0).astype(np.uint8)
    layer = r.Layer(W, H)
    layer.data[:] = rgba.tobytes()
    return layer, solid


def mountain(ridge, depth, level, seed, passes=4, waterfall=None):
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
                                   level * (1.0 - 0.10 * step), seed + step, waterfall=waterfall)
        picture = r.blend(picture, layer, 'normal', 1.0)
    return picture, solid


def cun_marks(ridge, solid, level, groups, seed, reach=(38.0, 110.0)):
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
        span_reach = rng.uniform(*reach)
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
            length = span_reach * rng.uniform(0.55, 1.05)
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


def pavilion(x, y, level=0.70, seed=5000, scale=1.0):
    """亭子：**五笔，而它把一片山变成可以住的地方。**

    郭熙「山之樓觀以標勝概」—— 楼观标出名胜。而「四可」里最高的两档是可游与可居，两者都要一样具体的东西：一个
    能站进去的方框。

    **它也是整张画里唯一一处直线。** 山、树、水全是曲线或软边，而人造物是直的 —— 于是这几笔同时说明两件事：这里
    有人，而人的东西和自然的东西不一样。**一条直线的价值在于它旁边的东西全是曲线**，所以它只需要五笔，也不能
    多于五笔。
    """
    fig = project.Project(width=W, height=H, title='pavilion')
    ink = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in wash(min(0.90, level)))
    # **尺寸是参数，因为「远」有两个意思。** 高远里那座在次峰的坡上，你走得到它；深远里那座藏在层间，你只能看
    # 见它 —— 而让同一座亭子在不同的场景里缩小，比写两座亭子更诚实：**远不是另一种东西，是同一件东西更小。**
    s = float(scale)
    # 屋顶：一条略拱的横笔，**比台基宽** —— 亭子的檐是它最宽的地方，第一版把台基画宽了，读成一个倒梯形。
    fig.add_stroke(core.stroke_record(
        [(x - 16.0 * s, y - 15.0 * s), (x, y - 20.0 * s), (x + 16.0 * s, y - 15.0 * s)],
        'brush', seed=seed, colour=ink, soft=0.6, edge=1.6,
        width_profile=[5.5 * s, 6.5 * s, 5.5 * s], alpha_profile=[0.72, 0.84, 0.72],
        absolute_width=True), stage='line', layer='paint', note='')
    # 两柱：直、等宽、等长。**等长是「人造」在画面上最省的一句** —— 自然里的两根柱子不会一样长。
    for side in (-1.0, 1.0):
        fig.add_stroke(core.stroke_record(
            [(x + side * 9.0 * s, y - 14.0 * s), (x + side * 9.0 * s, y - 1.0 * s)],
            'brush', seed=seed + 1, colour=ink, soft=0.4, edge=1.0,
            width_profile=[2.6 * s, 2.6 * s], alpha_profile=[0.76, 0.76], absolute_width=True),
            stage='line', layer='paint', note='')
    # 台基：一条横，比顶略窄 —— 它把亭子按在坡上，而没有它亭子会浮着。
    fig.add_stroke(core.stroke_record(
        [(x - 9.0 * s, y), (x + 9.0 * s, y)], 'brush', seed=seed + 2,
        colour=ink, soft=0.4, edge=1.2,
        width_profile=[3.2 * s, 3.2 * s], alpha_profile=[0.62, 0.62], absolute_width=True),
        stage='line', layer='paint', note='')
    return fig


def path_marks(level=0.62, segments=26, seed=6000):
    """山路：**断续的短笔，而「断」是山遮住它的地方。**

    郭熙「山之人物以標道路」—— 人物标出道路。反过来读也一样：路要先有，人物才有地方站。而一条画成连续线的路是
    一条**看得见全貌**的路，那只有鸟瞰才有；从山脚往上看的路上，它一段在坡上、一段被石头挡住、一段拐到看不见的
    那一侧。所以路是断续的，**而断续的比例就是这座山有多起伏。**

    位置不跟着山脊走。脊是山的最高处，而路沿坡走 —— 一条贴着脊的路是「看山的人」，不是「住在山里的人」。
    """
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='path')
    colour = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in wash(min(0.94, level + 0.18)))
    for i in range(segments):
        t = (i + rng.uniform(0.0, 0.6)) / segments
        x = 1240.0 - t * 820.0
        y = 834.0 - t * 300.0 + math.sin(t * 9.0) * 14.0
        length = rng.uniform(12.0, 30.0)
        # **笔要顺着坡，不是横着。** 第一版的每一段都是短横线，落在坡上读成一道擦痕；而这条路的方向是
        # (−820, −300) 归一化之后的样子 —— 每一段都该是那个方向的一小截。
        fig.add_stroke(core.stroke_record(
            [(x, y), (x - length * 0.94, y - length * 0.34 + rng.uniform(-3.0, 3.0))], 'brush',
            seed=seed + i, colour=colour, soft=0.5, edge=1.4,
            width_profile=[3.4, 2.2], alpha_profile=[rng.uniform(0.44, 0.64), 0.32],
            absolute_width=True), stage='line', layer='paint', note='')
    return fig


def figure_dot(x, y, seed=6100):
    """一个人：两点。**远人无目 —— 而这里连脸都没有，只有一竖一点。**

    它比一棵树还小，而它的用处不是「有个人」，是**让那条路成立**：一条没有人的路是一道裂缝，一条有一个人的路是
    一条可以走的路。郭熙把这句话写成了「山之人物以標道路」，而模特本身不需要任何细节 —— **点在画上，路就有了
    尺度与方向。**
    """
    fig = project.Project(width=W, height=H, title='figure')
    ink = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in wash(0.92))
    fig.add_stroke(core.stroke_record(
        [(x, y - 10.0), (x, y)], 'brush', seed=seed, colour=ink, soft=0.4, edge=0.8,
        width_profile=[1.8, 1.5], alpha_profile=[0.84, 0.84], absolute_width=True),
        stage='line', layer='paint', note='')
    fig.add_stroke(core.stroke_record(
        [(x - 0.7, y - 13.0), (x + 0.7, y - 12.2)], 'brush', seed=seed + 1, colour=ink,
        soft=0.4, edge=0.6, width_profile=[2.6, 2.3], alpha_profile=[0.92, 0.92], absolute_width=True),
        stage='line', layer='paint', note='')
    return fig


def splash(centre, y, level=0.50, seed=6200):
    """溅起的水花：**瀑布底下的一小丛淡墨，而它比瀑布本身更说明这是水。**

    一条竖直的缝可以是一道裂缝、一条石缝、一条什么都没画的空白。**水花把它认领成水** —— 因为只有水从高处落下来
    才会在底下散成一片。所以这几笔不是装饰，是那个减法最后需要的**一句声明**：缝是水，因为它落到了地上。

    位置在缝的底端，宽度比缝宽三倍，而每一笔都朝外斜 —— 落下的东西散开时是向外走的。
    """
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='splash')
    ink = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in wash(level))
    for i in range(14):
        side = rng.choice((-1.0, 1.0))
        span = rng.uniform(14.0, 52.0)
        rise = rng.uniform(4.0, 20.0)
        fig.add_stroke(core.stroke_record(
            [(centre, y - rng.uniform(0.0, 10.0)),
             (centre + side * span * 0.55, y - rise * 0.8),
             (centre + side * span, y - rise * 0.2)], 'brush', seed=seed + i,
            colour=ink, soft=0.7, edge=2.4, bristle=0.34, bristle_pitch=2.6,
            width_profile=[rng.uniform(2.6, 4.6), rng.uniform(1.8, 3.4), 1.0],
            alpha_profile=[rng.uniform(0.30, 0.50), 0.24, 0.10], absolute_width=True),
            stage='line', layer='paint', note='')
    return fig


def reflection(picture, waterline, strength=0.20, squash=0.45, blur=3.0):
    """水面的倒影：**岸上的东西翻过来，而它一定比岸上淡、比岸上软、比岸上矮。**

    郭熙「山無水則不媚」—— 而水的「媚」有一半来自倒影，因为它把山的墨**还给了水**。三个必然的偏差各有一条理由：
    **淡**（水面只反射一部分，其余透下去或被碎浪打散）、**软**（水在动，倒影的边从来没有清的）、**矮**（透视把
    竖直的影像压扁）。**倒影画成岸上那张的等大复制，读成「地上放了一块镜子」，而不是水。**

    而它还有一个副作用，比倒影本身值钱：**山脚与水面之间那条硬边被泡软了。** 平远那张画到这里，山是浮在水面上
    的一块墨 —— 有了倒影，山才有重量，因为它开始把东西压进水里。
    """
    source = np.frombuffer(bytes(picture.data), dtype=np.uint8).reshape(H, W, 4).astype(np.float64)
    line = int(max(1, min(H - 2, waterline)))
    out = np.zeros((H, W, 4), dtype=np.float64)
    for y in range(H - line):
        row = line - 1 - int(y * squash)
        if 0 <= row < H:
            out[line + y, :, 0:3] = source[row, :, 0:3]
            out[line + y, :, 3] = 255.0
    # **软，而且是沿竖直方向软。** 水在动，动的是上下 —— 一条横向的模糊把倒影抹平，一条纵向的模糊才让它像水。
    out[:, :, 3] = ndimage.gaussian_filter1d(out[:, :, 3], blur, axis=0)
    out[:, :, 0] = ndimage.gaussian_filter1d(out[:, :, 0], blur, axis=0)
    out[:, :, 1] = ndimage.gaussian_filter1d(out[:, :, 1], blur, axis=0)
    out[:, :, 2] = ndimage.gaussian_filter1d(out[:, :, 2], blur, axis=0)
    out[:, :, 3] *= strength
    layer = r.Layer(W, H)
    layer.data[:] = out.astype(np.uint8).tobytes()
    return layer


def cloud_band(y, level=0.22, seed=6300, count=3):
    """云：**一层极淡的墨横着走过山腰，而它的边是虚的。**

    郭熙七个「無…則…」里第一条就是「山無雲則不秀」。而在这条水道上有两件事让云和山不是同一种东西：

    **它横着走，山竖着站。** 所以云是画面里唯一一个纯粹的水平元素 —— 山有脊、树有干、水在底下横着，而云高高地
    横在山腰，它说明的是这座山有多**高**（云在它的腰上），不是它有多远。

    **它的墨比最远的山还淡，而它盖在山的前面。** 这一对是矛盾的，而正因为它矛盾，云才读成云：比远山淡说明它是
    空气，盖在近山前面说明它在动。**一个在远处而压在前面的东西，只有云。**

    **它有浓度，没有轮廓。** `soft=1.0` 加一百以上的 `edge` 让边完全化开 —— 而这不是"柔和的风格"，是云没有边这个
    事实；一条画得出边的云是一条画得出边的雾。

    **而 `edge` 一过笔宽的一半，浓度就被摊平了。** `ramp` 在笔心被 `clip` 到一，取 `soft=1.0` 之后平方仍是一；
    再往外一点就掉得很快 —— 宽 150–250、`edge` 96–148 的时候，中心的有效 alpha 只有 `alpha_profile` 的七成左右。
    所以 alpha 放在零点三到零点四四，落到纸上是一层薄雾而不是一块灰。
    """
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='cloud')
    ink = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in wash(level))
    for i in range(count):
        x = rng.uniform(-120.0, W + 120.0)
        yy = y + rng.uniform(-46.0, 46.0)
        length = rng.uniform(520.0, 1180.0)
        fig.add_stroke(core.stroke_record(
            [(x - length * 0.5, yy), (x, yy + rng.uniform(-16.0, 16.0)), (x + length * 0.5, yy)],
            'brush', seed=seed + i, colour=ink, soft=1.0, edge=rng.uniform(96.0, 148.0),
            bristle=0.0, width_profile=[rng.uniform(150.0, 250.0)] * 3,
            alpha_profile=[rng.uniform(0.30, 0.44)] * 3,
            absolute_width=True), stage='line', layer='paint', note='')
    return fig


def birds(count=5, y=210.0, seed=6400, level=0.66):
    """飞鸟：**一笔一个，而它们是画面里唯一在动的东西。**

    山水画的天空很少是空的，而填它的东西极省 —— 一只鸟是一笔：从左翼到右翼，中间向下折一个尖，而那个尖是身体。
    把两只翅膀分开画会更像鸟，也更花；**一笔的折角已经够了，因为认鸟靠的是那个角，不是任何一根羽毛。**

    而鸟的用处和人物一样：**它们说明天空有多大。** 一只鸟在这张画上是四到十像素，而天空占整张画的上三分之一 ——
    有了鸟，那片纸就从「没画完」变成「很高」。**留白需要一个参照物，否则它只是空白。**

    它们不落在山里，落在天里，所以在最前面 —— 鸟在云之上，而云在山之上。
    """
    rng = random.Random(seed)
    fig = project.Project(width=W, height=H, title='birds')
    ink = '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in wash(level))
    # **一群鸟是一个整体，不是一个一个散开的点。** 第一版把六只撒在整条天空上，画出来是六处孤立的折角，读成纸上
    # 的瑕疵。真实的鸟群共享一个中心：它们在飞同一个方向，所以彼此靠得很近，而整群只占天空的一小块。
    centre_x = rng.uniform(260.0, W - 260.0)
    centre_y = y + rng.uniform(-34.0, 34.0)
    for i in range(count):
        x = centre_x + rng.uniform(-126.0, 126.0)
        yy = centre_y + rng.uniform(-62.0, 62.0)
        size = rng.uniform(4.5, 10.0)
        fold = rng.uniform(0.45, 0.95)
        fig.add_stroke(core.stroke_record(
            [(x - size, yy - size * 0.35), (x, yy + size * fold), (x + size, yy - size * 0.35)],
            'brush', seed=seed + i, colour=ink, soft=0.5, edge=1.2,
            width_profile=[1.0, 1.8, 1.0], alpha_profile=[0.42, 0.62, 0.42],
            absolute_width=True), stage='line', layer='paint', note='')
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


# **峰必须落在不同的列上。** 第一版六条脊的起伏几乎一样、只是往下挪 —— 画出来是六条平行的波，而"重叠"和"平行"
# 在纸上是相反的东西。真实的层叠里，这一层的峰正对着上一层的谷，于是视线被它挡住又放开。
#
# **而六层太密，改成五层，每层要够宽。** 「重晦」不是把颜色调深就有的 —— 它需要一个**面积**。六层等间距时每层只
# 剩八十像素高，远层的墨刚铺开就被下一层遮掉，于是六层的暗加起来也不如一层厚。五层、间距一百二到一百四、深度比
# 间距多二十（重叠一点点），每层才有一块自己的面可以重。
SHEN_FAR = [(-140, 330), (110, 290), (240, 240), (390, 320), (540, 270), (660, 220),
            (820, 310), (950, 260), (1090, 230), (1240, 310), (1540, 330)]
SHEN_A = [(-140, 460), (150, 430), (290, 380), (400, 330), (540, 400), (700, 360),
          (830, 320), (960, 400), (1120, 360), (1240, 330), (1540, 450)]
SHEN_B = [(-140, 600), (90, 570), (180, 520), (330, 580), (460, 530), (590, 480),
          (740, 550), (880, 500), (1020, 470), (1160, 540), (1300, 500), (1540, 580)]
SHEN_C = [(-140, 720), (170, 690), (320, 640), (450, 700), (600, 650), (760, 600),
          (900, 670), (1050, 620), (1180, 590), (1320, 660), (1540, 700)]
SHEN_NEAR = [(-140, 840), (90, 820), (220, 770), (380, 830), (540, 780), (700, 740),
             (860, 800), (1000, 750), (1150, 720), (1300, 790), (1540, 830)]


SCENES = {
    # 平远：脊缓、深度浅、浓度低、平滑足 —— 观者站在近山上望远山，所以一切都摊开在水平方向上。
    'ping': (((FAR, 70.0, INK_LEVELS[4], 0, None),
              (MID, 140.0, INK_LEVELS[3], 34, None),
              (NEAR, 150.0, INK_LEVELS[2], 56, None)), 7, (38.0, 110.0)),
    # 高远：脊陡、深度深、浓度高、平滑少 —— 尖峰留着，因为「其勢突兀」就是这四步里被平滑得最少的那一步。
    #
    # **而三层不能叠得太密。** 上一版三层的深度是 200/260/320，而三条脊都在 y 200 到 800 之间 —— 于是远山透不出
    # 来，三层糊成一片尖峰，读成「一座有五个头的东西」。远山的深度收到 120：它只在脊下露一点点，露出多少就是它
    # 有多远。**深度的绝对值不重要，三层之间的差才重要。**
    #
    # **皴也要跟着坡变短。** 一段四十到一百一十像素的细笔落在陡坡上，读成一道划痕；斧劈那一类皴是短而宽的块，
    # 因为陡坡上的一笔本来就短。所以高远这一场的皴收到二十二到五十八。
    #
    # **而「山無水則不媚」—— 高远这一场有一道瀑布，落在一道谷里（x=640，主峰左侧的山坳）。** 它只挖在近山那一层：
    # 远层的瀑布会被近层遮住，挖了也看不见，而挖一条看不见的缝等于没画。
    'gao': (((GAO_FAR, 120.0, INK_LEVELS[4], 0, None),
             (GAO_MID, 210.0, INK_LEVELS[2], 34, None),
             (GAO_NEAR, 300.0, INK_LEVELS[1], 60, (640.0, 26.0))), 3, (22.0, 58.0)),
    # 深远：五层，一层比一层近、一层比一层淡 —— **浓度是往回走的**，远处最重。而每层的深度只比间距多二十：重叠
    # 只发生在边界上，于是层与层之间留着纸，那就是山腰的云。**「大块留白」不是画上去的，是五层之间必然剩下的
    # 那条缝。**
    'shen': (((SHEN_FAR, 150.0, 0.62, 34, None),
              (SHEN_A, 160.0, 0.50, 30, None),
              (SHEN_B, 140.0, 0.40, 26, None),
              # **山涧挖在中间那一层。** 挖在最近的一层，它会被看成前景的一道裂缝；挖在最远的一层，它被四层墨盖住
              # 看不见。而第三层正好是「窥」那一眼停下的地方 —— 缝在那里断开三次，每一次断开都是一处浅滩。
              (SHEN_C, 140.0, 0.31, 22, (700.0, 15.0, ((452, 492), (536, 578), (624, 668)))),
              (SHEN_NEAR, 150.0, 0.24, 18, None)), 5, (14.0, 34.0)),
}


def main():
    mode = os.environ.get('LAND_MODE', 'ping')
    planes, rounds, reach = SCENES[mode]
    os.makedirs(OUT, exist_ok=True)
    picture = r.Layer(W, H)
    r.fill_polygon(picture, [(-20.0, -20.0), (W + 20.0, -20.0), (W + 20.0, H + 20.0), (-20.0, H + 20.0)],
                   PAPER, 1.0)
    marks = 0
    rough = r.PAPERS['rough']
    # **每一块在 PSD 里是一层，而层的名字是它在画里的身份。** 这张画不是「一堆笔」，是「山、皴、树、水、云、鸟、
    # 亭、路、人」—— 而分出这些名字之后，才能把「树」整层关掉看还剩下什么。那一步是判断，不是编辑，而它要求
    # 笔分属不同的纸。**一张所有笔都叫 `paint` 的画仍然逐笔可改，而它不能被"看"。**
    stack = []

    def place(name, layer):
        nonlocal picture
        picture = r.blend(picture, layer, 'normal', 1.0)
        canvas = psd.Layer(name, W, H)
        canvas.data = bytearray(layer.data)
        for i in range(0, len(canvas.data), 4):
            if canvas.data[i + 3] == 0:
                canvas.data[i] = canvas.data[i + 1] = canvas.data[i + 2] = 255
        stack.append(canvas)
        return layer
    # **远山不皴。** 「遠山無皴，遠水無波，遠人無目 —— 非無也，如無耳」（郭熙《林泉高致》）。三句说的是同一件事：
    # 远处的细节不是「没画」，是画了也读不出来。所以远山那一档的组数是零，而不是小一点 —— 这不是省笔，是那条
    # 判据本身：**远处的形体要被减去它显示不出来的东西。**
    for ridge, depth, level, groups, fall in planes:
        smooth = ridge_curve(ridge, rounds=rounds)
        layer, solid = mountain(smooth, depth, level, seed=len(ridge), waterfall=fall)
        place('mountain-%d' % len(ridge), layer)
        fig = cun_marks(smooth, solid, level, groups, seed=len(ridge) * 7, reach=reach)
        place('cun-%d' % len(ridge), r.render_marks([m.to_dict() for m in fig.marks], W, H, sweep=True,
                                                    paper=rough))
        marks += len(fig.marks)
        # **树按远近分大小与数量**：远山的树少而小（几粒），近山的多而大 —— 而这两组数不是风格，是尺度：
        # 同一种树在两座山上要长得一样大，只有它的墨要跟着山淡。
        trees = trees_on_ridge(smooth, solid, level, 10 if depth < 100 else (26 if depth < 230 else 70),
                               seed=int(len(ridge) * 13))
        place('trees-%d' % len(ridge), r.render_marks([m.to_dict() for m in trees.marks], W, H, sweep=True,
                                                      paper=rough))
        marks += len(trees.marks)
        # **瀑布底下要有水花**，而它比瀑布本身更说明那是水：一条竖直的缝可以是一道裂缝、一条石缝、一条什么都没画
        # 的空白，而水花把它认领成水。**加法里那几笔是减法最后需要的一句声明。**
        if fall:
            spray = splash(fall[0], 706.0, level, seed=6200 + len(ridge))
            place('splash', r.render_marks([m.to_dict() for m in spray.marks], W, H, sweep=True, paper=rough))
            marks += len(spray.marks)
    # **云在山之后画，而它盖在山腰上。** 顺序不是排版：先画山，云才有东西可以横穿；而云如果先画，山会把它整片
    # 盖掉 —— 云在山上，不在山后。
    if mode == 'gao':
        clouds = cloud_band(392.0, 0.22, seed=6300, count=3)
        place('cloud', r.render_marks([m.to_dict() for m in clouds.marks], W, H, sweep=True, paper=rough))
        marks += len(clouds.marks)
    # **深远不画云带。** 它的云是层与层之间剩下的那条缝 —— 4.89 记过「云是两层之间没有被墨碰到的一条」。在那张
    # 画上再横一条淡墨，等于把两种云叠在一起，而两种都不明显。**一个画面只需要一种方法做同一件事**，而深远已经
    # 有了一种更好的：它的云是减法出来的，那条横带是加法，谁也不服谁。
    # **深远要有一个「窥」的目标。** 那座亭子藏在第三层的脊上（x=760 处），只有正常大小的六成二，而且被上面那几
    # 层遮掉一半 —— 它不在等你走过去，它在等你看见它。郭熙「深遠者細碎」：细碎的不只是树，也是人做出的东西。
    if mode == 'shen':
        house = pavilion(760.0, 516.0, 0.34, seed=5100, scale=0.62)
        place('pavilion', r.render_marks([m.to_dict() for m in house.marks], W, H, sweep=True, paper=rough))
        marks += len(house.marks)
    if mode == 'gao':
        # 亭子落在左边那道次峰的坡上（x=520 处脊在 y 534 附近）。**位置比形状重要**：它要在一条坡上、并且能看见
        # 主峰 —— 观者站在画外往里看，而亭子里的人正看着同一座山。
        house = pavilion(520.0, 536.0, 0.66, seed=5000)
        place('pavilion', r.render_marks([m.to_dict() for m in house.marks], W, H, sweep=True, paper=rough))
        marks += len(house.marks)
        # **路先于人物。** 人物标出道路，而它标的是一个已经在的地方；反过来把人先放上去，那条路就成了「从这里到
        # 那里」的图解，而不是山里本来就有的那条。
        trail = path_marks(0.62, segments=26, seed=6000)
        place('path', r.render_marks([m.to_dict() for m in trail.marks], W, H, sweep=True, paper=rough))
        marks += len(trail.marks)
        # 人在 t=0.42 处：x = 1240 - 0.42*820 = 896，y = 834 - 0.42*300 + sin(3.78)*14 ≈ 711
        walker = figure_dot(896.0, 712.0, seed=6100)
        place('figure', r.render_marks([m.to_dict() for m in walker.marks], W, H, sweep=True, paper=rough))
        marks += len(walker.marks)
    # 深远那一场没有湖。观者是**从山前窥山后**，脚下是山口而不是水面；五层的底在 y 840，再往下就是纸。给它加一片
    # 平的水，等于把「向里看」改成「向远看」—— 那是平远。**一条水法的错用能改掉一个视点。**
    if mode != 'shen':
        # **倒影先于波纹。** 波纹是水面上的东西，倒影是水面里的东西 —— 先铺水面下的，再压水面上的。
        if mode == 'ping':
            place('reflection', reflection(picture, 786.0, strength=0.22))
        water = water_marks()
        place('water', r.render_marks([m.to_dict() for m in water.marks], W, H, sweep=True, paper=rough))
        marks += len(water.marks)
    # **鸟在最前。** 它们不落在山里、落在天里，而天比云高、云比山高 —— 所以顺序是山、云、鸟。
    if mode in ('gao', 'ping'):
        flock = birds(6 if mode == 'gao' else 4, 196.0 if mode == 'gao' else 232.0,
                      seed=6400 if mode == 'gao' else 6410, level=0.66)
        place('birds', r.render_marks([m.to_dict() for m in flock.marks], W, H, sweep=True, paper=rough))
        marks += len(flock.marks)
    path = os.path.join(OUT, 'landscape-%s.png' % mode)
    r.save_png(picture, path, background=PAPER)
    # **一张画是一个工程，而它的层是它自己说出来的那几样东西。** 导出 PSD 之后，「把树关掉」变成一次点击，而
    # 那一步是判断 —— 它回答「这张画靠什么立着」，而这个问题逐笔编辑永远回答不了。
    psd_path = os.path.join(OUT, 'landscape-%s.psd' % mode)
    psd.save_psd(stack, psd_path)
    print('%s  %d marks  %d layers  + %s' % (path, marks, len(stack), os.path.basename(psd_path)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
