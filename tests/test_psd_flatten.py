"""The array composite and the pixel loop have to produce the same bytes.

`flatten` builds a PSD's merged section -- what a viewer that ignores layers puts on screen. It used to do that one
pixel at a time, four million iterations on a 1400x900 page. `_flatten_pixels` is that loop, kept as the reference,
and `_flatten_numpy` is what runs.

**The one thing that could make this a change of picture rather than a rewrite is the rounding.** Both sides send a
half to the nearest even integer, and the tests below lean on that rather than argue it: random alphas, random colours,
several layers, then a byte comparison.
"""
from __future__ import annotations

import numpy as np
import pytest

from lineweight import psd


def a_layer(width, height, alphas, colour=(200, 40, 30), opacity=1.0, visible=True):
    layer = psd.Layer('L', width, height, opacity=opacity, visible=visible)
    for index, alpha in enumerate(alphas):
        layer.data[index * 4 + 0] = colour[0]
        layer.data[index * 4 + 1] = colour[1]
        layer.data[index * 4 + 2] = colour[2]
        layer.data[index * 4 + 3] = int(alpha)
    return layer


def compare(layers, width, height, background=255):
    fast = psd.flatten(layers, width, height, background)
    slow = psd._flatten_pixels(layers, width, height, background)
    return bytes(fast), bytes(slow)


def test_an_empty_stack_is_just_the_paper():
    reference, vectorised = compare([], 5, 4)
    assert reference == vectorised
    assert set(reference[0::4]) == {255}, 'the paper is opaque'


def test_one_opaque_layer_agrees_pixel_for_pixel():
    alphas = [255] * 20
    reference, vectorised = compare([a_layer(5, 4, alphas)], 5, 4)
    assert reference == vectorised
    assert list(reference[0::4]) == [200] * 20


def test_two_layers_agree_pixel_for_pixel():
    rng = np.random.default_rng(4)
    first = a_layer(6, 5, rng.integers(0, 256, 30), colour=(10, 200, 90))
    second = a_layer(6, 5, rng.integers(0, 256, 30), colour=(240, 30, 20))
    reference, vectorised = compare([first, second], 6, 5)
    assert reference == vectorised


def test_a_layer_opacity_below_one_agrees_pixel_for_pixel():
    rng = np.random.default_rng(5)
    layer = a_layer(7, 3, rng.integers(0, 256, 21), opacity=0.37)
    reference, vectorised = compare([layer], 7, 3)
    assert reference == vectorised


def test_an_invisible_layer_is_skipped_by_both():
    rng = np.random.default_rng(6)
    hidden = a_layer(4, 4, rng.integers(0, 256, 16), visible=False)
    reference, vectorised = compare([hidden], 4, 4)
    assert reference == vectorised
    assert set(reference[0::4]) == {255}, 'a hidden layer must not reach the merged image'


def test_a_fully_transparent_layer_leaves_the_paper_alone():
    reference, vectorised = compare([a_layer(4, 4, [0] * 16)], 4, 4)
    assert reference == vectorised
    assert set(reference[0::4]) == {255}


def test_a_halved_alpha_agrees_at_the_rounding_boundary():
    """128/255 of a mid colour over white lands at a fraction that the two roundings could disagree about. They do not,
    and this is the case that would say so first."""
    reference, vectorised = compare([a_layer(1, 1, [128], colour=(200, 40, 30))], 1, 1)
    assert reference == vectorised
    assert reference[3] == 255


def test_a_background_other_than_white_agrees():
    rng = np.random.default_rng(7)
    layer = a_layer(5, 5, rng.integers(0, 256, 25), colour=(90, 140, 210))
    for background in (0, 64, 200):
        reference, vectorised = compare([layer], 5, 5, background=background)
        assert reference == vectorised, 'background %d' % background


def test_three_random_layers_agree_over_a_larger_page():
    rng = np.random.default_rng(8)
    width, height = 40, 30
    layers = [a_layer(width, height, rng.integers(0, 256, width * height),
                      colour=tuple(int(v) for v in rng.integers(0, 256, 3)),
                      opacity=float(rng.uniform(0.2, 1.0)))
              for _ in range(3)]
    reference, vectorised = compare(layers, width, height)
    assert reference == vectorised
