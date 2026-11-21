"""The vectorised write and the pixel loop have to produce the same bytes, not merely the same picture.

`sweep_layer` ends by turning a coverage array into RGBA, and it used to do that one pixel at a time. That loop is now
`_flatten_ink`, kept in the file as the reference, and `_flatten_ink_numpy` is what runs. The argument for their
equivalence is short -- `np.rint` and `round()` both round a half to even, `astype` and `int()` both truncate -- but an
argument is what a rewrite drifts from silently, so these tests compare bytes instead.

**Two roundings live in that function and they are not interchangeable.** The alpha channel uses `round()`; the three
colour channels use `int()`, which truncates. They disagree on every value whose fraction is above a half, so a
tidier version that used one rule for all four channels would change most of the pixels in a drawing while looking
entirely plausible. That is what the truncation test is for.
"""
from __future__ import annotations

import numpy as np
import pytest

from lineweight import core
from lineweight import raster as r


def both_paths(ink, red=None, green=None, blue=None, colour=(26, 22, 32)):
    height, width = ink.shape
    reference = bytearray(width * height * 4)
    vectorised = bytearray(width * height * 4)
    r._flatten_ink(ink, red, green, blue, colour, width, height, reference)
    r._flatten_ink_numpy(ink, red, green, blue, colour, width, height, vectorised)
    return bytes(reference), bytes(vectorised)


def test_a_layer_with_no_ink_stays_empty():
    ink = np.zeros((40, 60), dtype=np.float64)
    reference, vectorised = both_paths(ink)
    assert reference == vectorised
    assert set(reference) == {0}, 'a pixel with no coverage must stay untouched, alpha included'


def test_one_colour_strokes_agree_pixel_for_pixel():
    rng = np.random.default_rng(11)
    for _ in range(8):
        ink = rng.random((37, 53)) ** 2.0
        reference, vectorised = both_paths(ink)
        assert reference == vectorised


def test_a_colour_profile_agrees_pixel_for_pixel():
    rng = np.random.default_rng(12)
    for _ in range(8):
        shape = (29, 47)
        ink = rng.random(shape)
        red, green, blue = (rng.random(shape) * 255.0 for _ in range(3))
        reference, vectorised = both_paths(ink, red, green, blue)
        assert reference == vectorised


def test_the_alpha_channel_rounds_and_the_colour_channels_truncate():
    """The rule that a tidier implementation would break. 100.7 becomes 100 in a colour channel and would be 101 under
    the rounding the alpha channel uses; if this ever reports 101 for the colour, the two rules were merged."""
    ink = np.full((1, 1), 1.0, dtype=np.float64)
    plane = np.full((1, 1), 100.7, dtype=np.float64)
    reference, vectorised = both_paths(ink, plane, plane, plane)
    assert reference == vectorised
    assert reference[0] == 100, 'the colour channel truncates'
    assert reference[3] == 255, 'the alpha channel rounds'


def test_a_half_in_the_alpha_rounds_to_even_on_both_paths():
    """`np.rint` and `round()` both send a half to the nearest even integer, which is the one place a vectorised
    version rewritten with `int(a * 255 + 0.5)` would differ on half the channels."""
    levels = np.array([0.5, 1.5, 2.5, 3.5, 10.5, 11.5], dtype=np.float64)
    ink = (levels / 255.0).reshape(1, -1)
    reference, vectorised = both_paths(ink)
    assert reference == vectorised
    alphas = list(reference[3::4])
    expected = [int(round(value)) for value in levels]
    assert alphas == expected


def test_coverage_outside_zero_and_one_is_clipped_the_same_way():
    ink = np.array([[-0.4, -1e-9, 0.0, 1.0, 1.4, 3.0]], dtype=np.float64)
    reference, vectorised = both_paths(ink)
    assert reference == vectorised
    assert list(reference[3::4])[:3] == [0, 0, 0], 'coverage at or below zero writes nothing'
    assert list(reference[3::4])[3:] == [255, 255, 255], 'coverage above one clips'


def test_a_rendered_stroke_is_the_same_bytes_under_either_path(monkeypatch):
    """The end-to-end version, on a coverage array the renderer actually produced rather than a random one."""
    record = core.stroke_record(
        [(12.0, 20.0), (60.0, 34.0), (104.0, 22.0)], 'brush', seed=5,
        width_profile=[6.0, 11.0, 7.0], alpha_profile=[0.5, 0.8, 0.45],
        absolute_width=True, edge=2.5, soft=0.4)
    fast = r.sweep_layer(dict(record), 120, 80)
    monkeypatch.setattr(r, '_flatten_ink_numpy', r._flatten_ink)
    slow = r.sweep_layer(dict(record), 120, 80)
    monkeypatch.undo()
    assert bytes(fast.data) == bytes(slow.data)


def test_a_graded_stroke_with_a_colour_profile_is_the_same_bytes_under_either_path(monkeypatch):
    """The same end-to-end check on the path that writes three channels instead of one."""
    record = core.stroke_record(
        [(14.0, 16.0), (70.0, 40.0), (110.0, 18.0)], 'wash', seed=9,
        colour_profile=[[40, 30, 20], [180, 120, 90], [60, 40, 30]],
        width_profile=[9.0, 13.0], alpha_profile=[0.6, 0.75])
    fast = r.sweep_layer(dict(record), 128, 64)
    monkeypatch.setattr(r, '_flatten_ink_numpy', r._flatten_ink)
    slow = r.sweep_layer(dict(record), 128, 64)
    monkeypatch.undo()
    assert bytes(fast.data) == bytes(slow.data)
    assert fast.data[3::4] and any(fast.data[3::4]), 'the stroke has to have covered something to be a test'
