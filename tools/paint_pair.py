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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lineweight import raster as r            # noqa: E402
import paint_apple as pa                      # noqa: E402

W, H = pa.W, pa.H
OUT = os.environ.get('PAIR_OUT') or os.path.join(os.getcwd(), 'pair')

# The larger one sits behind and to the right; the smaller one in front and to the left, so its silhouette cuts into
# the other's. That overlap is the thing a single-object picture cannot have.
BACK = (648.0, 512.0, 262.0)
FRONT = (428.0, 690.0, 186.0)


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


def apple_body(picture, cx, cy, radius, seed, dim=1.0):
    """一只果子的全部笔触：果身、湿拖、凹陷、梗、高光 —— 顺序就是遮挡的顺序。"""
    body = pa.body_marks(cx, cy, radius, seed, dim)
    layer = r.render_marks([m.to_dict() for m in body.marks], W, H, sweep=True)
    wet_drags(layer, cx, cy, radius, seed + 7)
    picture = r.blend(picture, layer, 'normal', 1.0)
    for extra in (pa.dip_marks(cx, cy, radius, seed + 1),
                  pa.stem_marks(cx, cy, radius, seed + 2),
                  pa.gloss_marks(cx, cy, radius, seed + 3)):
        picture = r.blend(picture,
                          r.render_marks([m.to_dict() for m in extra.marks], W, H, sweep=True), 'normal', 1.0)
    return picture


def main():
    os.makedirs(OUT, exist_ok=True)
    picture = pa.ground(*BACK)
    # **两道阴影都要在两只果子之前。** 第一版按「一只果子一整套」来排：后一只的地面阴影、后一只的果身、
    # 前一只的地面阴影、前一只的果身 —— 于是前一只的阴影压在后一只的果身上，后面那只被绕了一圈黑环，
    # 前面那只像在发光。阴影落在桌面上，两只果子都在桌面上方，所以阴影必须全部排在果身之前。
    picture = r.blend(picture, pa.table_shadow(*BACK), 'normal', 1.0)
    picture = r.blend(picture, pa.table_shadow(*FRONT), 'normal', 1.0)
    picture = apple_body(picture, *BACK, 20261106, 0.84)
    picture = apple_body(picture, *FRONT, 771103)
    path = os.path.join(OUT, 'pair.png')
    r.save_png(r.light(picture, direction=(-0.50, -0.58, 1.15), strength=0.34, tilt=1.15), path,
               background=(22, 16, 13))
    print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
