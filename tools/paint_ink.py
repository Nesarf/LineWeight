"""的一条鱼，没骨：**没有轮廓，边由墨停下来的地方形成。**

**这是这个仓库的第三条边。** 画到现在，每条边只有两个来源：笔触自己的收尾（苹果，4.75 之前的鱼身），或者一次
硬裁（布，4.63）。用户贴来的那篇水墨教程里有第四个风格 —— **没骨 mogu，「无骨」**：直接上色、不先打稿，而
「线条可能因水边或重叠的颜色而无意中形成」。水媒质自己会做这件事；盖章式的渲染器必须先被告知。

所以这个文件不是 `paint_fish.py` 的另一个参数，而是它的反面：

```
paint_fish.py   先算掩膜 → 撒笔 → 裁到掩膜        边是给定的
paint_ink.py    直接落几笔墨 → 让它们的并集成边    边是长出来的
```

**形体还是那条鱼。** `BODY` / `DORSAL` / `FIN` / `TAIL` / `EYE` 从 `paint_fish` 借来，但这里只读它们的中线与
体高 —— **不用掩膜、不裁、不描**。一笔的宽度由那一处的体高乘一个比例给出，于是笔自己越过了轮廓；越过多少，
是笔的事，不是掩膜的事。

**墨的浓淡是几档，不是一条连续曲线。** 中国传统叫「墨分五色」：焦、浓、重、淡、清。这个说法不在那篇教程里
（它给的是四风格与骨法），所以它是借来的常识、不是引用；写成 `INK_LEVELS` 五个常数，好让「借」这件事在代码里
看得见。

**而写意要少笔。** 一条侧扁的鱼，身体三笔、头一笔、尾两笔、眼一点 —— 六到八笔。这个数字不是风格上的谦虚：
每一笔落下就不能改，多一笔就多一处要交代的地方。
"""
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lineweight import core, project, psd   # noqa: E402
from lineweight import raster as r          # noqa: E402
from paint_fish import BODY, DORSAL, EYE, FIN, TAIL, H, W, mask_of   # noqa: E402

OUT = os.environ.get('INK_OUT') or os.path.join(os.getcwd(), 'ink')
#: 宣纸：比白暖，比米黄浅。墨落在它上面才有「渗」的余地。
PAPER = (234, 228, 214)
INK = (28, 24, 30)
#: 焦、浓、重、淡、清。**借来的常识，不是引用** —— 源里给的是四风格与骨法。
INK_LEVELS = (0.88, 0.70, 0.50, 0.30, 0.14)


def wash(level):
    """一档墨色。"""
    return tuple(PAPER[i] + (INK[i] - PAPER[i]) * level for i in range(3))


def hexed(colour):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in colour)


def frame(mask):
    """每一列的上下界 —— 形体给这里的东西只有两样：中线和体高。"""
    top_of = np.argmax(mask, axis=0)
    bot_of = H - 1 - np.argmax(mask[::-1, :], axis=0)
    return top_of, bot_of


