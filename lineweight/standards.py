"""这个库认为「一画画对了」的那些判据，集中在一处。

**它们此前散在四个地方。** `core.is_uniform` 说一支笔的宽度有没有变化；`invariants.check` 说一层的不变量过
不过；`learn/errors.jsonl` 说十种被看见过的错；而「三停五眼」那组比值住在 `tools/paint_figure.py` 里 ——
**一条判据住在画它的那个脚本里，等于没有判据**：换一个题材就要重抄一遍，而重抄的那一份会与原件漂移。

四种问题，一个入口：

```python
from lineweight import standards

standards.line(record)                   # 一支笔：强弱够不够
standards.stage(stage, current)          # 一层：不变量
standards.face(half_width, half_height)  # 一张脸：眼在哪里、多大
standards.known()                        # 十种被看见过的错
```

**它们回答同一个问题**，所以三种粒度用同一个返回形状（`invariants.Finding`）。那里 `ok` 的三态 —— 过、不过、
测不了 —— 对三种粒度都成立，而「测不了」与「过了」不是一回事，这一点 `Finding` 当初就写对了，这个模块沿用
它而不是另立一套。

**这里只做转调，不重新实现。** 两份实现会漂移，而这个库已经为它付过账：`aesthetic.verify()` 的第一版对着
一份被证明干净的写出了十一条假警报，每一条都是猜的规则。
"""
from __future__ import annotations

from . import core
from .invariants import Finding, measure_layer, MEASURES
from .invariants import check as check_stage

UNIFORM_FLOOR = core.UNIFORM_FLOOR


def line(record: dict, stage: str = 'line', floor: float = UNIFORM_FLOOR) -> Finding:
    """一支笔的 強弱：**它自己最薄的五分之一比上它自己的均值。**

    `ok` 是「有强弱」，也就是比值**低于**门槛 —— 一条等宽的线在这个比值上是 1.00，而那是这个库存在的理由：
    平直的线稿是「忘了 強弱」的样子。

    **比值按笔量，不按画量。** 一笔的收尾只占它几个百分点，所以一张画的总比值被笔与笔之间的差主导，笔尖改了
    它也几乎不动。《RESEARCH-LINE-QUALITY》记的就是这件事。
    """
    # **先问这个记录能不能量，再问它量出来多少。** `stroke_widths` 要 `brush`，所以一个空字典会在到达「没有
    # 宽度」那句之前就抛 `KeyError` —— 而那样一来，`ok=None`（测不了）这一种答案就永远拿不到。
    if not record or 'brush' not in record or not record.get('centre'):
        return Finding(stage=stage, name='stroke variation', ok=None, measured=None,
                       expected='a stroke record to measure')
    widths = core.stroke_widths(record)
    if not widths:
        return Finding(stage=stage, name='stroke variation', ok=None, measured=None,
                       expected='a width profile to measure')
    variation = core.stroke_variation(record)
    mean = sum(widths) / len(widths)
    thinnest = min(widths) / mean if mean > 0 else 1.0
    return Finding(stage=stage, name='stroke variation', ok=variation < floor, measured=variation,
                   expected='< %.2f, and a flat line sits at 1.00' % floor,
                   detail='%d samples, %.2f..%.2f, thinnest fifth %.3f of mean'
                          % (len(widths), min(widths), max(widths), thinnest))


def stage(one_stage: dict, current: dict, previous: dict | None = None,
          advisory: bool = True) -> list:
    """一层的不变量。**转调 `invariants.check`**，所以只有一个实现。"""
    return check_stage(one_stage, current, previous, advisory)


def layers(drawing, scale: float = 1.0, background: tuple[int, int, int] = (244, 241, 233)) -> list:
    """每一层渲染出来的量（覆盖、亮度、饱和度、暖度、明暗带），可以直接交给 `stage`。

    **量出来而不是猜出来**：`measure_layer` 走的是同一个渲染器，所以判据与画面看的是同一批像素。
    """
    from . import raster

    measured = {}
    for role in drawing.stage_names():
        marks = [mark.to_dict() for mark in drawing.in_stage(role)]
        if not marks:
            continue
        picture = raster.render_marks(marks, drawing.width, drawing.height, scale)
        measured[role] = measure_layer(picture, background)
    return measured


def face(half_width: float, half_height: float, top: float = -1.00, chin: float = 0.76,
         visible: float = 0.80, aspect: float = 0.34, hairline: float = -0.648,
         mouth_third: float = 1.0 / 3.0) -> dict:
    """「三停五眼」落成坐标：**五官各在哪一行、多大、两眼相距多少。**

    **三个数是解剖，五个数是这一版调的，要分清。** 五等分、三段等长、以及「嘴在下三停里」是《Hampton》与
    画脸教程里写下的规则（`learn/sources.md`）；`visible=0.80` 是颧骨那一点的 x、`aspect=0.34` 是眼裂的高宽
    比、`-0.12` 是眼中心相对脸中心的高度 —— 这三个是这个库试出来的。

    **坐标都以脸中心为原点、以半高为单位给出**（乘过 `half_height`），因为调用者拿到的是屏幕 y，而多一处换算
    就多一处符号错误。`top` 与 `chin` 是脸的上下界，`hairline` 是发际。

    **三停为什么需要发际这个参数。** `top=-1.00` 是颅顶，而三停的第一停从发际算起，少了这一条三段就不等长，
    眉、鼻底、下巴会一路偏下去 —— 上一版正是这样：鼻底写在脸的 0.33 半高处，而三停给的是 0.29。

    **那条从鼻底到下巴的线段里，嘴落在上三分之一。** 这一条是面部测量的常用值（口裂点位于鼻下点与颏下点之间
    的上三分之一），而 `learn/sources.md` 里关于嘴只有一句「the mouth sits above the guide」，比它粗得多。
    所以 `mouth_third` 是这个库选的精度，不是书上抄来的数；标在这里，是因为混在一起的那天就没有人知道哪个能改。
    """
    span = 2.0 * half_width * visible
    eye_width = span / 5.0
    # **三停：发际到眉、眉到鼻底、鼻底到下巴，三段等长。** 眉与鼻底由等分给出，嘴不再等分，它在第三段里面。
    stop = (chin - hairline) / 3.0
    brow = hairline + stop
    nose = hairline + 2.0 * stop
    mouth = nose + (chin - nose) * mouth_third
    return {
        'visible_width': span,
        'eye_width': eye_width,
        'eye_height': eye_width * aspect,
        'eye_dx': eye_width,
        'eye_dy': half_height * (top + chin) * 0.5,
        'hairline_y': half_height * hairline,
        'brow_y': half_height * brow,
        'nose_y': half_height * nose,
        'mouth_y': half_height * mouth,
        'chin_y': half_height * chin,
    }


def known() -> list:
    """十种被看见过的错，每一种带位置、现象、原因与「能不能查」。转调 `aesthetic.errors()`。"""
    from . import aesthetic

    return aesthetic.errors()


def values() -> dict:
    """这张表里的门槛本身，好让调用者不必去 `core` 里找。

    **一个门槛是一句判断，不是一个可调参数。** 它写在这里是为了被读与被质疑，不是为了被随手改 —— `0.95` 是从
    「一条等宽的线是 1.00」反推出来的，任何更小的值都会让平直的线通过。
    """
    return {'uniform_floor': UNIFORM_FLOOR, 'measures': sorted(MEASURES)}
