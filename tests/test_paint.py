"""Two capabilities paint needs and line work never did.

Both were added while painting an apple, and both were added because the picture was wrong without them: a stroke whose
cross-section is a trapezium reads as a ribbon rather than as pigment, and a stroke that can only be one colour cannot
describe a loaded brush. Neither one changes any drawing made before it, because `soft` defaults to zero and an empty
`colour_profile` is the single-colour path -- which is the property these two tests also guard.
"""

import numpy as np

from lineweight import core
from lineweight import raster as r

W, H = 120, 40


def painted(**kwargs):
    record = core.stroke_record([(20, 20), (60, 20), (100, 20)], 'brush', seed=1,
                                width_profile=[24.0, 24.0, 24.0], absolute_width=True, edge=8.0, **kwargs)
    return r.sweep_layer(record, W, H)


def rendered(**kwargs):
    return np.frombuffer(bytes(painted(**kwargs).data), dtype=np.uint8).reshape(H, W, 4)


def test_a_flat_mark_is_untouched_by_the_relief_plumbing():
    """厚度为零是默认，而默认必须与加这一支之前的像素完全一致 -- 否则线稿会悄悄变样。"""
    flat = painted()
    assert flat.relief is None
    same = r.light(flat)
    assert bytes(same.data) == bytes(flat.data)


def test_a_mark_with_thickness_lights_its_own_edge():
    """一堆有高低的颜料，光斜着来，笔触的边缘因此自己显出轮廓 -- 这是厚涂能被看见的全部机制。"""
    plain = painted()
    raised = painted(height=0.6)
    assert raised.relief is not None
    # 厚度不改变覆盖：颜色与 alpha 一个像素都不动
    assert bytes(raised.data) == bytes(plain.data)
    lit = r.light(raised, direction=(0.0, -1.0, 0.6), strength=1.2)
    before = np.frombuffer(bytes(raised.data), dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(int)
    after = np.frombuffer(bytes(lit.data), dtype=np.uint8).reshape(H, W, 4)[:, :, :3].astype(int)
    # 笔触的上下两条边，一条被照亮、一条被压暗
    assert after[30, 60].sum() != before[30, 60].sum()


def test_a_soft_section_falls_faster_towards_the_rim():
    """The linear ramp gives a trapezium; `soft` bends its shoulders down without moving the core.

    Across the stroke, not along it: the path runs left to right at row twenty, so the section is a column.
    """
    hard = rendered()[:, 60, 3].astype(float) / 255.0
    soft = rendered(soft=1.5)[:, 60, 3].astype(float) / 255.0
    assert hard[20] > 0.9 and soft[20] > 0.9, (hard[20], soft[20])
    shoulder = 32  # exactly the half width of twenty-four, so the linear ramp is at one half there
    assert soft[shoulder] < hard[shoulder] - 0.15, (hard[shoulder], soft[shoulder])


def test_one_mark_can_change_colour_along_itself():
    """A loaded brush carries one mix at the tip and another at the heel."""
    data = rendered(colour='#ff0000', colour_profile=[[255, 0, 0], [0, 0, 255]])
    left = data[20, 26, :3].astype(int)
    right = data[20, 94, :3].astype(int)
    assert left[0] > 180 and left[2] < 80, left
    assert right[2] > 180 and right[0] < 80, right


def test_a_mark_without_a_profile_is_still_one_colour():
    """The old path: one colour end to end, which is every stroke drawn before `colour_profile` existed."""
    data = rendered(colour='#2040c0')
    left = data[20, 26, :3].astype(int)
    right = data[20, 94, :3].astype(int)
    assert abs(int(left[0]) - int(right[0])) < 12
    assert abs(int(left[2]) - int(right[2])) < 12
