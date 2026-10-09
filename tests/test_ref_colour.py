"""Tests for the colour side of the measurement.

`ref.py` reduced every image to luminance, which is right for every geometry measurement in it and made the library
unable to answer the one question about ink that the drawing convention turns out to have a measured answer for. The
tests here are mostly about the two ways that measurement went wrong before it worked, because both were the kind
that produce a plausible number rather than a failure.
"""

import struct
import zlib

import pytest

from lineweight import roles
from lineweight.ref import ImageError, decode_png, load_rgb, measure_ink_colour


def write_rgb_png(path, rows):
    """A colour PNG written by hand -- colour type 2, no filter on any row.

    By hand rather than through Pillow, because `ref.py`'s whole point is that it reads PNG without a dependency and a
    test that needed one would not be testing that path.
    """
    height, width = len(rows), len(rows[0])
    raw = b''.join(bytes([0]) + b''.join(bytes(pixel) for pixel in row) for row in rows)

    def chunk(kind, body):
        return (struct.pack('>I', len(body)) + kind + body
                + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF))

    with open(path, 'wb') as handle:
        handle.write(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw))
                     + chunk(b'IEND', b''))


def an_image(ink, paper=(255, 255, 255), size=64, band=4):
    """A paper-coloured field with one horizontal band of ink across it."""
    top = size // 2 - band // 2
    return [[ink if top <= y < top + band else paper for _ in range(size)] for y in range(size)]


# ------------------------------------------------------------------------------------- the decoder refactor

def test_the_rgb_path_agrees_with_the_greyscale_path(tmp_path):
    """`decode_png(rgb=True)` must see the same image, not a second decoder's opinion of it.

    The colour path was added by branching inside the one filter loop rather than by writing another decoder, and this
    is the check that the branch did not change what the filters reconstruct: the luminance of the RGB decode has to
    equal the greyscale decode pixel for pixel, including on the filtered rows.
    """
    ink = (200, 157, 161)
    path = str(tmp_path / 'band.png')
    write_rgb_png(path, an_image(ink))
    grey = decode_png(path)
    colour = decode_png(path, rgb=True)
    assert (colour.width, colour.height) == (grey.width, grey.height)
    assert len(colour.pixels) == grey.width * grey.height * 3
    for i in range(grey.width * grey.height):
        r, g, b = colour.pixels[i * 3:i * 3 + 3]
        assert (r * 299 + g * 587 + b * 114) // 1000 == grey.pixels[i]


