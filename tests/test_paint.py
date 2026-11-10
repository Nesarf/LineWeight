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


def test_clipping_takes_the_thickness_with_the_colour():
    """A clipped layer must not keep thickness outside the shape.

    The colour is cut but `relief` is what `light` reads: a whole relief under a cut layer leaves a cliff along the
    cut, and the light draws a bright line exactly at the edge. That is the one visible artefact clipping can
    produce, and it turned up the first time a contour was drawn in `tools/paint_pair.py`.
    """
    layer = painted(height=0.5, colour='#c04030')
    mask = r.Layer(W, H)
    r.fill_polygon(mask, [(0, 0), (W // 2, 0), (W // 2, H), (0, H)], (255, 255, 255), 1.0)
    cut = r.clip(layer, mask)
    assert cut.relief is not None, 'clipping dropped the relief entirely'
    assert cut.relief[:, W // 2 + 2:].max() < 1e-9, 'thickness survived outside the mask'
    assert cut.relief[:, : W // 2 - 2].max() > 0.0, 'thickness was removed inside the mask too'


def test_clipping_a_layer_without_relief_only_cuts_the_alpha():
    """The path every clipped drawing took before relief existed, and it must still clip exactly as it did."""
    layer = painted(colour='#c04030')
    mask = r.Layer(W, H)
    r.fill_polygon(mask, [(0, 0), (W // 2, 0), (W // 2, H), (0, H)], (255, 255, 255), 1.0)
    cut = r.clip(layer, mask)
    assert cut.relief is None
    assert cut.data[(20 * W + 104) * 4 + 3] == 0, 'alpha survived outside the mask'
    assert cut.data[(20 * W + 30) * 4 + 3] > 0, 'alpha was removed inside the mask'


PROBE_W, PROBE_H = 200, 60


def probe_stroke(widths):
    """One straight stroke through the path a picture takes, and its alpha grid."""
    from lineweight import project
    fig = project.Project(width=PROBE_W, height=PROBE_H, title='probe')
    fig.add_stroke(core.stroke_record([(20, 30), (90, 30), (160, 30)], 'brush', seed=1,
                                      width_profile=widths, alpha_profile=[0.8, 0.8, 0.8],
                                      absolute_width=True, edge=1.0),
                   stage='line', layer='paint', note='')
    layer = r.render_marks([m.to_dict() for m in fig.marks], PROBE_W, PROBE_H, sweep=True)
    return np.frombuffer(bytes(layer.data), dtype=np.uint8).reshape(PROBE_H, PROBE_W, 4)


def test_a_width_profile_reaches_the_middle_of_the_stroke():
    """宽度剖面要铺满整条路径 —— 只覆盖起笔的剖面等于没有剖面。

    **这一条是补上的，而它漏了很久。** 中心的点被重采样成几十个，而 `width_profile` 还是调用者写的那几个值；
    渲染按重采样段的下标取值，于是曲线只作用在路径最前面几段，之后全是最后一个值。修之前，一条「起笔六、中间
    二十四、收笔六」的笔在中间量出来是六 —— 而 381 项测试没有一项发现它。这是它值得一条测试的全部理由。
    """
    wide = probe_stroke([6.0, 24.0, 6.0])
    flat = probe_stroke([6.0, 6.0, 6.0])

    def across(image, x):
        return int((image[:, x, 3] > 128).sum())

    assert across(wide, 90) > across(flat, 90) + 6, 'the middle of the stroke ignored its profile'
    assert across(wide, 22) < across(wide, 90) - 6, 'the ends and the middle came out the same width'


def test_a_varying_profile_does_not_leave_beads_along_the_stroke():
    """沿中线相邻像素的 alpha 不该大跳 —— 一串珠子是 dab 间距与半径不同步留下的。

    修之前这样一条笔沿中线在 0.31 与 1.00 之间以约八像素的周期跳，而同样一条常宽度的笔是平的（0.541 到 0.600，
    零次跳动）。`tools/probe_stroke_dab.py` 保留着这两行数。
    """

    def jumps(image):
        line = image[30, 20:160, 3].astype(int)
        return sum(1 for i in range(1, len(line)) if abs(line[i] - line[i - 1]) > 20)

    assert jumps(probe_stroke([13.0, 13.0, 13.0])) == 0
    assert jumps(probe_stroke([7.0, 13.0, 13.0, 6.0])) <= 2


def test_bleed_leaves_the_boundary_alone_when_it_is_zero():
    """`bleed` 是第五个上色字段，而它的默认值必须是零，否则此前每一张画都会变。

    判据和 `soft`、`colour_profile` 一样：**一个默认什么都不做的字段，才能加进一条已经有很多张画依赖的渲染路径。**
    """
    assert np.array_equal(rendered(bleed=0.0)[:, :, 3], rendered()[:, :, 3])


def test_bleed_puts_ink_outside_the_mark_and_leaves_the_core_alone():
    """湿笔的墨在笔的有效半径之外，而笔心不动。

    干笔在端点之外是空白；湿笔在同一处有墨（那个指数尾巴），而笔心的 alpha 与干笔相同。**把这两件事混在一起 ——
    比如用 `soft` 做湿 —— 得到的是整笔发灰，那不是墨渗出去，那是墨变淡了。**
    """
    dry = rendered()
    wet = rendered(bleed=14.0)
    assert dry[20, 118, 3] == 0, 'the dry stroke reached outside its own end'
    assert wet[20, 118, 3] > 0, 'the wet stroke did not bleed past its end'
    assert abs(int(wet[20, 60, 3]) - int(dry[20, 60, 3])) <= 2, 'the wet stroke dimmed its own core'

