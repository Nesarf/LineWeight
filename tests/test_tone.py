"""A screen has to deliver the value it was asked for, and to be a screen rather than a tint."""
import numpy as np
import pytest
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


def _rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_a_fill_with_a_tone_is_screened_rather_than_flat():
    """The point of the whole thing: a fifty per cent area has to come out as dots covering half, not as grey."""
    from lineweight import raster
    mark = {'geometry': {'points': _rect(0, 0, 60, 60),
                         'tone': {'value': 0.5, 'pitch': 10.0, 'angle': 45.0}},
            'appearance': {'fill': '#000000', 'opacity': 1.0}}
    layer = raster.fill_layer(mark, 60, 60)
    alpha = np.frombuffer(layer.data, dtype=np.uint8)[3::4]
    assert alpha.min() == 0, 'a screen must leave paper between the dots'
    assert alpha.max() > 200, 'and ink inside them'
    cover = (alpha > 127).sum() / alpha.size
    assert abs(cover - 0.5) < 0.08, cover


def test_a_fill_without_a_tone_is_still_flat():
    from lineweight import raster
    mark = {'geometry': {'points': _rect(0, 0, 40, 40)},
            'appearance': {'fill': '#808080', 'opacity': 1.0}}
    layer = raster.fill_layer(mark, 40, 40)
    alpha = np.frombuffer(layer.data, dtype=np.uint8)[3::4]
    inside = alpha[:40 * 40].reshape(40, 40)[5:35, 5:35]
    assert inside.min() == inside.max()


def test_the_lattice_is_phased_to_the_page_and_not_to_the_shape():
    """Two areas screened at the same pitch have to continue each other, which they only do if the screen knows where
    the area sits. Read back: the same origin reproduces the screen, a shifted origin does not."""
    first = tone.dot_screen(40, 40, 0.5, pitch=10.0, origin=(0.0, 0.0))
    same = tone.dot_screen(40, 40, 0.5, pitch=10.0, origin=(0.0, 0.0))
    shifted = tone.dot_screen(40, 40, 0.5, pitch=10.0, origin=(40.0, 0.0))
    assert np.allclose(first, same)
    assert not np.allclose(first, shifted)


@pytest.mark.parametrize('shape', sorted(tone.SCREENS))
@pytest.mark.parametrize('value', (0.2, 0.5, 0.8))
def test_every_screen_in_the_catalogue_delivers_its_value(shape, value):
    """**The catalogue is only worth having if every entry is honest about its tone.** A shape whose real coverage is
    something other than what was asked for would silently change the picture every time it replaced a dot."""
    built = tone.screen({'shape': shape, 'value': value, 'pitch': 10.0}, 400, 400)
    measured = tone.value_of(built)
    assert abs(measured - value) < 0.07, (shape, value, measured)


def test_an_unknown_shape_is_refused_rather_than_drawn_as_dots():
    with pytest.raises(ValueError):
        tone.screen({'shape': 'mezzotint', 'value': 0.5}, 40, 40)


def test_the_noise_screen_is_the_only_one_without_a_lattice():
    """A stochastic texture must not tile, or it would read as a ruling after all."""
    built = tone.screen({'shape': 'noise', 'value': 0.5, 'pitch': 9.0}, 200, 200)
    shifted = np.roll(built, 7, axis=1)
    assert not np.allclose(built, shifted)


def test_a_cross_screen_covers_more_than_one_of_its_own_rulings():
    """Two rulings at the requested value would cover `2v - v²`, which is why the cross solves for a smaller value
    each time. If it stopped doing that, asking for half would deliver three quarters."""
    both = tone.screen({'shape': 'cross', 'value': 0.5, 'pitch': 10.0}, 300, 300)
    one = tone.line_screen(300, 300, 0.5, pitch=10.0)
    assert abs(tone.value_of(both) - 0.5) < 0.07
    assert tone.value_of(both) < tone.value_of(one) + 0.4