def body_strokes(fig, seed=2027):
    """身体：**三笔淡墨的并集。**

    背一笔、侧一笔、腹一笔。每一笔沿体轴走，宽度是那一处体高的一个比例，所以它在头尾自动收窄 —— 而它越出轮廓
    多少不由任何人决定：三笔各自的宽度合起来的边就是鱼的边。

    **背最浓、腹最淡**，因为写意画身上的墨是从上往下渗的，也是因为背脊在真实的光里最深（4.75 的三段色，用墨
    再说一遍）。
    """
    rng = random.Random(seed)
    mask = mask_of(BODY)
    top_of, bot_of = frame(mask)
    columns = [x for x in range(200, 1050, 24) if mask[:, x].any()]
    for index, (offset, level, share) in enumerate(((-0.24, INK_LEVELS[2], 0.42),
                                                    (0.02, INK_LEVELS[3], 0.46),
                                                    (0.28, INK_LEVELS[4], 0.40))):
        points = []
        widths = []
        for x in columns:
            top = float(top_of[x])
            bot = float(bot_of[x])
            span = bot - top
            points.append((float(x), (top + bot) * 0.5 + offset * span))
            widths.append(span * share)
        thick = [widths[min(len(widths) - 1, int(i * (len(widths) - 1) / 7.0))] for i in range(8)]
        # **一笔之内有浓淡，而这是写意最基本的一件事。** 笔尖上的墨是一点一点用掉的：起笔最浓，收笔最淡。上一版
        # 每一笔是一个常数色相，于是九笔读成九个均匀的色块 —— 而「墨色」在这条路上不是九个色块，是九次变成。
        body = wash(level)
        fig.add_stroke(core.stroke_record(
            points, 'brush', seed=2000 + index, colour=hexed(body),
            soft=0.9, edge=rng.uniform(10.0, 18.0),
            # **飞白是笔毛的，不是纸的。** 粗纸给的是细密的颗粒 —— 那是「纸纹」，而飞白是墨没跟上的那几条**顺着
            # 笔画**的空隙，它由笔上分开的毛决定。所以毛的幅度提上去、间距拉开：每一根毛自己决定留下多少墨，
            # 相邻两根之间那道缝就是白的。纸的咬墨留着，它是这两件事的底噪，不是其中任何一件。
            bristle=0.78, bristle_pitch=rng.uniform(7.0, 13.0),
            colour_profile=[[v * 0.90 for v in body], list(body), [min(255.0, v * 1.16) for v in body]],
            width_profile=thick,
            alpha_profile=[0.66, 0.84, 0.78, 0.72, 0.76, 0.68, 0.56, 0.30],
            bleed=r.bleed_radius(level, r.PAPERS['rough']),
            absolute_width=True), stage='line', layer='body', note='')
    return fig


def gill_stroke(fig, seed=2100):
    """鳃盖：一笔短的浓墨，**它把「头」从「身体」里分出来。**

    第一版这一笔在吻端、一百像素宽，画出来是一个球 —— 读成一块石头而不是一个头。两处都错了：**位置**上它该在
    鳃盖，那是头与身体的分界；**宽度**上它该窄，因为它交代的是一道转折，不是头骨的体积。

    **而吻端不需要额外一笔。** 身体那三笔走到那里自己结束 —— 那个结束就是吻端的边。没骨的全部内容就是这个：
    一个形状的边界，是它最后一笔停下来的地方。
    """
    mask = mask_of(BODY)
    top_of, bot_of = frame(mask)
    x0 = 936
    top = float(top_of[x0])
    bot = float(bot_of[x0])
    # **而它的墨不能比身体浓太多。** 第一版给它「浓」那一档、alpha 零点五八，画出来是一条黑线压在鱼身上 —— 鳃盖
    # 是同一块墨在转折处厚了一点，不是另一笔更黑的墨。所以降到「重」那一档，中段的 alpha 也压下来。
    fig.add_stroke(core.stroke_record(
        [(x0 + 8, top + 26.0), (x0 - 10, (top + bot) * 0.5), (x0 + 2, bot - 26.0)],
        'brush', seed=2100, colour=hexed(wash(INK_LEVELS[2])), soft=0.85, edge=9.0,
        bristle=0.20, width_profile=[14.0, 22.0, 11.0],
        alpha_profile=[0.18, 0.40, 0.14], absolute_width=True), stage='line', layer='gill', note='')
    return fig


def tail_strokes(fig, seed=2200):
    """尾：两笔。**它们不相接，中间那道缝就是尾鳍的分叉** —— 没骨的做法里，缝不是留空，是两笔之间没有墨。"""
    rng = random.Random(seed)
    for index, (dy, level) in enumerate(((-34.0, INK_LEVELS[2]), (30.0, INK_LEVELS[3]))):
        fig.add_stroke(core.stroke_record(
            [(194.0, 486.0 + dy * 0.3), (124.0, 472.0 + dy), (44.0, 462.0 + dy * 1.8)],
            'brush', seed=2200 + index, colour=hexed(wash(level)), soft=0.9, edge=rng.uniform(9.0, 14.0),
            bristle=0.40, bristle_pitch=3.6,
            width_profile=[62.0, 44.0, 10.0],
            alpha_profile=[0.64, 0.56, 0.22], absolute_width=True), stage='line', layer='tail', note='')
    return fig


