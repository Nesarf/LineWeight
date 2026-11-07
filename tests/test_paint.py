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


def test_bristle_leaves_streaks_along_the_stroke():
    """笔毛的纹路沿笔画走：横跨笔触时会出现周期性的明暗，而 `bristle=0` 的那一笔是平滑的。"""
    smooth = rendered()[:, 60, 3].astype(float) / 255.0
    hairy = rendered(bristle=0.8, bristle_pitch=3.0)[:, 60, 3].astype(float) / 255.0
    band = slice(8, 33)  # 笔触覆盖的那一条：宽二十四，中心在第二十行
    # **看相邻两像素的差，不看整条剖面的标准差。** 剖面本身从零到一，那条坡度比毛纹大一个数量级，
    # 用标准差去测毛纹只会测到坡度。毛纹的特征是「相邻两格之间跳」，所以量的是这个。
    flat_steps = float(np.abs(np.diff(smooth[band])).mean())
    hair_steps = float(np.abs(np.diff(hairy[band])).mean())
    assert hair_steps > flat_steps * 1.15, (flat_steps, hair_steps)


def test_smudge_moves_colour_and_leaves_opacity_alone():
    """拖的是颜料，不是它铺了多厚。"""
    layer = painted(colour='#ff0000', colour_profile=[[255, 0, 0], [0, 0, 255]])
    before = bytes(layer.data)
    alpha_before = np.frombuffer(before, dtype=np.uint8).reshape(H, W, 4)[:, :, 3].copy()
    r.smudge(layer, [(28, 20), (48, 20), (68, 20), (92, 20)], radius=12.0, strength=0.8)
    after = np.frombuffer(bytes(layer.data), dtype=np.uint8).reshape(H, W, 4)
    assert bytes(layer.data) != before
    assert (after[:, :, 3] == alpha_before).all()


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
