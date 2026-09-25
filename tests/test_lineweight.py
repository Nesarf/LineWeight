"""Tests for the pressure model, the outline expansion and the whole-document inking.

The two most useful tests here are regressions for mistakes that were made while this was being written, and both
were visible only by rendering an image and looking at it: a closed contour walked forwards and then backwards,
which drew its line twice and scalloped every hair mass into fish scales, and a brush with no taper dividing by
zero because a floating-point position can land a hair above 1.0.
"""
from __future__ import annotations

import math

from lineweight import BRUSHES, inked_svg, outline, parse_path, pressures, stroke


def test_parse_handles_the_commands_a_generator_writes():
    polys = parse_path('M 0 0 L 10 0 Q 15 5 10 10 Z')
    assert len(polys) == 1
    # the quadratic is sampled, so the curve arrives as a polyline like everything else
    assert len(polys[0]) > 4
    assert polys[0][0] == (0.0, 0.0)


def test_parse_ignores_what_it_does_not_know_rather_than_guessing():
    # an arc is not handled; the line before it still is, and nothing raises
    polys = parse_path('M 0 0 L 10 0 A 5 5 0 0 1 20 0')
    assert polys and polys[0][0] == (0.0, 0.0)


def test_pressure_tapers_at_both_ends_of_an_open_stroke():
    path = [(x * 10.0, 0.0) for x in range(21)]
    ps = pressures(path, BRUSHES['ink'], seed=0)
    assert ps[0] < ps[len(ps) // 2]
    assert ps[-1] < ps[len(ps) // 2]
    assert all(0.0 < p <= 1.0 for p in ps)


def test_a_brush_with_no_taper_does_not_divide_by_zero():
    # regression: `t` accumulates from floating-point lengths and can exceed 1.0, so the taper test has to be
    # guarded by the taper being non-zero -- otherwise a legitimate brush setting crashes
    brush = dict(BRUSHES['ink'], taper_in=0.0, taper_out=0.0)
    path = [(x * 10.0, 0.0) for x in range(21)]
    ps = pressures(path, brush, seed=1)
    assert len(ps) == len(path)
    assert all(p > 0 for p in ps)


def test_pressure_is_lighter_through_a_sharp_turn():
    straight = [(x * 10.0, 0.0) for x in range(21)]
    turned = [(x * 10.0, 0.0) for x in range(10)] + [(90.0, y * 10.0) for y in range(1, 11)]
    a = pressures(straight, BRUSHES['ink'], seed=3)
    b = pressures(turned, BRUSHES['ink'], seed=3)
    assert min(b[8:13]) < max(a[8:13])


def test_the_outline_is_a_closed_shape_with_area():
    path = [(float(x), math.sin(x / 5.0) * 20.0) for x in range(40)]
    d = outline(path, [6.0] * len(path))
    assert d.startswith('M') and d.endswith('Z')
    xs = [float(v) for v in d.replace('M', '').replace('L', '').replace('Z', '').split()[0::2]]
    ys = [float(v) for v in d.replace('M', '').replace('L', '').replace('Z', '').split()[1::2]]
    assert max(xs) - min(xs) > 30
    assert max(ys) - min(ys) > 30


def test_a_wider_brush_produces_a_wider_outline():
    path = [(float(x), 0.0) for x in range(30)]
    thin = stroke(path, 'fine')[0]
    thick = stroke(path, 'ink')[0]
    def spread(d: str) -> float:
        ys = [float(v) for v in d.replace('M', '').replace('L', '').replace('Z', '').split()[1::2]]
        return max(ys) - min(ys)
    assert spread(thick) > spread(thin)


def test_inking_leaves_small_details_alone():
    # a heavy line around an eye is mud, so extent decides rather than a list of names
    svg = ('<svg><path d="M 0 0 L 100 0 L 100 80 L 0 80 Z" fill="#111"/>'
           '<path d="M 0 0 L 5 0 L 5 5 Z" fill="#222"/></svg>')
    out = inked_svg(svg)
    assert out.count('<path') == 3          # the two originals, plus one contour for the big one
    assert inked_svg(svg).count('<path') == 3


def test_a_closed_contour_is_walked_once():
    # regression: walking a loop forwards and then backwards drew the line twice and scalloped the shapes it
    # outlined -- a defect that only a rendered image showed
    svg = '<svg><path d="M 0 0 L 100 0 L 100 80 L 0 80 Z" fill="#111"/></svg>'
    out = inked_svg(svg)
    contour = [p for p in out.split('<path') if 'fill="#2A1E26"' in p]
    assert len(contour) == 1
    # one walk of a four-point loop samples the same number of points as its perimeter, not twice that
    d = contour[0].split('d="')[1].split('"')[0]
    assert d.count('L') < 40
