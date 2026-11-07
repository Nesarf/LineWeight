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


def rendered(**kwargs):
    record = core.stroke_record([(20, 20), (60, 20), (100, 20)], 'brush', seed=1,
                                width_profile=[24.0, 24.0, 24.0], absolute_width=True, edge=8.0, **kwargs)
    return np.frombuffer(bytes(r.sweep_layer(record, W, H).data), dtype=np.uint8).reshape(H, W, 4)


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
