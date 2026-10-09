"""Tests for the curve fitter.

The fit has one property -- **the fitted curve stays within the requested distance of the polyline** -- and the first
implementation appeared to have it while not having it, so most of these tests are about that property specifically:
what it means, how to measure it, and how it was measured wrong.
"""

import math

import pytest

from lineweight import curve


def a_circle(radius=100.0, count=100, cx=100.0, cy=100.0):
    return [(cx + radius * math.cos(2 * math.pi * i / count), cy + radius * math.sin(2 * math.pi * i / count))
            for i in range(count + 1)]


def a_sine(count=120, amplitude=40.0):
    return [(i * 2.0, amplitude * math.sin(i / 5.0)) for i in range(count)]


# ------------------------------------------------------------------------------------------------- the one property

def test_a_fit_meets_its_tolerance_on_smooth_input():
    """A circle and a sine wave, at two tolerances each, and the deviation measured rather than assumed.

    The measured value is asserted to be a real fit and not a coincidence of the tolerance being loose: at a tenth of
    the tolerance a good fitter needs more segments, and it must still come in under.
    """
    for points in (a_circle(), a_sine()):
        for tolerance in (0.05, 0.5):
            chain = curve.fit_chain(points, tolerance)
            assert chain, 'no curve was produced for a %d-point input' % len(points)
            assert curve.deviation(points, chain) <= tolerance


def test_a_fit_never_bulges_out_of_the_shape():
    """**The regression.** A closed five-point square is what `inked_svg` actually hands the expander.

    The first fitter produced a segment from (378,102) to (301,179) with its handles at (435,157) and (347,226) -- the
    shape is inside 296.8..382.1 by 96.8..181.5, so the curve left it by about 50 units. Every input point was still
    near the curve, so the one-directional check reported 0.0000 and a test that only looked at the outline's own
    points would have passed.

    Asserted on the *extent* of the drawn curve as well as on `deviation`, because a bound is only as good as the
    measurement behind it and the extent is a second, independent way of seeing the same defect.
    """
    square = [(300.0, 100.0), (380.0, 100.0), (380.0, 180.0), (300.0, 180.0), (300.0, 100.0)]
    for tolerance in (0.065, 0.5):
        chain = curve.fit_chain(square, tolerance)
        drawn = curve.sample(chain, 24)
        assert curve.deviation(square, chain) <= tolerance
        assert min(p[0] for p in drawn) >= 300.0 - tolerance
        assert max(p[0] for p in drawn) <= 380.0 + tolerance
        assert min(p[1] for p in drawn) >= 100.0 - tolerance
        assert max(p[1] for p in drawn) <= 180.0 + tolerance


def test_one_directional_measurement_cannot_see_a_bulge():
    """**The negative control for the test above**, and the reason `deviation` is two-sided.

    A cubic is built with its chord as the only input and a deliberate 45-unit bulge between the ends. Measured
    point-to-curve it is **perfect**: its two endpoints are exactly on it, so that direction reports zero. Measured
    curve-to-polyline it is 45 units wrong. The first version of `deviation` made only the first measurement, which
    is how a fit that left a closed square by 50 units came with a reading of 0.0000.

    Written against the measurement rather than against the fitter on purpose: this is a statement about what a
    one-directional check can see, and it has to hold whatever `fit_chain` does.
    """
    chord = [(0.0, 0.0), (20.0, 0.0)]
    bulging = ((0.0, 0.0), (0.0, 60.0), (20.0, 60.0), (20.0, 0.0))
    forward = max(curve.distance_to_chain(p, [bulging]) for p in chord)
    backward = curve.distance_to_polyline(curve.cubic_at(bulging, 0.5), chord)
    # Not exactly zero: `distance_to_chain` refines with a ternary search, so it has a floor of about 3e-5 of the
    # curve's size. That floor is five orders of magnitude below the bulge, which is the point being made.
    assert forward < 1e-3, 'the endpoints are on the curve, so this direction is blind by construction'
    assert backward > 40.0, 'the bulge should be enormous in the other direction'
    assert curve.deviation(chord, [bulging]) > 40.0, 'deviation must take the worse of the two'


def test_an_unfittable_polyline_falls_back_to_lines_rather_than_breaking_the_promise():
    """A zigzag cannot be fitted by splitting, so the fitter admits it instead of returning a bad fit.

    Measured 17.9 units of deviation against a requested 0.2 before the fallback existed. **A function whose one
    documented property is sometimes violated is worse than one that is slower**, because every caller then has to
    know when the promise holds -- which is exactly the class of failure this project keeps finding in its own checks.
    """
    zigzag = [(i * 3.0, 0.0 if i % 2 else 30.0) for i in range(60)]
    for tolerance in (0.2, 0.01):
        chain = curve.fit_chain(zigzag, tolerance)
        assert curve.deviation(zigzag, chain) <= tolerance
    # and the fallback is a fallback, not the normal path
    assert len(curve.fit_chain(a_circle(), 0.5)) < 20


def test_a_straight_line_is_one_segment():
    """The simplest case, because a fitter that cannot recognise a line will subdivide every flat stretch."""
    chain = curve.fit_chain([(i * 5.0, 0.0) for i in range(50)], 0.01)
    assert len(chain) == 1
    assert curve.deviation([(i * 5.0, 0.0) for i in range(50)], chain) <= 0.01


def test_a_fit_starts_and_ends_exactly_on_the_input():
    """The ends are pinned, not approximated -- the outline's two end caps are straight lines to these exact points,
    so a fit that moved them would open a gap in the closed loop."""
    points = a_sine()
    chain = curve.fit_chain(points, 0.05)
    assert chain[0][0] == pytest.approx(points[0])
    assert chain[-1][3] == pytest.approx(points[-1])


# ------------------------------------------------------------------------------------------------ degenerate input

def test_degenerate_input_is_handled_rather_than_crashing():
    """Fewer than two points, repeated points, and zero-length chords.

    The split in `_fit` halves on the worst point, so identical points are the case where a naive implementation
    recurses for ever; and `chord_lengths` divides by the total, which is zero when every point is the same.
    """
    assert curve.fit_chain([]) == []
    assert curve.fit_chain([(1.0, 2.0)]) == []
    two = curve.fit_chain([(0.0, 0.0), (10.0, 0.0)], 0.01)
    assert len(two) == 1 and curve.deviation([(0.0, 0.0), (10.0, 0.0)], two) <= 0.01
    same = [(5.0, 5.0)] * 8
    assert curve.deviation(same, curve.fit_chain(same, 0.01)) <= 0.01
    assert curve.chord_lengths(same)[-1] == 1.0, 'a zero total must not divide by zero'


def test_the_default_tolerance_scales_with_the_input():
    """`error=0` means "relative to these points", so a caller that only wants smoothness does not have to know the
    drawing's scale -- and the same shape at ten times the size does not get ten times the segments."""
    small = a_circle(radius=10.0)
    large = a_circle(radius=1000.0)
    assert len(curve.fit_chain(small)) == len(curve.fit_chain(large))
    assert curve.deviation(small, curve.fit_chain(small)) <= curve.DEFAULT_ERROR * 20.0


def test_the_chain_can_be_written_as_path_data_and_read_back():
    """The serialiser is the one part of this that no referee examines, so it is checked by round trip."""
    from lineweight.core import parse_path
    chain = curve.fit_chain(a_sine(40), 0.05)
    written = curve.chain_to_path(chain)
    assert written.startswith('M') and 'C' in written
    read = parse_path(written, samples=8)[0]
    assert curve.deviation(read, chain) <= 0.05, 'the written path is not the chain that was fitted'
