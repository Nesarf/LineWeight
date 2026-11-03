"""Two quantities that are easy to get backwards: how far the ink reaches across a hollow band, and where a section is
half as deep as its own ink.

**Both were wrong on the first attempt and neither showed up as a failing picture.** The ring formula transformed the holes
instead of their complement -- `distance_transform_edt` measures to the nearest *zero* pixel, so on the ink it returned
nought everywhere and the correction fired nowhere, while every number it touched stayed exactly as before. The half-depth
width reported a ratio of 1.00 against a "truth" computed by the same function, which is a tautology rather than a check.

So the tests here are about the arithmetic of the two quantities and nothing else: a band with a hollow in it must come
back at the band's width, a pinhole must not change anything, and a triangle must be as wide at half its depth as its base.
"""

import pathlib
import sys

import numpy as np
from scipy import ndimage

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for extra in (ROOT, ROOT / 'tools'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from reference_lines import _half_depth_width, ring_room   # noqa: E402


def a_band(height=20, length=80, hollow=None):
    """A band of ink with an optional hollow punched out of it, centred on a 100-pixel page."""
    mask = np.zeros((100, 100), dtype=bool)
    top = 50 - height // 2
    mask[top:top + height, 10:10 + length] = True
    if hollow:
        gap = hollow // 2
        middle = 50
        mask[middle - gap:middle + gap, 20:20 + length - 20] = False
    return mask


def test_a_hollow_band_is_measured_across_its_hollow():
    """The whole point: twice the transform measures the rim of a hollow band, and the band is the rim plus the hollow."""
    mask = a_band(height=20, hollow=10)
    edt = ndimage.distance_transform_edt(mask)
    room = ring_room(mask, edt)
    # **Only the columns the hollow reaches.** At the band's own ends the transform measures the band correctly, because
    # there is no hollow to fall into -- comparing there would say the correction is not needed.
    span = slice(30, 60)
    here = mask[:, span]
    rim = float((2.0 * edt[:, span])[here].max())
    widest = float(room[:, span][here].max())
    assert rim < 7.0, 'the transform already reported the band, so this test is not measuring the correction: %.2f' % rim
    assert widest > 0.8 * 20.0, 'the band came back at %.2f rather than near its own 20 pixels' % widest


def test_a_pinhole_does_not_widen_anything():
    """A two-pixel hole in a hatched pass is not a hollow, and widening a stroke by its radius is how a line gets fat."""
    mask = a_band(height=10)
    mask[49:51, 40:42] = False
    edt = ndimage.distance_transform_edt(mask)
    room = ring_room(mask, edt)
    plain = 2.0 * edt
    assert np.allclose(room[mask], plain[mask]), 'a pinhole changed the width somewhere'


def test_a_mask_with_no_holes_costs_nothing_and_changes_nothing():
    mask = a_band(height=10)
    edt = ndimage.distance_transform_edt(mask)
    assert np.allclose(ring_room(mask, edt), 2.0 * edt)


def test_half_depth_width_of_a_triangle_is_its_base():
    """A triangular section is half as deep as its ink halfway out, so the two half-depth points are the base's ends."""
    width = 8.0
    step = 0.25
    offsets = np.arange(-12.0, 12.0 + step, step)
    section = 255.0 - 235.0 * np.clip(1.0 - np.abs(offsets) / width, 0.0, 1.0)
    measured = _half_depth_width(section, offsets)
    assert measured is not None
    assert abs(measured - width) < 0.6, 'a %.1f pixel triangle measured %.2f at half depth' % (width, measured)


def test_half_depth_width_refuses_a_section_with_no_line_in_it():
    """Paper with a smudge is not a line, and a width is not a number to guess."""
    step = 0.25
    offsets = np.arange(-12.0, 12.0 + step, step)
    assert _half_depth_width(np.full_like(offsets, 250.0), offsets) is None