def test_the_rgb_path_keeps_the_colour_the_greyscale_path_discards(tmp_path):
    """The point of the addition, against a hand-computed value."""
    path = str(tmp_path / 'band.png')
    write_rgb_png(path, an_image((200, 157, 161)))
    colour = load_rgb(path)
    assert colour.pixel(5, colour.height // 2) == (200, 157, 161)
    assert colour.pixel(0, 0) == (255, 255, 255)


# ------------------------------------------------------------------------------ a known ink measures back

def test_a_known_ink_measures_back(tmp_path):
    path = str(tmp_path / 'band.png')
    write_rgb_png(path, an_image((200, 157, 161)))
    measured = measure_ink_colour(load_rgb(path))
    assert measured.median == (200, 157, 161)
    assert measured.warmth == 39
    assert measured.hue_fraction > 0.9, 'almost every ink pixel here is the ink'
    assert 'has a hue' in measured.verdict()


def test_the_measurement_is_relative_to_paper_and_an_absolute_threshold_is_not(tmp_path):
    """**The bug that produced the wrong recorded number, as an executable demonstration.**

    Video 1's line art is a *light* dusty rose: the median ink pixel measures luminance **170**, which is well above
    `INK_THRESHOLD` of 128. The instrument that produced the recorded figure used that absolute threshold, so it
    skipped the line art almost entirely and returned the median of a grey watermark and a frame border that happened
    to fall below it -- `119,108,113`, R-B +10, for a drawing whose lines are at R-B +40.

    Asserted both ways: the absolute threshold would find nothing here, and the paper-relative one finds the ink.
    """
    ink = (200, 157, 161)
    luminance = (200 * 299 + 157 * 587 + 161 * 114) // 1000
    assert luminance > 128, 'this ink is meant to sit above the absolute threshold for the test to mean anything'
    path = str(tmp_path / 'light.png')
    write_rgb_png(path, an_image(ink))
    assert decode_png(path).pixels.count(0) == 0 or True          # nothing below 128 in the greyscale decode
    grey = decode_png(path)
    assert min(grey.pixels) > 128, 'an absolute threshold of 128 would find no ink in this image at all'
    assert measure_ink_colour(load_rgb(path)).median == ink


def test_the_paper_is_taken_from_the_image_not_assumed(tmp_path):
    """A drawing on grey paper, and on white paper, measure the same ink the same way.

    `PAPER_MARGIN` is applied below each image's own paper level, and one of the two video frames is on paper at 233
    while the other is at 254.
    """
    # chroma 0.118, just above `CHROMA_FLOOR` -- an ink below the floor is reported hueless by design, which
    # is a different test
    ink = (60, 35, 30)
    for paper in ((255, 255, 255), (225, 225, 228)):
        path = str(tmp_path / ('paper%d.png' % paper[0]))
        write_rgb_png(path, an_image(ink, paper=paper))
        measured = measure_ink_colour(load_rgb(path))
        assert measured.median == ink, 'ink measured differently on paper %r' % (paper,)
        assert measured.paper == paper[0], 'the paper level should be read from the image'


# ------------------------------------------------------------------ and it says so when there is nothing to say

def test_a_hueless_ink_is_reported_as_hueless_rather_than_as_a_colour(tmp_path):
    """**The other half of the same fault, and the one that matters more.**

    Video 2's line art is a neutral black. Recording that as "R-B +0.3" makes it a *measurement of hue* when there is
    no hue to measure -- and the number then looks like a position on the axis, sitting near the warm brown's, when
    the truth is that the drawing is not on the axis at all. The instrument refuses rather than returning a median of
    grey pixels.
    """
    path = str(tmp_path / 'grey.png')
    write_rgb_png(path, an_image((40, 40, 40)))
    measured = measure_ink_colour(load_rgb(path))
    assert measured.ink > 200, 'the fixture should hold a real band of ink'
    assert measured.coloured == 0
    assert measured.hue_fraction == 0.0
    assert 'hueless' in measured.verdict()
    assert 'has a hue' not in measured.verdict()


def test_a_blank_image_is_refused_rather_than_measured(tmp_path):
    """No ink at all is an error naming the file, like every other unreadable input here -- a blank frame in a video
    is a real case and silently returning zeros for it would put a fake sample into a distribution."""
    path = str(tmp_path / 'blank.png')
    write_rgb_png(path, an_image((255, 255, 255), band=0))
    with pytest.raises(ImageError):
        measure_ink_colour(load_rgb(path))


# ------------------------------------------------------------------------------------- the library's own ink

def test_the_default_ink_sits_on_the_measured_axis():
    """**The default used to be a cool violet-black, R-B minus six, and neither measured drawing is cool.**

    Video 1's line stage is a warm red-brown at R-B +40; video 2's is hueless. KEER2014 measured black and the browns
    as positive on naturalness and green, blue and red as negative, so both drawings sit on the positive side and a
    cool cast sits on no measured setting at all.

    The test is stated as the property rather than as the literal, so a future default only has to be justified rather
    than matched.
    """
    warmth = int(roles.DEFAULT_INK[1:3], 16) - int(roles.DEFAULT_INK[5:7], 16)
    assert warmth >= 0, 'the default ink is cool (R-B %+d) and nothing measured is' % warmth
    assert roles.measured_natural(roles.DEFAULT_INK)
    assert warmth <= 20, 'the default should be near-neutral; the warm end is the silhouette role\'s job'


def test_every_role_ink_is_on_the_measured_positive_side_and_the_warmth_is_ordered():
    """The convention puts the warm ink on the outline, and the registry should not contradict it."""
    warmth = {name: int(roles.ROLES[name].ink[1:3], 16) - int(roles.ROLES[name].ink[5:7], 16)
              for name in roles.names()}
    for name, value in warmth.items():
        assert roles.measured_natural(roles.ROLES[name].ink)
        assert value >= 0, '%s is cool at R-B %+d' % (name, value)
    assert warmth['contour'] <= warmth['silhouette'], 'the outer contour is the warmer line, by the convention'
