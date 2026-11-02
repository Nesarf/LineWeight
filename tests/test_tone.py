"""A screen has to deliver the value it was asked for, and to be a screen rather than a tint."""
import numpy as np
from scipy import ndimage

from lineweight import tone


def test_zero_and_one_are_flat():
    assert tone.dot_screen(20, 20, 0.0).max() == 0.0
    assert tone.dot_screen(20, 20, 1.0).min() == 1.0
    assert tone.line_screen(20, 20, 0.0).max() == 0.0
    assert tone.line_screen(20, 20, 1.0).min() == 1.0


def test_a_dot_screen_delivers_the_value_it_was_asked_for():
    """**The one thing a screen must not do is lie about its own tone.**"""
    for value in (0.1, 0.25, 0.5, 0.75, 0.9):
        screen = tone.dot_screen(400, 400, value, pitch=10.0)
        measured = tone.value_of(screen)
        assert abs(measured - value) < 0.04, (value, measured)


def test_a_line_screen_delivers_the_value_it_was_asked_for():
    for value in (0.2, 0.5, 0.8):
        screen = tone.line_screen(400, 400, value, pitch=10.0)
        measured = tone.value_of(screen)
        assert abs(measured - value) < 0.045, (value, measured)


def test_a_finer_pitch_puts_more_dots_on_the_page():
    """The pitch is a length on the page, so the dot count must follow it -- that is what makes it a screen and not a
    tint that happens to be made of dots."""
    fine = tone.dot_screen(200, 200, 0.3, pitch=5.0)
    coarse = tone.dot_screen(200, 200, 0.3, pitch=20.0)
    fine_blobs = ndimage.label(fine > 0.5)[1]
    coarse_blobs = ndimage.label(coarse > 0.5)[1]
    assert fine_blobs > coarse_blobs * 8, (fine_blobs, coarse_blobs)


def test_the_lattice_is_rotated_so_it_does_not_line_up_with_the_page():
    """A screen at nought degrees would run parallel to every vertical and horizontal stroke in the drawing; the
    printing convention is forty-five, and that has to change the picture."""
    square = tone.dot_screen(120, 120, 0.3, pitch=12.0, angle=0.0)
    rotated = tone.dot_screen(120, 120, 0.3, pitch=12.0, angle=45.0)
    assert not np.allclose(square, rotated)


def test_a_dot_edge_softens_the_way_a_stroke_edge_does():
    """Coverage has to pass through intermediate values, or a screen would be a stair-stepped bitmap pasted on a
    drawing whose lines are all anti-aliased."""
    screen = tone.dot_screen(80, 80, 0.4, pitch=14.0)
    partial = ((screen > 0.0) & (screen < 1.0)).sum()
    assert partial > 100
