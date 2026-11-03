"""The edge a line has, as a length in pixels -- which means it may not depend on how finely it was sampled.

**This file exists because of one factor of 2.5.** `crossing_width` multiplied its answer by the module's own sampling
step while `reference_lines` took its sections at a different one, so every edge written into a copied project was 2.5
times smaller than the line it came from: 1.48 where the drawing's crossing is 3.70. The copy was then drawn with hard
edges on soft drawings, and the acceptance table read that back as a fault of the trace.

The property is simple enough to state and it is the whole test: **the same boundary, sampled at two steps, must come
back as the same number of pixels.** A quadratically-sampled section and a finely-sampled one describe one line, and a
length that changes when the sampling changes is not a length.
"""

import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for extra in (ROOT, ROOT / 'tools'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import edge_profile                            # noqa: E402
from lineweight import raster                  # noqa: E402


def a_section(edge, step, ink=20.0, field=250.0, half=8.0):
    """One cross-section of a line whose boundary falls from field to ink over `edge` pixels.

    A linear falling ramp, so the 10-to-90 crossing is exactly 0.8 of the ramp's length. Built symmetric, because
    `crossing_width` reads both sides and averages them.
    """
    ramp = edge / 0.8
    xs = np.arange(-half, half + step, step)
    # Flat ink within `half - ramp` of the centre, then a linear rise to the field.
    flat = half - ramp
    rise = np.clip((np.abs(xs) - flat) / ramp, 0.0, 1.0)
    return ink + (field - ink) * rise


def test_a_boundary_is_the_same_length_at_any_sampling_step():
    """The fault that was found: 3.70 pixels of boundary reported as 1.48 because the step was not passed in."""
    for edge in (1.0, 2.5, 3.7, 6.0):
        coarse = edge_profile.crossing_width(a_section(edge, 0.25), 0.25)
        fine = edge_profile.crossing_width(a_section(edge, 0.1), 0.1)
        assert coarse is not None and fine is not None
        assert abs(coarse - edge) < 0.12, 'a %.2f pixel boundary read %.2f at a quarter-pixel step' % (edge, coarse)
        assert abs(fine - edge) < 0.12, 'a %.2f pixel boundary read %.2f at a tenth-pixel step' % (edge, fine)


def test_leaving_the_step_out_is_a_quarter_pixel_reading_not_a_silent_rescale():
    """The default is the module's own step, so the one caller that takes a tenth-pixel section needs to pass nothing.

    The other side of the same coin: a section taken at a quarter pixel and measured with the default comes back 2.5
    times too small -- which is not a bug in the default, it is the reason the argument exists. Stated as a test so the
    2.5 is a number in the repository rather than a story in a commit message.
    """
    section = a_section(3.7, 0.25)
    wrong = edge_profile.crossing_width(section)
    right = edge_profile.crossing_width(section, 0.25)
    assert wrong is not None and right is not None
    assert abs(right / wrong - 2.5) < 0.02


def test_a_boundary_this_soft_reaches_the_copy_as_a_soft_edge():
    """The two sides joined, in the renderer's own units: a record asking for `edge` crosses in that many pixels.

    **The record's `edge` is the whole ramp and the measurement is a tenth-to-ninetieth span**, which is 0.8 of it, so
    the test states the conversion rather than hiding it. This is the check that would have said "the parameter does
    nothing" instead of "the parameter is 2.5 times too small", because it goes through `stroke_record` and the
    renderer and measures the picture rather than the record.
    """
    from lineweight import core

    page = 2880
    width = 600
    height = 600
    for crossing in (1.0, 3.7, 6.0):
        edge = crossing / edge_profile.CROSSING_SHARE
        record = core.stroke_record([(40, 300), (560, 300)], 'fine', seed=3, resolution=2, edge=edge,
                                    page_long=page, absolute_width=True,
                                    width_profile=[20.0, 20.0])
        layer = raster.sweep_layer(record, width, height)
        section = np.array([layer.data[(y * width + 300) * 4 + 3] for y in range(height)], dtype=np.float64)
        measured = edge_profile.crossing_width(section, 1.0)
        assert measured is not None, 'an edge of %.2f produced no measurable boundary' % edge
        assert abs(measured - crossing) < max(0.6, crossing * 0.25), (
            'a %.2f pixel crossing was drawn as %.2f' % (crossing, measured))