def fin_stroke(fig, seed=2300):
    """背鳍与胸鳍各一笔清墨，**比身体淡两档** —— 鳍是薄的，墨在它上面渗得开。"""
    rng = random.Random(seed)
    fig.add_stroke(core.stroke_record(
        [(500.0, 322.0), (580.0, 268.0), (668.0, 300.0)], 'brush', seed=2300,
        colour=hexed(wash(INK_LEVELS[3])), soft=1.0, edge=16.0,
        width_profile=[38.0, 54.0, 30.0], alpha_profile=[0.44, 0.56, 0.30], absolute_width=True),
        stage='line', layer='fin', note='')
    fig.add_stroke(core.stroke_record(
        [(916.0, 552.0), (858.0, 606.0), (800.0, 662.0)], 'brush', seed=2301,
        colour=hexed(wash(INK_LEVELS[4])), soft=1.0, edge=12.0,
        width_profile=[30.0, 24.0, 8.0], alpha_profile=[0.50, 0.44, 0.18], absolute_width=True),
        stage='line', layer='fin', note='')
    return fig


def eye_dot(fig, seed=2400):
    """眼：一点焦墨。**整张画里最浓的一点**，而它只有九像素。"""
    cx, cy = EYE
    fig.add_stroke(core.stroke_record(
        [(cx - 4.0, cy - 1.0), (cx + 4.0, cy + 1.5)], 'brush', seed=2400,
        colour=hexed(wash(INK_LEVELS[0])), soft=0.6, edge=1.8,
        width_profile=[9.0, 7.0], alpha_profile=[0.92, 0.86], absolute_width=True),
        stage='line', layer='eye', note='')
    return fig


def main():
    os.makedirs(OUT, exist_ok=True)
    # **每一笔落在它自己的层上。** 层名不是排版 —— 它同时是导出 PSD 时那一张纸的名字，和「改这一笔」与「改这一层」
    # 之间的那个单位。五层：body / gill / fin / tail / eye。
    fig = project.Project(width=W, height=H, title='ink fish')
    body_strokes(fig)
    gill_stroke(fig)
    fin_stroke(fig)
    tail_strokes(fig)
    eye_dot(fig)
    # **纸咬墨，就是飞白。** 粗纸的凸起盖不住墨，于是笔划过的地方留下细碎的白点 —— 那是水彩与书法共用的一个
    # 效果，而它在 `lineweight` 里不需要新的机制：`Paper.bite` 早就在，只是没有人给它一张粗纸。**这一条是这一节
    # 唯一一处「不用写代码」的改动**，也是把墨从「灰色的水」变成「墨」的最后一步。
    rough = r.PAPERS['rough']
    picture = r.Layer(W, H)
    r.fill_polygon(picture, [(-20.0, -20.0), (W + 20.0, -20.0), (W + 20.0, H + 20.0), (-20.0, H + 20.0)],
                   PAPER, 1.0)
    picture = r.blend(picture, r.render_marks([m.to_dict() for m in fig.live()], W, H, sweep=True,
                                              paper=rough), 'normal', 1.0)
    path = os.path.join(OUT, 'ink.png')
    r.save_png(picture, path, background=PAPER)
    project.save_project(fig, os.path.join(OUT, 'pass-ink.json'))
    stack = psd.layers_from_project(fig)
    psd.save_psd(stack, os.path.join(OUT, 'ink.psd'))
    print('%s  %d marks  %d layers  + ink.psd' % (path, len(fig.live()), len(stack)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
